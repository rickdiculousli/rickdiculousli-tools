"""One permanent root lock protects identity, atomic writes and collection."""
from contextlib import contextmanager
from types import SimpleNamespace
import errno
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid
import warnings
from .git import path_key
from .model import Invalid

WEEK = 7 * 86400
MONTH = 30 * 86400


def xdg(kind):
    """Explicit XDG roots override platform defaults; Windows uses local app data."""
    name = 'XDG_' + kind.upper() + '_HOME'
    raw = os.environ.get(name)
    namespace = Path('rickdiculousli-tools') / 'long-horizon'
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
    return path


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as error:
        raise Invalid('Cannot read state; inspect or explicitly recover ' + str(path)) from error


def atomic(path, value, raw=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.write-', delete=False) as handle:
            name = handle.name
            handle.write(value if raw else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@contextmanager
def lock(root=None, timeout=10):
    root = root or xdg('state')
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle = open(root / 'state.lock', 'a+b')
    except OSError as error:
        raise Invalid('XDG state root is not writable; configure a shared writable XDG_STATE_HOME: ' + str(root)) from error
    locked = False
    try:
        try:
            import fcntl
            def acquire():
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except ImportError:
            try:
                import msvcrt
            except ImportError:
                raise Invalid('State writes require POSIX flock or Windows msvcrt locking.') from None
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'\0')
                handle.flush()
            def acquire():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire()
                locked = True
                break
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EACCES, errno.EDEADLK):
                    raise Invalid('Cannot lock shared XDG state root: ' + str(root)) from error
                if time.monotonic() >= deadline:
                    raise Invalid('State lock busy; retry after the current transaction.') from error
                time.sleep(.05)
        yield
    finally:
        try:
            if locked:
                release()
        finally:
            handle.close()


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



def containing_volume(path):
    candidate = Path(path)
    while True:
        try:
            return candidate.stat().st_dev
        except FileNotFoundError:
            if candidate == candidate.parent:
                raise
            candidate = candidate.parent


def identity(git, now):
    return {'version': 1, 'worktree': str(git.root), 'common': str(git.common), 'git': str(git.directory),
            'files': {key: file_identity(path) for key, path in
                      [('worktree', git.root), ('common', git.common), ('git', git.directory)]},
            'volume': file_identity(git.root)['device'],
            'created': now, 'last_mutation': now, 'missing_since': None}


class State:
    def __init__(self, git):
        self.git = git
        verify_location(git)
        self.root = xdg('state')
        self.path = self.root / path_key(git.common) / 'worktrees' / path_key(git.root)
        self.cache = xdg('cache') / path_key(git.common) / 'worktrees' / path_key(git.root)

    def compatible(self):
        saved = read(self.path / 'identity.json')
        if saved is None:
            return not self.path.exists()
        try:
            current = identity(self.git, time.time())
            return all(saved.get(key) == current[key] for key in ('version', 'worktree', 'common', 'git', 'files', 'volume'))
        except OSError:
            return False

    def get(self, relative, default=None):
        if not self.root.exists():
            return default
        with lock(self.root):
            if not self.compatible():
                raise Invalid('Worktree identity changed; inspect state gc and explicitly import recoverable evidence before reusing it.')
            return read(self.path / relative, default)

    def put(self, relative, value, immutable=False):
        try:
            gc(apply=True, if_due=True)
        except (Invalid, OSError) as error:
            warnings.warn('Opportunistic cleanup skipped: ' + str(error) + '; inspect state gc.', RuntimeWarning)
        with lock(self.root):
            now = time.time()
            if self.path.exists() and not self.compatible():
                retired = self.path.with_name(self.path.name + '.retired-' + uuid.uuid4().hex)
                os.rename(self.path, retired)
                saved = read(retired / 'identity.json', {})
                saved['retired_since'] = now
                atomic(retired / 'identity.json', saved)
            saved = read(self.path / 'identity.json') or identity(self.git, now)
            saved['last_mutation'] = now
            saved['missing_since'] = None
            old = read(self.path / relative)
            if immutable and old is not None and old != value:
                raise Invalid('Conflicting immutable state record: ' + relative)
            if old != value:
                atomic(self.path / relative, value)
            atomic(self.path / 'identity.json', saved)

    def remove(self, relative):
        with lock(self.root):
            if not self.compatible():
                raise Invalid('Worktree identity changed; refusing cleanup.')
            path = self.path / relative
            if path.is_file() and not path.is_symlink():
                path.unlink()


def registered(common, worktree):
    result = subprocess.run(['git', '--git-dir', common, 'worktree', 'list', '--porcelain', '-z'],
                            capture_output=True, timeout=10)
    if result.returncode:
        return None
    paths = [x[9:].decode('utf-8', 'surrogateescape') for x in result.stdout.split(b'\0') if x.startswith(b'worktree ')]
    return any(path_key(x) == path_key(worktree) for x in paths)


def safe_payload(path):
    allowed = {'identity.json', 'closure.json', 'evidence', 'snapshots', 'drafts', 'trailers.txt'}
    for item in path.iterdir():
        if item.is_symlink() or item.name not in allowed:
            return False
        if item.is_dir() and any(x.is_symlink() or (x.is_file() and x.suffix != '.json') for x in item.rglob('*')):
            return False
    return True


def gc(apply=False, if_due=False, now=None, location_root=None):
    verify_location(root_hint=location_root)
    root = xdg('state')
    now = time.time() if now is None else now
    result = {'entries': [], 'applied': apply, 'due': True}
    if not root.exists() and not xdg('cache').exists() and not apply:
        return result
    # Git registration probes occur before the root transaction. Revalidate the
    # exact identity snapshot under the lock before acting on each observation.
    registrations = {}
    for path in [*root.glob('*/worktrees/*'), *xdg('cache').glob('*/worktrees/*')]:
        if any(x.is_symlink() for x in (path, path.parent, path.parent.parent)):
            continue
        try:
            saved = read(path / 'identity.json')
            if saved and 'retired_since' not in saved:
                reg = registered(saved['common'], saved['worktree'])
                if not Path(saved['common']).exists() and not Path(saved['git']).exists() and containing_volume(saved['common']) == saved['files']['common']['device']:
                    reg = False
                registrations[str(path)] = (saved, reg)
        except (Invalid, OSError, KeyError, subprocess.TimeoutExpired):
            pass
    with lock(root):
        last = read(root / 'gc.json', {}).get('last_sweep', 0)
        if if_due and now - last < WEEK:
            result['due'] = False
            return result
        collect(root, apply, now, result, registrations)
        collect_cache(root, apply, now, result, registrations)
        if apply:
            atomic(root / 'gc.json', {'version': 1, 'last_sweep': now})
    return result


def collect(root, apply, now, result, registrations):
    for path in sorted(root.glob('*/worktrees/*')):
        if any(x.is_symlink() for x in (path, path.parent, path.parent.parent)) or not path.is_dir():
            continue
        entry = {'path': str(path), 'action': 'retain', 'reason': 'unknown identity'}
        result['entries'].append(entry)
        try:
            saved = read(path / 'identity.json')
            if not saved or path_key(saved['common']) != path.parent.parent.name or path.name.split('.retired-', 1)[0] != path_key(saved['worktree']) or not safe_payload(path):
                continue
            entry['pending'] = len(list((path / 'evidence').glob('*.json')))
            closure = read(path / 'closure.json', {})
            entry['unfinished_closure'] = bool(closure and any(closure.get('observations', {}).get(x, {}).get('outcome') != 'success' for x in closure.get('steps', [])))
            missing = False
            if 'retired_since' in saved:
                since = saved['retired_since']
                entry['reason'] = 'retired identity generation'
                missing = True
            else:
                paths = [Path(saved[key]) for key in ('worktree', 'common', 'git')]
                if containing_volume(paths[0]) != saved['volume']:
                    entry['reason'] = 'volume unavailable or changed'
                    continue
                # stat distinguishes permission errors from confirmed absence.
                present = []
                for item in paths:
                    try:
                        item.stat()
                        present.append(True)
                    except FileNotFoundError:
                        present.append(False)
                if any(present[i] and file_identity(paths[i]) != saved['files'][key] for i, key in [(1, 'common'), (2, 'git')]):
                    entry['reason'] = 'changed Git directory identity; retained'
                    continue
                if present[0]:
                    if file_identity(paths[0]) != saved['files']['worktree']:
                        entry['reason'] = 'recreated path; mutation will quarantine old generation'
                        continue
                    entry['reason'] = 'existing worktree'
                    if saved.get('missing_since') is not None and apply:
                        saved['missing_since'] = None
                        atomic(path / 'identity.json', saved)
                else:
                    snapshot, reg = registrations.get(str(path), (None, None))
                    if snapshot != saved:
                        reg = None
                    if not present[1]:
                        reg = False
                    if reg is None or reg or (not present[1] and present[2]):
                        entry['reason'] = 'registered missing worktree or inaccessible identity'
                        continue
                    missing = True
                    since = saved.get('missing_since')
                    entry['reason'] = 'confirmed deleted worktree'
                    if since is None:
                        since = now
                        if apply:
                            saved['missing_since'] = since
                            atomic(path / 'identity.json', saved)
            if missing:
                entry['deadline'] = since + WEEK
                if now >= since + WEEK:
                    entry['action'] = 'remove'
                    if apply:
                        remove_payload(path)
                continue
            # Pending evidence protects every referenced snapshot.
            referenced = set()
            for record in (path / 'evidence').glob('*.json'):
                content = read(record, {})
                if content.get('snapshot'):
                    referenced.add(content['snapshot'])
            for directory in ('snapshots', 'drafts'):
                for item in (path / directory).glob('*.json'):
                    value = read(item, {})
                    if item.stem not in referenced and now - value.get('last_use', value.get('created', item.stat().st_mtime)) >= MONTH:
                        result['entries'].append({'path': str(item), 'action': 'remove', 'reason': 'unreferenced for 30 days'})
                        if apply:
                            item.unlink()
        except (Invalid, OSError, KeyError, subprocess.TimeoutExpired) as error:
            entry['reason'] = 'unknown/inaccessible; retained (' + type(error).__name__ + ')'
    if apply:
        for repo in root.iterdir():
            if repo.is_dir() and not repo.is_symlink():
                worktrees = repo / 'worktrees'
                if worktrees.is_dir() and not any(worktrees.iterdir()):
                    worktrees.rmdir()
                if not any(repo.iterdir()):
                    repo.rmdir()
    return result


def clear(git, expected):
    current = State(git)
    if Path(expected).absolute() != current.path.absolute():
        raise Invalid('Clear requires the exact displayed current --state-directory path.')
    with lock(current.root):
        if current.path.exists():
            if not current.compatible() or not safe_payload(current.path):
                raise Invalid('Unknown/mismatched payload; inspect manually, refusing clear.')
            remove_payload(current.path)
    return {'cleared': str(current.path), 'durable_files_retained': True}


def remove_payload(path):
    """Keep identity until last, so a failed partial removal remains collectible."""
    saved = read(path / 'identity.json')
    for item in path.iterdir():
        if item.name == 'identity.json':
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    (path / 'identity.json').unlink()
    try:
        path.rmdir()
    except OSError:
        atomic(path / 'identity.json', saved)
        raise


def verify_location(git=None, root_hint=None):
    """Never use a checkout, Git dir or installed plugin as an XDG lock domain."""
    forbidden = [Path(__file__).resolve().parents[4]]
    if git is None:
        from .git import Git
        try:
            git = Git(root_hint or Path.cwd())
        except Invalid:
            pass  # state gc also works outside a checkout
    if git is not None:
        forbidden += [git.root, git.common, git.directory]
    for kind in ('state', 'cache'):
        resolved = xdg(kind).resolve()
        for base in forbidden:
            try:
                resolved.relative_to(base.resolve())
            except ValueError:
                continue
            raise Invalid('XDG_' + kind.upper() + '_HOME puts plugin runtime files inside a checkout, Git directory or installed plugin; restore the shared external XDG root for every coordinating process.')


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



def draft(git, name=None):
    """Create/touch an identity-bearing setup draft in this worktree's cache."""
    name = name or uuid.uuid4().hex
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', name):
        raise Invalid('Draft id must be a letter/digit followed by at most 63 letters, digits, dots, underscores or hyphens.')
    current = State(git)
    gc(apply=True, if_due=True)
    with lock(current.root):
        if not current.compatible():
            raise Invalid('Worktree identity changed; recover old state before creating drafts.')
        expected = identity(git, time.time())
        saved = read(current.cache / 'identity.json')
        if saved and any(saved.get(k) != expected[k] for k in ('version', 'worktree', 'common', 'git', 'files', 'volume')):
            raise Invalid('Cache worktree identity changed; inspect state gc and recover drafts explicitly.')
        if any(x.is_symlink() for x in (current.cache, current.cache.parent, current.cache.parent.parent, current.cache / 'drafts')):
            raise Invalid('Unsafe symlink in draft cache path.')
        path = current.cache / 'drafts' / name
        if path.is_symlink():
            raise Invalid('Unsafe draft symlink.')
        existing = read(path / 'identity.json')
        if path.exists() and not existing:
            raise Invalid('Unknown draft without identity; inspect it before reuse.')
        if existing and alive(existing.get('owner')) is not False:
            raise Invalid('Draft has an active or uncertain owner; retain it and use a fresh id.')
        atomic(current.cache / 'identity.json', saved or expected)
        atomic(path / 'identity.json', {'version': 1, 'created': existing.get('created', time.time()) if existing else time.time(), 'last_use': time.time(), 'owner': owner()})
    return {'draft_directory': str(path), 'cache_directory': str(current.cache)}


def collect_cache(root, apply, now, result, registrations):
    for path in sorted(xdg('cache').glob('*/worktrees/*')):
        entry = {'path': str(path), 'action': 'retain', 'reason': 'unknown cache identity'}
        result['entries'].append(entry)
        try:
            if any(x.is_symlink() for x in (path, path.parent, path.parent.parent)):
                continue
            saved = read(path / 'identity.json')
            if not saved or path_key(saved['common']) != path.parent.parent.name or path_key(saved['worktree']) != path.name or any(x.name not in {'identity.json', 'drafts', 'readiness'} or x.is_symlink() for x in path.iterdir()):
                continue
            if (path / 'readiness').exists() and (not (path / 'readiness').is_dir() or any(x.is_symlink() or (x.is_file() and x.suffix != '.json') for x in (path / 'readiness').rglob('*'))):
                entry['reason'] = 'unknown readiness cache files; retained'
                continue
            if containing_volume(Path(saved['worktree'])) != saved['volume']:
                entry['reason'] = 'volume unavailable or changed'
                continue
            missing = False
            try:
                actual = identity(SimpleNamespace(root=Path(saved['worktree']), common=Path(saved['common']), directory=Path(saved['git'])), now)
                if any(actual[k] != saved[k] for k in ('files', 'volume')):
                    entry['reason'] = 'recreated cache worktree identity'
                    continue
                entry['reason'] = 'existing worktree cache'
            except FileNotFoundError:
                if Path(saved['worktree']).exists():
                    continue
                snapshot, reg = registrations.get(str(path), (None, None))
                if snapshot != saved or reg is not False:
                    entry['reason'] = 'registered missing or inaccessible cache identity'
                    continue
                missing = True
            drafts = list((path / 'drafts').iterdir()) if (path / 'drafts').exists() else []
            protected = False
            for item in drafts:
                if item.is_symlink() or not item.is_dir():
                    protected = True
                    continue
                record = read(item / 'identity.json')
                if (not record or alive(record.get('owner')) is not False
                        or any(x.is_symlink() or (x.is_file() and x.suffix != '.md' and x != item / 'identity.json') for x in item.rglob('*'))):
                    protected = True
                    continue
                last_use = max([record.get('last_use', now), *(x.stat().st_mtime for x in item.rglob('*') if x.is_file())])
                if not missing and now - last_use >= MONTH:
                    result['entries'].append({'path': str(item), 'action': 'remove', 'reason': 'unreferenced draft without use for 30 days'})
                    if apply:
                        shutil.rmtree(item)
            if missing:
                since = saved.get('missing_since')
                since = now if since is None else since
                entry['deadline'] = since + WEEK
                if apply and saved.get('missing_since') is None:
                    atomic(path / 'identity.json', {**saved, 'missing_since': since})
                if not protected and now >= since + WEEK:
                    entry.update(action='remove', reason='confirmed deleted cache worktree')
                    if apply:
                        remove_payload(path)
            elif saved.get('missing_since') is not None and apply:
                atomic(path / 'identity.json', {**saved, 'missing_since': None})
        except (Invalid, OSError, KeyError):
            entry['reason'] = 'unknown/inaccessible cache identity; retained'
    if apply:
        for repo in xdg('cache').glob('*'):
            worktrees = repo / 'worktrees'
            if not repo.is_symlink() and worktrees.is_dir() and not any(worktrees.iterdir()):
                worktrees.rmdir()
                if not any(repo.iterdir()):
                    repo.rmdir()
