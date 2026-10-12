"""Shared helpers for delegation check.py tests."""

from pathlib import Path
import subprocess
import sys
import os
import tempfile

# macOS's /var is a symlink to /private/var, and the tools report resolved paths, so give every
# test resolved temporary directories rather than resolving them test by test.
tempfile.tempdir = os.path.realpath(tempfile.gettempdir())

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/delegation/skills/delegation/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=path, check=True, capture_output=True, text=True
    )


def configure_git(path: Path) -> None:
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "commit.gpgsign", "false")


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    configure_git(path)
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    git(path, "add", "a.txt")
    git(path, "commit", "-q", "-m", "init")
    return path


def write_overlay(root: Path, text: str) -> Path:
    target = root / ".agents" / "delegation.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))
    return target


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "check.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
    )


def isolate_xdg(test, base):
    import os
    from unittest.mock import patch
    patched = patch.dict(os.environ, XDG_STATE_HOME=str(base / 'xdg state'), XDG_CACHE_HOME=str(base / 'xdg cache'))
    patched.start()
    test.addCleanup(patched.stop)


def state_payload(root):
    from delegation_check.state import Paths, mutex
    paths = Paths(root)
    with mutex(paths.state_root):
        return paths.ensure()
