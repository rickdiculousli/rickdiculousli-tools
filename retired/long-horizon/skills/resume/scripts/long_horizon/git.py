import os
from pathlib import Path
import subprocess
from .model import Invalid


class Git:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root = Path(self.run('rev-parse', '--show-toplevel').strip()).resolve()
        self.common = Path(self.run('rev-parse', '--path-format=absolute', '--git-common-dir').strip()).resolve()
        self.directory = Path(self.run('rev-parse', '--absolute-git-dir').strip()).resolve()

    def run(self, *args, binary=False, check=True, input=None):
        result = subprocess.run(['git', '-C', str(self.root), *args], input=input,
                                capture_output=True, timeout=30, text=not binary, encoding=None if binary else 'utf-8', errors=None if binary else 'surrogateescape', env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
        if check and result.returncode:
            raise Invalid('Git operation failed: ' + ' '.join(args[:2]) + '; check repository access and revision.')
        return result.stdout if result.returncode == 0 else (b'' if binary else '')

    def oid(self, ref='HEAD'):
        return self.run('rev-parse', '--verify', ref + '^{commit}', check=False).strip() or None

    def ancestor(self, older, newer='HEAD'):
        return subprocess.run(['git', '-C', str(self.root), 'merge-base', '--is-ancestor', older, newer],
                              capture_output=True, timeout=30).returncode == 0

    def read(self, rev, path):
        return self.run('show', f'{rev}:{path}', check=False)

    def branch(self):
        return self.run('symbolic-ref', '--short', '-q', 'HEAD', check=False).strip() or None

    def target(self):
        remote = self.run('symbolic-ref', '--short', '-q', 'refs/remotes/origin/HEAD', check=False).strip()
        if remote:
            return remote.split('/', 1)[1]
        names = [name for name in ('main', 'master') if self.oid('refs/heads/' + name)]
        return names[0] if len(names) == 1 else None

    def dirty(self):
        return self.run('status', '--porcelain=v1', '-z', binary=True).decode('utf-8', 'surrogateescape').split('\0')[:-1]


def confined(base, value):
    if not isinstance(value, str) or not value:
        raise Invalid('Managed paths must be nonempty strings.')
    base = Path(base).resolve()
    path = (base / value).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        raise Invalid('Managed path escapes checkout/draft: ' + value) from None
    return path


def path_key(path):
    import hashlib
    return hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode()).hexdigest()
