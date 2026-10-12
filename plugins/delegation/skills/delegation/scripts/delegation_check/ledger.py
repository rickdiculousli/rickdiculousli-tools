"""Append-only JSONL evidence ledger with delegation lifecycle rules."""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import os
import platform
import re
import signal
import subprocess
import sys
import time
import tempfile
import threading
from typing import Sequence

from . import DelegationError
from . import locks, state
from .overlay import Lock, Role, Validator, _escapes
from .tree import state_dir, tree_hash, git_tree, with_extra_inputs

SCHEMA = 1
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
TIERS = ("execute", "routine")
OUTCOMES = ("done", "stuck", "abandoned")
CONTEXT_REF = re.compile(r"state:context/[^\s`\"\'<>),;]+")


def _context_hashes(root: Path, brief: bytes) -> dict[str, str]:
    """Hash each logical `state:context/` file the brief names, keyed by that path."""
    hashes = {}
    for ref in sorted(set(CONTEXT_REF.findall(brief.decode("utf-8", errors="replace")))):
        if ".." in Path(ref).parts:
            raise DelegationError(f"context path escapes state:context: {ref}")
        target = state.context_path(root, ref)
        if not target.is_file():
            raise DelegationError(f"context file not found: {target}")
        hashes[ref] = hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


def ledger_path(root: Path) -> Path:
    return state_dir(root) / "ledger.jsonl"


@contextlib.contextmanager
def ledger_lock(root: Path, write=False):
    paths = state.Paths(root)
    if write:
        state.opportunistic()
    with state.bind(paths), state.mutex(paths.state_root):
        paths.check()
        if write:
            paths.ensure()
        yield


def read_events(root: Path) -> list[dict]:
    """Read a complete ledger snapshot, serialized with appends."""
    with ledger_lock(root):
        return _read_events_unlocked(root)


def _read_events_unlocked(root: Path) -> list[dict]:
    """Read the ledger; the caller must already hold ledger_lock."""
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
    with ledger_lock(root, write=True):
        return _append(root, event)


def _pending(events: list[dict]) -> list[dict]:
    closed = {e.get("delegation") for e in events if e.get("event") == "close"}
    return [e for e in events if e.get("event") == "open" and e.get("delegation") not in closed]


def pending(root: Path) -> list[dict]:
    return _pending(read_events(root))


def _runbook_source(root: Path, reference: str) -> tuple[Path, bytes]:
    """Validate before reading; literal pathspecs cannot authorize wildcard aliases."""
    if not reference or _escapes(reference):
        raise DelegationError(f"unsafe role runbook source: {reference}")
    source = root / reference.replace('\\', '/')
    try:
        resolved_name = source.resolve().relative_to(root).as_posix()
    except ValueError:
        raise DelegationError(f"role runbook source escapes repository: {reference}")
    for name in {reference.replace('\\', '/'), resolved_name}:
        tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', '--', ':(literal)' + name],
                                 cwd=root, capture_output=True)
        if tracked.returncode:
            raise DelegationError(f"role runbook source and resolved target must be tracked: {name}")
    if not source.is_file():
        raise DelegationError(f"role runbook source must be a tracked file: {reference}")
    return source, source.read_bytes()


def open_delegation(
    root: Path,
    delegation: str,
    tier: str,
    brief: Path,
    writes: bool,
    parallel_limit: int,
    extra_inputs: Sequence[str],
    continued_from: str | None = None,
    role_name: str | None = None,
    roles: dict[str, Role] | None = None,
) -> dict:
    if not ID.match(delegation):
        raise DelegationError(f"invalid delegation id: {delegation!r}")
    if tier not in TIERS:
        raise DelegationError(f"tier must be one of {', '.join(TIERS)}, got {tier!r}")
    root_resolved = root.resolve()
    brief = brief if brief.is_absolute() else root_resolved / brief
    if not brief.is_file():
        raise DelegationError(f"brief not found: {brief}")
    location = {}
    state_path = state_dir(root)
    try:
        brief_name = brief.resolve().relative_to(state_path).as_posix()
        location = {'location': 'state'}
    except ValueError:
        try:
            brief_name = brief.resolve().relative_to(root_resolved).as_posix()
        except ValueError:
            brief_name = str(brief.resolve())
    brief_bytes = brief.read_bytes()
    brief_sha = hashlib.sha256(brief_bytes).hexdigest()
    selected_role = role_name
    if continued_from and not selected_role:
        prior_open = next((event for event in read_events(root)
                           if event.get('event') == 'open' and event.get('delegation') == continued_from), {})
        selected_role = prior_open.get('role')
    selected = (roles or {}).get(selected_role)
    source_snapshot = None
    if selected:
        source_snapshot = _runbook_source(root_resolved, selected.runbook)[1]
    state.opportunistic()
    tree = git_tree(root)
    with ledger_lock(root):
        events = _read_events_unlocked(root)
        if any(e.get("event") == "open" and e.get("delegation") == delegation for e in events):
            raise DelegationError(f"delegation id already used: {delegation}")
        active = _pending(events)
        metadata = {}
        material = None
        context = {}
        prior = None
        if continued_from:
            prior = next((e for e in events if e.get("event") == "open"
                          and e.get("delegation") == continued_from), None)
            if prior is None:
                raise DelegationError(f"prior delegation not found: {continued_from}")
            if prior['tier'] != tier or (role_name and role_name != prior.get('role')):
                raise DelegationError("a continued agent must keep its role and tier")
            role_name = prior.get('role')
            if not role_name:
                raise DelegationError("continue requires a prior role delegation with a reuse cap")
        if role_name:
            role = (roles or {}).get(role_name)
            if role is None or role.tier != tier:
                raise DelegationError(f"unknown role or wrong tier: {role_name}")
            source_name = PurePosixPath(role.runbook.replace('\\', '/')).as_posix()
            source, source_bytes = _runbook_source(root_resolved, role.runbook)
            if source_snapshot != source_bytes:
                raise DelegationError("role runbook source changed while hashing tree; retry")
            runbook_ref = 'state:context/' + source_name
            target = state.context_path(root, runbook_ref)
            if target.is_symlink():
                raise DelegationError(f"materialized runbook destination must not be a symlink: {target}")
            digest = hashlib.sha256(source_bytes).hexdigest()
            pins = [recorded_digest for event in active
                    for reference, recorded_digest in event.get('context', {}).items()
                    if state.context_path(root, reference).resolve() == target.resolve()]
            if pins and (not target.is_file() or target.read_bytes() != source_bytes
                         or any(recorded_digest != digest for recorded_digest in pins)):
                raise DelegationError(f"role runbook context is pinned by open delegations; close all pins before rematerializing {source_name}")
            material = (target, source_bytes, source)
            # Hash references under the transaction, allowing a new role context reference
            # without writing its proposed bytes until all admission checks pass.
            for ref in sorted(set(CONTEXT_REF.findall(brief_bytes.decode('utf-8', errors='replace')))):
                if state.context_path(root, ref).resolve() == target.resolve():
                    context[ref] = digest
                else:
                    context.update(_context_hashes(root, ref.encode()))
            context[runbook_ref] = digest
            session = prior.get('agent_session', continued_from) if prior else delegation
            chain = [e for e in events if e.get('event') == 'open' and e.get('agent_session') == session]
            if any(e.get('agent_session') == session for e in active):
                raise DelegationError("role agent has an open brief; review and close it before continuing")
            uses = len(chain) + 1
            size = len(brief_bytes) + sum(
                len(source_bytes) if state.context_path(root, ref).resolve() == target.resolve()
                else state.context_path(root, ref).stat().st_size
                for ref in context
            )
            context_bytes = sum(e.get('context_bytes_added', 0) for e in chain) + size
            if ((role.max_uses is not None and uses > role.max_uses)
                    or (role.max_context_bytes is not None and context_bytes > role.max_context_bytes)):
                raise DelegationError(f"reuse cap hit for role {role_name}; have the agent refresh the role runbook first, then start a fresh agent")
            metadata = {'role': role_name, 'role_runbook': runbook_ref,
                        'role_runbook_source': source_name,
                        'agent_session': session, 'continued_from': continued_from,
                        'uses': uses, 'context_bytes': context_bytes, 'context_bytes_added': size}
        else:
            context = _context_hashes(root, brief_bytes)
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
        if material and _runbook_source(root_resolved, source_name)[1] != material[1]:
            raise DelegationError("role runbook source changed while opening; retry")
        # Reject unsafe extra inputs before committing proposed context bytes.
        with_extra_inputs(root, tree, extra_inputs)
        state.Paths(root).ensure()
        if material:
            target, source_bytes, source = material
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.read_bytes() != source_bytes:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                        temporary = handle.name
                        handle.write(source_bytes)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, target)
                finally:
                    if temporary and os.path.exists(temporary):
                        os.unlink(temporary)
        tree = with_extra_inputs(root, tree, extra_inputs)
        return _append(
            root,
            {
                "event": "open",
                "delegation": delegation,
                "tier": tier,
                "writes": writes,
                "brief": brief_name,
                **location,
                "brief_sha256": brief_sha,
                "context": context,
                "tree": tree,
                **metadata,
            },
        )


def load_brief(root: Path, delegation: str) -> tuple[dict, bytes]:
    """The open event and brief bytes, after checking the brief and context hashes."""
    opened = [e for e in pending(root) if e["delegation"] == delegation]
    if not opened:
        raise DelegationError(f"delegation is not open: {delegation}")
    brief = state.recorded_path(root, opened[0], "brief")
    if not brief.is_file():
        raise DelegationError(f"brief not found: {brief}")
    data = brief.read_bytes()
    if hashlib.sha256(data).hexdigest() != opened[0]["brief_sha256"]:
        raise DelegationError(f"brief changed since open: {brief}")
    for ref, digest in opened[0].get("context", {}).items():
        target = state.context_path(root, ref)
        if not target.is_file():
            raise DelegationError(f"context file not found: {target}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise DelegationError(f"context changed since open: {target}")
    return opened[0], data


def close_delegation(root: Path, delegation: str, outcome: str, note: str | None) -> dict:
    if outcome not in OUTCOMES:
        raise DelegationError(f"outcome must be one of {', '.join(OUTCOMES)}, got {outcome!r}")
    with ledger_lock(root, write=True):
        if delegation not in {e["delegation"] for e in _pending(_read_events_unlocked(root))}:
            raise DelegationError(f"delegation is not open: {delegation}")
        return _append(
            root,
            {"event": "close", "delegation": delegation, "outcome": outcome, "note": note},
        )


TAIL_LINES = 40
TAIL_CHARS = 4000


FORWARDED = ("SIGTERM", "SIGINT", "SIGHUP")
FORWARD_GRACE = 1.0


class _Forwarded(BaseException):
    """Unwinds communicate() after a caller's signal was passed to the child group."""


def execute(
    root: Path, command: str | Sequence[str], timeout: float | None, capture: bool = True
) -> tuple[int | None, bool, bytes]:
    """Run a shell command string (or an argv list), killing its process group on timeout.

    The child runs in its own session, so on POSIX a SIGTERM/SIGINT/SIGHUP sent to
    this process is forwarded to the child's process group. If the group is still
    alive after FORWARD_GRACE seconds it is killed; the process then exits with
    128 + signal, releasing any lock it holds.
    """
    posix = os.name == "posix"
    process = subprocess.Popen(
        command,
        shell=isinstance(command, str),
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        start_new_session=posix,
    )
    received: list[int] = []

    def forward(signum, _frame):
        received.append(signum)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signum)
        raise _Forwarded()

    previous = {}
    try:
        try:
            if posix and threading.current_thread() is threading.main_thread():
                for name in FORWARDED:
                    number = getattr(signal, name)
                    previous[number] = signal.signal(number, forward)
            output, _ = process.communicate(timeout=timeout)
            return process.returncode, False, output or b""
        except subprocess.TimeoutExpired:
            if posix:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            output, _ = process.communicate()
            return None, True, output or b""
        except _Forwarded:
            for number in previous:
                signal.signal(number, signal.SIG_IGN)
            try:
                process.communicate(timeout=FORWARD_GRACE)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
            raise SystemExit(128 + received[0])
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def log_path(root: Path, result_id: str) -> Path:
    """Where a result's complete output is kept: state-relative logs/<delegation>/<n>.log."""
    delegation, _, number = result_id.rpartition("#")
    return state_dir(root) / "logs" / delegation / f"{number}.log"


def run_validator(
    root: Path,
    delegation: str,
    name: str | None,
    validator: Validator,
    lock: Lock | None,
    extra_inputs: Sequence[str],
    timeout: float | None,
    argv: Sequence[str] | None = None,
) -> dict:
    if delegation not in {e["delegation"] for e in pending(root)}:
        raise DelegationError(f"delegation is not open: {delegation}")
    if validator.requires and sys.platform not in validator.requires:
        raise DelegationError(
            f'validator "{name}" requires {"|".join(validator.requires)}; this host is {sys.platform}. '
            "Nothing was recorded; leave it to a session on a matching host."
        )
    timeout = timeout if timeout is not None else validator.timeout
    held = (
        locks.hold(root, validator.lock, lock or Lock(),
                   {"delegation": delegation, "command": name if name is not None else validator.command})
        if validator.lock
        else contextlib.nullcontext({"slot": None, "wait_s": None})
    )
    with state.activity(root, "validator"), held as slot:
        before = tree_hash(root, extra_inputs)
        started = time.monotonic()
        code, timed_out, output = execute(root, argv if argv is not None else validator.command, timeout)
        duration = round(time.monotonic() - started, 3)
        after = tree_hash(root, extra_inputs)
    text = output.decode("utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]
    with ledger_lock(root, write=True):
        events = _read_events_unlocked(root)
        if delegation not in {e["delegation"] for e in _pending(events)}:
            raise DelegationError(f"delegation closed while the validator ran: {delegation}")
        count = sum(
            1
            for e in events
            if e.get("event") == "result" and e.get("delegation") == delegation
        )
        result_id = f"{delegation}#{count + 1}"
        log = log_path(root, result_id)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(output)
        return _append(
            root,
            {
                "event": "result",
                "id": result_id,
                "delegation": delegation,
                "validator": name,
                "command": validator.command,
                "exit": code,
                "ok": code == 0 and not timed_out,
                "timed_out": timed_out,
                "timeout_s": timeout,
                "duration_s": duration,
                "lock": validator.lock,
                "lock_slot": slot["slot"],
                "lock_wait_s": slot["wait_s"],
                "tree": before,
                "stable": before == after,
                "host": {"platform": sys.platform, "machine": platform.machine(), "node": platform.node()},
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "output_tail": tail,
                "log": log.relative_to(state_dir(root)).as_posix(),
                "location": "state",
            },
        )


def judge_run(
    root: Path,
    name: str,
    validator: Validator,
    lock: Lock | None,
    extra_inputs: Sequence[str],
    timeout: float | None,
) -> dict:
    """Run a registered validator for the judge: open, record and close one self-delegation.

    The delegation never outlives the run, so nothing is left pending for a gate or relay.
    """
    if validator.requires and sys.platform not in validator.requires:
        raise DelegationError(
            f'validator "{name}" requires {"|".join(validator.requires)}; this host is {sys.platform}. '
            "Nothing was recorded; leave it to a session on a matching host."
        )
    delegation = "judge-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + os.urandom(3).hex()
    tree = tree_hash(root, extra_inputs)
    with ledger_lock(root, write=True):
        writers = [e["delegation"] for e in _pending(_read_events_unlocked(root)) if e.get("writes")]
        if writers:
            raise DelegationError(f"writer {', '.join(writers)} is open; review and close it before a judge run")
        _append(root, {"event": "open", "delegation": delegation, "tier": "judge", "writes": False,
                       "brief": None, "brief_sha256": None, "context": {}, "tree": tree})
    try:
        return run_validator(root, delegation, name, validator, lock, extra_inputs, timeout)
    finally:
        close_delegation(root, delegation, "done", "judge run")


def query(root: Path, delegation: str, tree: str | None) -> list[dict]:
    results = [
        e
        for e in read_events(root)
        if e.get("event") == "result" and e.get("delegation") == delegation
    ]
    if tree is not None:
        results = [e for e in results if e.get("tree") == tree and e.get("stable")]
    return results
