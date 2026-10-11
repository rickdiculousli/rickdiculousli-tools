"""One permanent root lock protects identity, atomic writes and collection."""
from contextlib import contextmanager
import errno
import json
import os
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
    raw = os.environ.get('XDG_' + kind.upper() + '_HOME', '')
    base = Path(raw) if raw and Path(raw).is_absolute() else Path.home() / ('.local/state' if kind == 'state' else '.cache')
    return base / 'rickdiculousli-tools' / 'long-horizon'


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
    stat = Path(path).stat()
    return {'device': stat.st_dev, 'inode': stat.st_ino,
            'birth': getattr(stat, 'st_birthtime', None)}


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
    if not root.exists():
        if not apply:
            return result
    if not apply:
        return collect(root, False, now, result)
    with lock(root):
        last = read(root / 'gc.json', {}).get('last_sweep', 0)
        if if_due and now - last < WEEK:
            result['due'] = False
            return result
        collect(root, True, now, result)
        atomic(root / 'gc.json', {'version': 1, 'last_sweep': now})
    return result


def collect(root, apply, now, result):
    for path in sorted(root.glob('*/worktrees/*')):
        if any(x.is_symlink() for x in (path, path.parent, path.parent.parent)) or not path.is_dir():
            continue
        entry = {'path': str(path), 'action': 'retain', 'reason': 'unknown identity'}
        result['entries'].append(entry)
        try:
            saved = read(path / 'identity.json')
            if not saved or not safe_payload(path):
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
                if present[0]:
                    if file_identity(paths[0]) != saved['files']['worktree']:
                        entry['reason'] = 'recreated path; mutation will quarantine old generation'
                        continue
                    entry['reason'] = 'existing worktree'
                    if saved.get('missing_since') is not None and apply:
                        saved['missing_since'] = None
                        atomic(path / 'identity.json', saved)
                else:
                    reg = registered(saved['common'], saved['worktree']) if present[1] else False
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
                    if item.stem not in referenced and now - value.get('last_use', value.get('created', now)) >= MONTH:
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
