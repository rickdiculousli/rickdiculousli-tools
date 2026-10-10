"""Append-only JSONL evidence ledger with delegation lifecycle rules."""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import re
import signal
import subprocess
import time
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
    root_resolved = root.resolve()
    brief = brief if brief.is_absolute() else root_resolved / brief
    if not brief.is_file():
        raise DelegationError(f"brief not found: {brief}")
    try:
        brief_name = brief.resolve().relative_to(root_resolved).as_posix()
    except ValueError:
        brief_name = str(brief)
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
                "brief": brief_name,
                "brief_sha256": brief_sha,
                "tree": tree,
            },
        )


def load_brief(root: Path, delegation: str) -> bytes:
    opened = [e for e in pending(root) if e["delegation"] == delegation]
    if not opened:
        raise DelegationError(f"delegation is not open: {delegation}")
    brief = Path(opened[0]["brief"])
    brief = brief if brief.is_absolute() else root.resolve() / brief
    if not brief.is_file():
        raise DelegationError(f"brief not found: {brief}")
    data = brief.read_bytes()
    if hashlib.sha256(data).hexdigest() != opened[0]["brief_sha256"]:
        raise DelegationError(f"brief changed since open: {brief}")
    return data


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


TAIL_LINES = 40
TAIL_CHARS = 4000


def _execute(root: Path, command: str, timeout: float | None) -> tuple[int | None, bool, bytes]:
    posix = os.name == "posix"
    process = subprocess.Popen(
        command,
        shell=True,
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=posix,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, False, output
    except subprocess.TimeoutExpired:
        if posix:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        output, _ = process.communicate()
        return None, True, output


def run_validator(
    root: Path,
    delegation: str,
    name: str,
    command: str,
    extra_inputs: Sequence[str],
    timeout: float | None,
) -> dict:
    if delegation not in {e["delegation"] for e in pending(root)}:
        raise DelegationError(f"delegation is not open: {delegation}")
    before = tree_hash(root, extra_inputs)
    started = time.monotonic()
    code, timed_out, output = _execute(root, command, timeout)
    duration = round(time.monotonic() - started, 3)
    after = tree_hash(root, extra_inputs)
    text = output.decode("utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]
    with ledger_lock(root):
        events = read_events(root)
        if delegation not in {e["delegation"] for e in _pending(events)}:
            raise DelegationError(f"delegation closed while the validator ran: {delegation}")
        count = sum(
            1
            for e in events
            if e.get("event") == "result" and e.get("delegation") == delegation
        )
        return _append(
            root,
            {
                "event": "result",
                "id": f"{delegation}#{count + 1}",
                "delegation": delegation,
                "validator": name,
                "command": command,
                "exit": code,
                "ok": code == 0 and not timed_out,
                "timed_out": timed_out,
                "duration_s": duration,
                "tree": before,
                "stable": before == after,
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "output_tail": tail,
            },
        )


def query(root: Path, delegation: str, tree: str | None) -> list[dict]:
    results = [
        e
        for e in read_events(root)
        if e.get("event") == "result" and e.get("delegation") == delegation
    ]
    if tree is not None:
        results = [e for e in results if e.get("tree") == tree and e.get("stable")]
    return results
