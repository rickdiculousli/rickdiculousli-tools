"""Counting locks shared by every worktree of a repository.

A lock with N slots is N files, `<name>.<slot>.lock`, in a directory under /tmp
keyed by git's common directory. Each slot has a native process lock. Windows
holder details use a sidecar so readers never access the byte-locked region.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import BinaryIO, Iterator

from . import DelegationError
from .file_lock import release, try_acquire
from .overlay import Lock
from .tree import lock_dir

POLL_S = 0.2
ANNOUNCE_GRACE_S = 1.0


def env_name(name: str) -> str:
    return "DELEGATION_LOCK_" + name.upper().replace("-", "_")


def slots(name: str, lock: Lock) -> int:
    """The overlay's slot count, unless this machine or session overrides it."""
    value = os.environ.get(env_name(name))
    if value is None:
        return lock.slots
    if not value.strip().isdigit() or int(value) < 1:
        raise DelegationError(f"{env_name(name)} must be a positive integer, got {value!r}")
    return int(value)


def _slot_path(root: Path, name: str, slot: int) -> Path:
    return lock_dir(root) / f"{name}.{slot}.lock"


def _try(path: Path) -> BinaryIO | None:
    return try_acquire(path)


def _metadata_path(path: Path) -> Path:
    # Keep the POSIX layout compatible with sessions using older versions.
    return path.with_suffix(".json") if os.name == "nt" else path


def _read(path: Path) -> dict | None:
    try:
        return json.loads(_metadata_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _describe(holder: dict | None) -> str:
    if not holder:
        return "held (no details yet)"
    who = holder.get("delegation") or "no delegation"
    return f"held by {who} (pid {holder.get('pid')}, since {holder.get('since')}): {holder.get('command')}"


def status(root: Path, name: str, lock: Lock) -> list[str]:
    """One line per slot: free, or who holds it."""
    lines = []
    for slot in range(slots(name, lock)):
        path = _slot_path(root, name, slot)
        handle = _try(path)
        if handle is None:
            lines.append(f"{name}.{slot} {_describe(_read(path))}")
            continue
        release(handle)
        lines.append(f"{name}.{slot} free")
    return lines


@contextlib.contextmanager
def hold(root: Path, name: str, lock: Lock, holder: dict) -> Iterator[dict]:
    """Wait for a free slot, then hold it for the block.

    Yields {"slot", "wait_s"}. Refuses (DelegationError) when the lock's wait
    limit passes first. Both POSIX and Windows use native process locks.
    """
    count = slots(name, lock)
    paths = [_slot_path(root, name, slot) for slot in range(count)]
    started = time.monotonic()
    announced = False
    while True:
        for slot, path in enumerate(paths):
            handle = _try(path)
            if handle is not None:
                break
        else:
            waited = time.monotonic() - started
            holders = [_read(p) for p in paths]
            busy = "; ".join(f"{name}.{i} {_describe(h)}" for i, h in enumerate(holders))
            if lock.wait is not None and waited >= lock.wait:
                raise DelegationError(f"lock {name} still busy after {lock.wait:g}s: {busy}")
            # A holder writes its details just after taking the slot; give it a moment.
            if not announced and (all(holders) or waited >= ANNOUNCE_GRACE_S):
                print(f"waiting for lock {name}: {busy}", file=sys.stderr, flush=True)
                announced = True
            time.sleep(POLL_S)
            continue
        break
    wait_s = round(time.monotonic() - started, 3)
    try:
        record = {
            **holder,
            "pid": os.getpid(),
            "worktree": str(root),
            "since": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        if os.name == "nt":
            _metadata_path(path).write_text(json.dumps(record) + "\n", encoding="utf-8")
        else:
            handle.seek(0)
            handle.truncate()
            handle.write((json.dumps(record) + "\n").encode("utf-8"))
            handle.flush()
        yield {"slot": slot, "wait_s": wait_s}
    finally:
        try:
            with contextlib.suppress(OSError):
                if os.name == "nt":
                    _metadata_path(path).unlink()
                else:
                    handle.seek(0)
                    handle.truncate()
        finally:
            release(handle)
