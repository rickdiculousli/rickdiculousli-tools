"""Counting native locks with root-mutex protected holder/waiter lifecycles.

With an overlay lock provider, slots are leases held by an external command
instead (see `lease`); the native files are not touched.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from typing import BinaryIO, Iterator

from . import DelegationError, state
from .file_lock import release, try_acquire
from .overlay import Lock

POLL_S = 0.2
ANNOUNCE_GRACE_S = 1.0
PROVIDER_POLL_S = 1.0
PROVIDER_BUSY = 3
PROVIDER_TIMEOUT_S = 60.0


def env_name(name: str) -> str:
    return 'DELEGATION_LOCK_' + name.upper().replace('-', '_')


def slots(name: str, lock: Lock) -> int:
    value = os.environ.get(env_name(name))
    if value is None:
        return lock.slots
    if not value.strip().isdigit() or int(value) < 1:
        raise DelegationError(f'{env_name(name)} must be a positive integer, got {value!r}')
    return int(value)


def _try(path: Path) -> BinaryIO | None:
    return try_acquire(path)


def _metadata_path(path):
    return path.with_suffix('.json')


def _read(path):
    return state.read(_metadata_path(path), {})


def _describe(metadata):
    holder = metadata.get('holder') if metadata else None
    if not holder:
        return 'held (no details yet)'
    who = holder.get('delegation') or 'no delegation'
    return f"held by {who} (pid {holder.get('pid')}, since {holder.get('since')}): {holder.get('command')}"


def _prune(meta):
    # Reused PIDs are confirmed different generations, never live old owners.
    meta['waiters'] = {k: v for k, v in meta.get('waiters', {}).items() if state.alive(v) is not False}
    if meta.get('holder') and state.alive(meta['holder']) is False:
        meta['holder'] = None
    return meta


def status(root: Path, name: str, lock: Lock) -> list[str]:
    paths = state.Paths(root)
    lines = []
    with state.mutex(paths.state_root):
        paths.check()
        for slot in range(slots(name, lock)):
            path = paths.locks / f'{name}.{slot}.lock'
            # Inspection creates neither payload nor slots.
            if not path.exists():
                lines.append(f'{name}.{slot} free')
                continue
            handle = _try(path)
            if handle is None:
                lines.append(f'{name}.{slot} {_describe(_read(path))}')
            else:
                release(handle)
                lines.append(f'{name}.{slot} free')
    return lines


def _provider_call(root: Path, provider: str, *args: str) -> tuple[int, str, str]:
    """Run `<provider> <args>` from the worktree root; a missing or hanging provider is an error."""
    argv = [*shlex.split(provider), *args]
    try:
        done = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, errors="replace", timeout=PROVIDER_TIMEOUT_S)
    except FileNotFoundError as error:
        raise DelegationError(f'lock provider not found: {error.filename or argv[0]} (overlay ## Locks provider)') from error
    except subprocess.TimeoutExpired as error:
        raise DelegationError(f'lock provider gave no answer in {PROVIDER_TIMEOUT_S:g}s: {shlex.join(argv)}') from error
    return done.returncode, done.stdout, done.stderr


def _ttl(lock: Lock) -> str:
    return str(max(1, math.ceil(lock.ttl)))


@contextlib.contextmanager
def lease(root: Path, name: str, lock: Lock, provider: str) -> Iterator[dict]:
    """Hold one lease on `name` from the provider for the duration of the block.

    `acquire <name> --ttl N` exits 0 with the lease key on stdout, 3 when every
    slot is taken (polled until `wait` runs out), anything else is a provider
    error and nothing runs. The lease is renewed every ttl/3 seconds in the
    background; a failed renewal is reported in `lease.lost`, and `release <key>`
    always runs when the block ends.
    """
    started, announced = time.monotonic(), False
    while True:
        code, out, err = _provider_call(root, provider, "acquire", name, "--ttl", _ttl(lock))
        if code == 0:
            key = next((line.strip() for line in out.splitlines() if line.strip()), "")
            if not key:
                raise DelegationError(f'lock provider acquired {name} but printed no lease key: {provider}')
            break
        reason = (err.strip() or out.strip()).splitlines()[-1:] or ["no reason given"]
        if code != PROVIDER_BUSY:
            raise DelegationError(f'lock provider failed to acquire {name} (exit {code}): {reason[0]}')
        waited = time.monotonic() - started
        if lock.wait is not None and waited >= lock.wait:
            raise DelegationError(f'lock {name} still busy after {lock.wait:g}s: {reason[0]}')
        if not announced:
            print(f'waiting for lock {name} from provider: {reason[0]}', file=sys.stderr)
            announced = True
        time.sleep(PROVIDER_POLL_S)
    info = {'provider': provider, 'key': key, 'ttl_s': lock.ttl, 'renewals': 0, 'lost': False}
    stop = threading.Event()

    def renew() -> None:
        while not stop.wait(max(0.1, lock.ttl / 3)):
            try:
                code, _, err = _provider_call(root, provider, "renew", key, "--ttl", _ttl(lock))
            except DelegationError as error:
                code, err = -1, str(error)
            if code == 0:
                info['renewals'] += 1
            else:
                info['lost'] = True
                print(f'lock provider could not renew {name} lease {key}: {err.strip() or code}', file=sys.stderr)

    keeper = threading.Thread(target=renew, name=f'lease-{name}', daemon=True)
    keeper.start()
    try:
        yield {'slot': None, 'wait_s': round(time.monotonic() - started, 3), 'lease': info}
    finally:
        stop.set()
        keeper.join()
        try:
            code, _, err = _provider_call(root, provider, "release", key)
        except DelegationError as error:
            code, err = -1, str(error)
        if code != 0:
            print(f'lock provider could not release {name} lease {key}: {err.strip() or code}', file=sys.stderr)


@contextlib.contextmanager
def hold(root: Path, name: str, lock: Lock, holder: dict, provider: str | None = None) -> Iterator[dict]:
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name):
        raise DelegationError('Invalid resource lock name: ' + name)
    if provider:
        with lease(root, name, lock, provider) as held:
            yield held
        return
    paths = state.Paths(root)
    count = slots(name, lock)
    token = uuid.uuid4().hex
    record = {**holder, **state.owner(), 'worktree': str(paths.root),
              'since': datetime.now(timezone.utc).isoformat()}
    started, announced = time.monotonic(), False
    handle, selected = None, None
    slot_paths = [paths.locks / f'{name}.{slot}.lock' for slot in range(count)]
    try:
        while True:
            with state.mutex(paths.state_root):
                paths.ensure()
                paths.locks.mkdir(parents=True, exist_ok=True)
                for slot, path in enumerate(slot_paths):
                    candidate = _try(path)
                    meta = _prune(_read(path))
                    if candidate is not None:
                        # An uncertain owner protects its state even when OS lock is free.
                        if meta.get('holder'):
                            release(candidate)
                        else:
                            handle, selected = candidate, slot
                            meta['holder'] = record
                    if handle is None:
                        meta.setdefault('waiters', {})[token] = record
                    else:
                        meta.setdefault('waiters', {}).pop(token, None)
                    state.atomic(_metadata_path(path), meta)
                    if handle is not None:
                        break
                # Remove our waiter registrations from earlier unsuccessful slots.
                if handle is not None:
                    for path in slot_paths:
                        if not path.exists():
                            continue
                        meta = _read(path)
                        if token in meta.get('waiters', {}):
                            del meta['waiters'][token]
                            state.atomic(_metadata_path(path), meta)
                busy = '; '.join(f'{name}.{i} {_describe(_read(p))}' for i, p in enumerate(slot_paths))
            if handle is not None:
                break
            waited = time.monotonic() - started
            if lock.wait is not None and waited >= lock.wait:
                raise DelegationError(f'lock {name} still busy after {lock.wait:g}s: {busy}')
            if not announced:
                print(f'waiting for lock {name}: {busy}', file=sys.stderr)
                announced = True
            time.sleep(POLL_S)
        yield {'slot': selected, 'wait_s': round(time.monotonic() - started, 3)}
    finally:
        try:
            with state.mutex(paths.state_root):
                for slot, path in enumerate(slot_paths):
                    if not path.exists():
                        continue
                    meta = _read(path)
                    meta.get('waiters', {}).pop(token, None)
                    if slot == selected:
                        meta['holder'] = None
                    state.atomic(_metadata_path(path), meta)
                if handle is not None:
                    release(handle)
                    handle = None
        finally:
            if handle is not None:
                release(handle)
