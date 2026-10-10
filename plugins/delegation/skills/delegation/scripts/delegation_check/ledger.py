"""Append-only JSONL evidence ledger with delegation lifecycle rules."""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Iterator, Sequence

from . import DelegationError
from .tree import state_dir, tree_hash

try:
    import fcntl
except ImportError:  # pragma: no cover - not available on Windows
    fcntl = None  # type: ignore[assignment]

SCHEMA = 1
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
TIERS = ("execute", "routine")
OUTCOMES = ("done", "stuck", "abandoned")


def ledger_path(root: Path) -> Path:
    return state_dir(root) / "ledger.jsonl"


@contextlib.contextmanager
def ledger_lock(root: Path) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    with (state_dir(root) / "ledger.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_events(root: Path) -> list[dict]:
    path = ledger_path(root)
    if not path.exists():
        return []
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError as error:
                raise DelegationError(f"ledger line {number}: {error}") from error
            if not isinstance(event, dict):
                raise DelegationError(f"ledger line {number}: not a JSON object")
            events.append(event)
    return events


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append(root: Path, event: dict) -> dict:
    """Append one line. The caller must hold ledger_lock."""
    stamped = {"schema": SCHEMA, **event, "timestamp": _now()}
    line = json.dumps(stamped, sort_keys=False, ensure_ascii=False) + "\n"
    with ledger_path(root).open("ab") as handle:
        handle.write(line.encode("utf-8"))
        handle.flush()
    return stamped


def append_event(root: Path, event: dict) -> dict:
    with ledger_lock(root):
        return _append(root, event)


def _pending(events: list[dict]) -> list[dict]:
    closed = {e.get("delegation") for e in events if e.get("event") == "close"}
    return [e for e in events if e.get("event") == "open" and e.get("delegation") not in closed]


def pending(root: Path) -> list[dict]:
    return _pending(read_events(root))


def open_delegation(
    root: Path,
    delegation: str,
    tier: str,
    brief: Path,
    writes: bool,
    parallel_limit: int,
    extra_inputs: Sequence[str],
) -> dict:
    if not ID.match(delegation):
        raise DelegationError(f"invalid delegation id: {delegation!r}")
    if tier not in TIERS:
        raise DelegationError(f"tier must be one of {', '.join(TIERS)}, got {tier!r}")
    if not brief.is_file():
        raise DelegationError(f"brief not found: {brief}")
    brief_sha = hashlib.sha256(brief.read_bytes()).hexdigest()
    tree = tree_hash(root, extra_inputs)
    with ledger_lock(root):
        events = read_events(root)
        if any(e.get("event") == "open" and e.get("delegation") == delegation for e in events):
            raise DelegationError(f"delegation id already used: {delegation}")
        active = _pending(events)
        if writes and active:
            raise DelegationError(
                f"a writer needs the worktree to itself; open: {', '.join(e['delegation'] for e in active)}"
            )
        if not writes:
            writers = [e["delegation"] for e in active if e.get("writes")]
            if writers:
                raise DelegationError(f"writer {', '.join(writers)} is open; wait for it to close")
            if len(active) >= parallel_limit:
                raise DelegationError(
                    f"parallel limit reached ({len(active)} of {parallel_limit} readers open)"
                )
        return _append(
            root,
            {
                "event": "open",
                "delegation": delegation,
                "tier": tier,
                "writes": writes,
                "brief": str(brief),
                "brief_sha256": brief_sha,
                "tree": tree,
            },
        )


def close_delegation(root: Path, delegation: str, outcome: str, note: str | None) -> dict:
    if outcome not in OUTCOMES:
        raise DelegationError(f"outcome must be one of {', '.join(OUTCOMES)}, got {outcome!r}")
    with ledger_lock(root):
        if delegation not in {e["delegation"] for e in _pending(read_events(root))}:
            raise DelegationError(f"delegation is not open: {delegation}")
        return _append(
            root,
            {"event": "close", "delegation": delegation, "outcome": outcome, "note": note},
        )
