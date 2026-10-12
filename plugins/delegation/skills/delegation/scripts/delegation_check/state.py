"""Self-contained XDG identities, lifecycle transactions and collection.

Storage keys identify local paths; they never establish validator acceptance.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import subprocess
import tempfile
import time
import uuid
import warnings

from . import DelegationError
from .file_lock import exclusive, try_acquire, release

WEEK = 7 * 86400
MONTH = 30 * 86400


def xdg(kind):
    """Explicit XDG roots override platform defaults; Windows uses local app data."""
    name = 'XDG_' + kind.upper() + '_HOME'
    raw = os.environ.get(name)
    namespace = Path('rickdiculousli-tools') / 'delegation'
    if raw and Path(raw).is_absolute():
        path = Path(raw) / namespace
    else:
        if raw is not None:
            warnings.warn(name + ' is empty or relative; using the platform default.', RuntimeWarning)
        if sys_platform() == 'win32':
            local = os.environ.get('LOCALAPPDATA')
            base = Path(local) if local and Path(local).is_absolute() else Path.home() / 'AppData' / 'Local'
            path = base / namespace / kind
        else:
            path = Path.home() / ('.local/state' if kind == 'state' else '.cache') / namespace
    return path.resolve()


def key(path):
    return hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode('utf-8')).hexdigest()


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as error:
        raise DelegationError('Cannot read state; inspect ' + str(path)) from error


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.write-', delete=False) as handle:
            name = handle.name
            handle.write((json.dumps(value, sort_keys=True, indent=2) + '\n').encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def file_identity(path):
    info = Path(path).stat()
    birth = getattr(info, 'st_birthtime', None)
    if birth is None and sys_platform() == 'linux':
        # Linux's Python stat lacks btime. statx supplies nanosecond creation
        # identity, preventing rapid inode reuse from resurrecting old payloads.
        import ctypes
        import struct
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            libc.statx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
            buffer = ctypes.create_string_buffer(256)
            if libc.statx(-100, os.fsencode(path), 0, 0x800, buffer) == 0 and struct.unpack_from('=I', buffer)[0] & 0x800:
                seconds, nanos = struct.unpack_from('=qI', buffer, 80)
                birth = {'seconds': seconds, 'nanoseconds': nanos}
        except (OSError, AttributeError):
            pass  # Older kernels/filesystems expose only device/inode identity.
    return {'device': info.st_dev, 'inode': info.st_ino, 'birth': birth}



def volume(path):
    path = Path(path)
    while True:
        try:
            return path.stat().st_dev
        except FileNotFoundError:
            if path == path.parent:
                raise
            path = path.parent


def process_start(pid):
    """Native process generation; None means uncertain, 'gone' confirmed absent."""
    try:
        if sys_platform() == 'linux':
            raw = Path(f'/proc/{pid}/stat').read_text()
            fields = raw[raw.rindex(')') + 2:].split()
            if fields[0] == 'Z':
                return 'gone'
            return Path('/proc/sys/kernel/random/boot_id').read_text().strip() + ':' + fields[19]
        if sys_platform() == 'darwin':
            import ctypes
            class BSDInfo(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint32) for name in ('flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')] + [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)] + [(name, ctypes.c_uint32) for name in ('nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')] + [('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]
            libproc = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
            libproc.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
            info = BSDInfo()
            count = libproc.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
            if count == ctypes.sizeof(info):
                return f'{info.start_sec}:{info.start_usec}'
            return 'gone' if ctypes.get_errno() == 3 else None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return 'gone' if ctypes.get_last_error() == 87 else None
            try:
                exit_code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return None
                if exit_code.value != 259:
                    return 'gone'
                created, exited, kern, user = (wintypes.FILETIME() for _ in range(4))
                if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kern), ctypes.byref(user)):
                    return None
                return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
            finally:
                kernel.CloseHandle(handle)
        # macOS/BSD: ps includes calendar start time rather than a reused PID.
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='], capture_output=True, text=True, timeout=2)
        return result.stdout.strip() or ('gone' if result.returncode == 1 else None)
    except FileNotFoundError:
        return 'gone' if sys_platform() == 'linux' else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def sys_platform():
    import sys
    return sys.platform


def owner():
    return {'pid': os.getpid(), 'start': process_start(os.getpid())}


def alive(record):
    if not isinstance(record, dict) or type(record.get('pid')) is not int or record['pid'] <= 0:
        return None
    current = process_start(record['pid'])
    if current == 'gone':
        return False
    if current is None or not record.get('start'):
        return None
    return current == record['start']


def verify_location(root=None):
    forbidden = [Path(__file__).resolve().parents[4]]
    if root is not None:
        forbidden += [root.root, root.common, root.git]
    else:
        # Explicit GC may run inside or outside Git. It must obey the same
        # external-root rule as normal checker commands, before creating locks.
        from .tree import _git, repo_root
        try:
            current = repo_root(Path.cwd()).resolve()
        except DelegationError:
            current = None
        if current is not None:
            forbidden.append(current)
            for option in ('--git-common-dir', '--git-dir'):
                directory = Path(_git(current, ['rev-parse', option]).strip())
                forbidden.append((directory if directory.is_absolute() else current / directory).resolve())
    for kind in ('state', 'cache'):
        target = xdg(kind)
        if any(target.is_relative_to(path.resolve()) for path in forbidden):
            raise DelegationError('XDG_' + kind.upper() + '_HOME puts runtime files inside a checkout, Git directory or installed plugin; use a shared external root.')


@contextmanager
def mutex(state_root=None):
    state_root = state_root or xdg('state')
    if (state_root / 'state.lock').is_symlink():
        raise DelegationError('Unsafe root state.lock symlink; inspect the shared XDG root.')
    with ExitStack() as stack:
        try:
            state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            stack.enter_context(exclusive(state_root / 'state.lock', timeout=10))
        except OSError as error:
            raise DelegationError('XDG state root is not writable; configure the same writable XDG_STATE_HOME for every coordinating process and allow that root in the host sandbox: ' + str(state_root)) from error
        yield


class Paths:
    def __init__(self, root):
        from .tree import _git, repo_root
        self.root = repo_root(Path(root).resolve()).resolve()
        def git_path(option):
            path = Path(_git(self.root, ['rev-parse', option]).strip())
            return (path if path.is_absolute() else self.root / path).resolve()
        self.common = git_path('--git-common-dir')
        self.git = git_path('--git-dir')
        self.state_root, self.cache_root = xdg('state'), xdg('cache')
        self.repo_key, self.worktree_key = key(self.common), key(self.root)
        self.repo = self.state_root / self.repo_key
        self.path = self.repo / 'worktrees' / self.worktree_key
        self.cache = self.cache_root / self.repo_key / 'worktrees' / self.worktree_key
        self.locks = self.repo / 'locks'
        verify_location(self)
        # Capture Git discovery and identity before entering bookkeeping locks.
        self.identity = {'version': 1, 'worktree': str(self.root), 'common': str(self.common), 'git': str(self.git),
                         'files': {k: file_identity(v) for k, v in [('worktree', self.root), ('common', self.common), ('git', self.git)]},
                         'volume': volume(self.root)}
        self.repo_identity = {'version': 1, 'common': str(self.common), 'file': file_identity(self.common)}

    def json(self):
        return {'version': 1, 'state_root': str(self.state_root), 'cache_root': str(self.cache_root),
                'repository_key': self.repo_key, 'worktree_key': self.worktree_key,
                'worktree_state_directory': str(self.path), 'brief_directory': str(self.path / 'briefs'),
                'context_directory': str(self.path / 'context'), 'log_directory': str(self.path / 'logs'),
                'resource_lock_directory': str(self.locks), 'root_mutex': str(self.state_root / 'state.lock'),
                'scratch_directory': str(self.cache / 'scratch'), 'kind_registry': str(self.repo / 'kinds.json'),
                'pattern_log': str(self.repo / 'patterns.jsonl')}

    def check(self):
        if any(p.is_symlink() for p in (self.repo, self.path.parent, self.path)):
            raise DelegationError('Unsafe symlink in XDG repository/worktree payload.')
        if any(file_identity(path) != self.identity['files'][name] for name, path in [('worktree', self.root), ('common', self.common), ('git', self.git)]):
            raise DelegationError('Worktree/repository identity changed during discovery; retry and recover explicitly.')
        saved = read(self.path / 'identity.json')
        repo = read(self.repo / 'identity.json')
        if repo is not None and any(repo.get(k) != v for k, v in self.repo_identity.items()):
            raise DelegationError('Repository identity changed; inspect state gc and recover the old generation explicitly.')
        if saved is not None and any(saved.get(k) != v for k, v in self.identity.items()):
            raise DelegationError('Worktree identity changed; inspect state gc and recover the old generation explicitly.')
        if saved is None and self.path.exists() and (not safe_payload(self.path) or (self.path / 'ledger.jsonl').exists()):
            raise DelegationError('Unknown worktree payload without identity; inspect ' + str(self.path))

    def ensure(self):
        """Caller holds mutex. No validators or Git processes run here."""
        self.check()
        now = time.time()
        if not (self.repo / 'identity.json').exists():
            atomic(self.repo / 'identity.json', {**self.repo_identity, 'created': now})
        saved = read(self.path / 'identity.json', {**self.identity, 'created': now})
        saved.update(last_mutation=now, missing_since=None)
        atomic(self.path / 'identity.json', saved)
        return self.path


_current_paths = ContextVar('delegation_paths', default=None)


def paths_for(root):
    current = _current_paths.get()
    if current is not None and current.root == Path(root).resolve():
        return current
    return Paths(root)


@contextmanager
def bind(paths):
    token = _current_paths.set(paths)
    try:
        yield
    finally:
        _current_paths.reset(token)


def confined(base, relative):
    if (not relative or PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).is_absolute()
            or '..' in PurePosixPath(relative.replace('\\', '/')).parts):
        raise DelegationError('State path escapes its directory: ' + relative)
    target = base / relative
    if not target.resolve().is_relative_to(base.resolve()):
        raise DelegationError('State path symlink escapes its directory: ' + relative)
    return target


def context_path(root, ref):
    paths = paths_for(root)
    if ref.startswith('state:context/'):
        return confined(paths.path / 'context', ref[len('state:context/'):])
    raise DelegationError('Context references must use state:context/<relative-path>: ' + ref)


def recorded_path(root, event, field):
    paths = paths_for(root)
    ref = event[field]
    if event.get('location') == 'state':
        return confined(paths.path, ref)
    path = Path(ref)
    return path if path.is_absolute() else paths.root / path


@contextmanager
def activity(root, kind):
    """A process-generation record pins payload/cache during long operations."""
    paths = paths_for(root)
    record = paths.path / 'active' / (uuid.uuid4().hex + '.json')
    with mutex(paths.state_root):
        paths.ensure()
        atomic(record, {**owner(), 'kind': kind, 'created': time.time()})
    try:
        yield paths
    finally:
        with mutex(paths.state_root):
            record.unlink(missing_ok=True)


def events_at(path):
    if not path.exists():
        return []
    try:
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if not all(isinstance(event, dict) for event in events):
            raise ValueError('not objects')
        return events
    except (ValueError, UnicodeError) as error:
        raise DelegationError('Malformed ledger: ' + str(path)) from error


def pending_events(events):
    closed = {e.get('delegation') for e in events if e.get('event') == 'close'}
    return [e for e in events if e.get('event') == 'open' and e.get('delegation') not in closed]


def active_records(path, apply=False):
    protected = []
    for item in (path / 'active').glob('*.json'):
        record = read(item)
        live = alive(record)
        if live is False:
            if apply:
                item.unlink()
        else:
            protected.append(str(item))
    return protected


def registered(common, worktree):
    result = subprocess.run(['git', '--git-dir', common, 'worktree', 'list', '--porcelain', '-z'], capture_output=True, timeout=10)
    if result.returncode:
        return None
    return any(key(x[9:].decode('utf-8', 'surrogateescape')) == key(worktree)
               for x in result.stdout.split(b'\0') if x.startswith(b'worktree '))


def missing_status(saved):
    """Git discovery happens outside the root mutex; uncertain observations retain."""
    worktree, common = Path(saved['worktree']), Path(saved['common'])
    if volume(worktree) != saved['volume']:
        return 'unknown', 'unavailable volume'
    try:
        worktree.stat()
        if file_identity(worktree) != saved['files']['worktree']:
            return 'unknown', 'recreated worktree identity; recover explicitly'
        if file_identity(common) != saved['files']['common']:
            return 'unknown', 'changed repository identity'
        return 'present', 'existing worktree'
    except FileNotFoundError:
        # Only missing root counts. Missing Git identity in an existing root is uncertain.
        if worktree.exists():
            return 'unknown', 'missing Git identity'
        try:
            common.stat()
        except FileNotFoundError:
            if Path(saved['git']).exists():
                return 'unknown', 'inconsistent identity'
            return 'missing', 'confirmed deleted repository/worktree'
        if file_identity(common) != saved['files']['common']:
            return 'unknown', 'recreated repository identity'
        reg = registered(str(common), str(worktree))
        return ('missing', 'confirmed deleted worktree') if reg is False else ('unknown', 'registered missing or inaccessible worktree')


def locks_idle(directory, apply=False):
    """Caller holds mutex, closing unlink/recreate races with all acquisitions."""
    handles = []
    try:
        for item in directory.glob('*.lock'):
            if item.is_symlink() or item.with_suffix('.json').is_symlink():
                return False
            handle = try_acquire(item)
            if handle is None:
                return False
            handles.append(handle)
            meta = read(item.with_suffix('.json'), {})
            owners = ([meta['holder']] if meta.get('holder') else []) + list(meta.get('waiters', {}).values())
            if any(alive(record) is not False for record in owners):
                return False
        if directory.exists() and any(p.is_symlink() or p.suffix not in {'.lock', '.json'} or (p.suffix == '.json' and not p.with_suffix('.lock').exists()) for p in directory.iterdir()):
            return False
        return True
    finally:
        for handle in handles:
            release(handle)


def safe_payload(path):
    allowed = {'identity.json', 'ledger.jsonl', 'briefs', 'context', 'logs', 'active'}
    return all(not p.is_symlink() and (p.relative_to(path).parts[0] in allowed) for p in path.rglob('*'))


def remove_payload(path):
    # Identity survives partial deletion so a later collection can finish.
    for item in path.iterdir():
        if item.name == 'identity.json':
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    (path / 'identity.json').unlink()
    path.rmdir()


def gc(apply=False, if_due=False, now=None):
    verify_location()
    state_root, cache_root = xdg('state'), xdg('cache')
    now = time.time() if now is None else now
    result = {'version': 1, 'applied': apply, 'due': True, 'entries': []}
    if not state_root.exists() and not apply:
        return result
    # No Git child processes while holding bookkeeping mutex.
    observations = {}
    for path in state_root.glob('*/worktrees/*'):
        try:
            if any(p.is_symlink() for p in (path, path.parent, path.parent.parent)):
                continue
            saved = read(path / 'identity.json')
            observations[str(path)] = (saved, missing_status(saved)) if saved else (None, ('unknown', 'unknown identity'))
        except (DelegationError, OSError, KeyError, subprocess.TimeoutExpired):
            observations[str(path)] = (None, ('unknown', 'inaccessible identity'))
    with mutex(state_root):
        if if_due and now - read(state_root / 'gc.json', {}).get('last_sweep', 0) < WEEK:
            result['due'] = False
            return result
        for path in sorted(state_root.glob('*/worktrees/*')):
            entry = {'path': str(path), 'action': 'retain', 'reason': 'unknown identity'}
            result['entries'].append(entry)
            try:
                if any(p.is_symlink() for p in (path, path.parent, path.parent.parent)) or not safe_payload(path):
                    continue
                saved, observation = observations.get(str(path), (None, ('unknown', 'new identity')))
                if saved is None or key(saved['common']) != path.parent.parent.name or key(saved['worktree']) != path.name or read(path / 'identity.json') != saved:
                    continue
                status, entry['reason'] = observation
                events = events_at(path / 'ledger.jsonl')
                entry['pending'] = [e['delegation'] for e in pending_events(events)]
                protected = active_records(path, apply)
                cache = cache_root / path.parent.parent.name / 'worktrees' / path.name
                for attempt in (cache / 'hashing').glob('*'):
                    if alive(read(attempt / 'identity.json')) is not False:
                        protected.append(str(attempt))
                if protected:
                    entry['reason'] = 'active or uncertain process'
                    continue
                if status == 'missing':
                    since = saved.get('missing_since')
                    since = now if since is None else since
                    entry['deadline'] = since + WEEK
                    if apply and saved.get('missing_since') is None:
                        atomic(path / 'identity.json', {**saved, 'missing_since': since})
                    if now >= since + WEEK and locks_idle(path.parent.parent / 'locks'):
                        entry['action'] = 'remove'
                        if apply:
                            remove_payload(path)
                            cache = cache_root / path.parent.parent.name / 'worktrees' / path.name
                            if cache.exists() and not any(p.is_symlink() for p in [cache, *cache.rglob('*')]):
                                shutil.rmtree(cache)
                    continue
                if status != 'present':
                    continue
                if saved.get('missing_since') is not None and apply:
                    atomic(path / 'identity.json', {**saved, 'missing_since': None})
                pinned = set()
                for event in events:
                    for field in ('brief', 'log'):
                        ref = event.get(field, '')
                        if event.get('location') == 'state':
                            pinned.add(ref)
                    for ref in event.get('context', {}):
                        if ref.startswith('state:'):
                            pinned.add(ref[6:])
                # Current role declarations pin even runbooks not yet used by a delegation.
                from .overlay import load_overlay
                overlay = load_overlay(Path(saved['worktree']))
                for ref in overlay.extra_inputs:
                    if ref.startswith('state:context/'):
                        pinned.add(ref[6:])
                for role in overlay.roles.values():
                    pinned.add('context/' + PurePosixPath(role.runbook.replace('\\', '/')).as_posix())
                for folder in ('briefs', 'context'):
                    for item in (path / folder).rglob('*'):
                        if item.is_file() and not any(item.relative_to(path).as_posix() == ref or item.relative_to(path).as_posix().startswith(ref.rstrip('/') + '/') for ref in pinned) and now - item.stat().st_mtime >= MONTH:
                            result['entries'].append({'path': str(item), 'action': 'remove', 'reason': 'unreferenced for 30 days'})
                            if apply:
                                item.unlink()
                # Scratch is disposable working space; untouched files expire like briefs.
                scratch = cache / 'scratch'
                if scratch.is_dir() and not any(p.is_symlink() for p in [scratch, *scratch.parents]):
                    for item in sorted(scratch.rglob('*'), reverse=True):
                        if item.is_symlink() or item.is_file():
                            if now - item.lstat().st_mtime >= MONTH:
                                result['entries'].append({'path': str(item), 'action': 'remove', 'reason': 'scratch untouched for 30 days'})
                                if apply:
                                    item.unlink()
                        elif item.is_dir() and apply and not any(item.iterdir()):
                            item.rmdir()
            except (DelegationError, OSError, KeyError):
                entry['reason'] = 'unknown/inaccessible; retained'
        # Interrupted hash attempts are independent of worktree payload age.
        for attempt in cache_root.glob('*/worktrees/*/hashing/*'):
            entry = {'path': str(attempt), 'action': 'retain', 'reason': 'active or uncertain hashing owner'}
            result['entries'].append(entry)
            try:
                if any(p.is_symlink() for p in [attempt, *attempt.parents, *attempt.rglob('*')]):
                    continue
                if alive(read(attempt / 'identity.json')) is False:
                    entry.update(action='remove', reason='confirmed exited hashing owner')
                    if apply:
                        shutil.rmtree(attempt)
            except (OSError, DelegationError):
                pass
        from .patterns import prune
        for repo in state_root.iterdir():
            if not repo.is_dir() or repo.is_symlink() or len(repo.name) != 64:
                continue
            try:
                pruned = prune(repo, apply, now)
            except (DelegationError, OSError, KeyError, ValueError):
                pruned = {'path': str(repo / 'patterns.jsonl'), 'action': 'retain', 'reason': 'unreadable pattern log; inspect it'}
            if pruned:
                result['entries'].append(pruned)
            worktrees = repo / 'worktrees'
            if worktrees.exists() and any(worktrees.iterdir()):
                continue
            if worktrees.exists() and apply:
                worktrees.rmdir()
            saved = read(repo / 'identity.json', {})
            if not saved.get('common') or key(saved['common']) != repo.name:
                continue
            try:
                common = Path(saved['common'])
                common.stat()
                continue  # live repository retains slot inodes
            except FileNotFoundError:
                if volume(common) != saved['file']['device']:
                    continue
            except (OSError, KeyError):
                continue
            since = saved.get('missing_since', now)
            if apply and 'missing_since' not in saved:
                atomic(repo / 'identity.json', {**saved, 'missing_since': since})
            if now < since + WEEK or not locks_idle(repo / 'locks'):
                continue
            result['entries'].append({'path': str(repo), 'action': 'remove', 'reason': 'retired repository, no holders/waiters'})
            if apply and all(p.name in {'identity.json', 'worktrees', 'locks', 'kinds.json', 'patterns.jsonl'} for p in repo.iterdir()):
                shutil.rmtree(repo)
        if apply:
            for item in sorted(cache_root.glob('*/worktrees/*/hashing'), reverse=True):
                for parent in (item, item.parent, item.parent.parent, item.parent.parent.parent):
                    if parent.is_dir() and not parent.is_symlink() and not any(parent.iterdir()):
                        parent.rmdir()
            atomic(state_root / 'gc.json', {'version': 1, 'last_sweep': now})
    return result


def opportunistic():
    # Due check before Git discovery keeps normal commands cheap.
    if time.time() - read(xdg('state') / 'gc.json', {}).get('last_sweep', 0) >= WEEK:
        gc(apply=True, if_due=True)
