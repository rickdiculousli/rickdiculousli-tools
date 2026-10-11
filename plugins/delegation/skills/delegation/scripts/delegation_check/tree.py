"""Worktree tree hash computed through a temporary index."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
from typing import Sequence

from . import DelegationError


def _git(root: Path, args: Sequence[str], env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, env=env, capture_output=True, text=True
        )
    except OSError as error:
        raise DelegationError(f"cannot run git: {error}") from error
    if result.returncode != 0:
        raise DelegationError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def repo_root(start: Path) -> Path:
    try:
        output = _git(start, ["rev-parse", "--show-toplevel"])
    except (DelegationError, NotADirectoryError, FileNotFoundError):
        raise DelegationError(f"check.py needs a git worktree: {start}") from None
    return Path(output.strip())


def state_dir(root: Path) -> Path:
    directory = root / ".delegation"
    directory.mkdir(parents=True, exist_ok=True)
    ignore = directory / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return directory


def lock_dir(root: Path) -> Path:
    """Locks shared by every worktree of the repository.

    They live under /tmp (the system temp directory on Windows), keyed by
    git's common directory, because sandboxes
    (Codex's workspace mode) leave `.git` read-only but /tmp writable.
    """
    common = Path(_git(root, ["rev-parse", "--git-common-dir"]).strip())
    common = (common if common.is_absolute() else root / common).resolve()
    key = hashlib.sha256(os.path.normcase(str(common)).encode("utf-8")).hexdigest()[:16]
    temporary_root = Path(tempfile.gettempdir()) if os.name == "nt" else Path("/tmp")
    directory = temporary_root / f"delegation-locks-{key}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def git_tree(root: Path) -> str:
    root = root.resolve()
    directory = state_dir(root)
    suffix = f"{os.getpid()}-{secrets.token_hex(4)}"
    temp = directory / f"tmp-index-{suffix}"
    lock = temp.with_name(temp.name + ".lock")
    objects = directory / f"tmp-objects-{suffix}"
    try:
        real = Path(_git(root, ["rev-parse", "--git-path", "index"]).strip())
        if not real.is_absolute():
            real = root / real
        real_objects = Path(_git(root, ["rev-parse", "--git-path", "objects"]).strip())
        if not real_objects.is_absolute():
            real_objects = root / real_objects
        if real.is_file():
            shutil.copyfile(real, temp)
        objects.mkdir()
        env = dict(
            os.environ,
            GIT_INDEX_FILE=str(temp),
            GIT_OBJECT_DIRECTORY=str(objects),
            GIT_ALTERNATE_OBJECT_DIRECTORIES=str(real_objects),
        )
        quiet = ["-c", "core.splitIndex=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
        _git(root, [*quiet, "add", "-A"], env)
        return _git(root, [*quiet, "write-tree"], env).strip()
    finally:
        shutil.rmtree(objects, ignore_errors=True)
        for leftover in (temp, lock):
            try:
                leftover.unlink()
            except FileNotFoundError:
                pass


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_digest(root: Path, relative: str) -> str:
    target = root / relative
    if target.is_dir():
        lines = []
        for folder, _, names in os.walk(target):
            for name in names:
                path = Path(folder) / name
                lines.append(f"{path.relative_to(target).as_posix()}\t{_file_sha(path)}\n")
        return hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()
    if target.is_file():
        return _file_sha(target)
    return "missing"


def tree_hash(root: Path, extra_inputs: Sequence[str] = ()) -> str:
    tree = git_tree(root)
    if not extra_inputs:
        return tree
    parts = [f"git {tree}\n"]
    parts.extend(f"{path}\t{_input_digest(root, path)}\n" for path in sorted(extra_inputs))
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()
