"""Worktree tree hash computed through a temporary index."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import shutil
import subprocess
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
    """Resolve payload location without creating it (use Paths.ensure for writes)."""
    from .state import paths_for
    return paths_for(root).path


def lock_dir(root: Path) -> Path:
    from .state import paths_for
    return paths_for(root).locks


def git_tree(root: Path) -> str:
    from .state import Paths, atomic, mutex, owner
    paths = Paths(root)
    root = paths.root
    # Inspect identity without opening a new payload for hashing.
    paths.check()
    attempt = paths.cache / 'hashing' / secrets.token_hex(16)
    with mutex(paths.state_root):
        paths.check()
        try:
            attempt.mkdir(parents=True, mode=0o700)
        except OSError as error:
            raise DelegationError('XDG cache root is not writable; configure a writable XDG_CACHE_HOME and allow it in the host sandbox: ' + str(paths.cache_root)) from error
        atomic(attempt / 'identity.json', owner())
    temp, objects = attempt / 'index', attempt / 'objects'
    try:
        real = Path(_git(root, ['rev-parse', '--git-path', 'index']).strip())
        if not real.is_absolute():
            real = root / real
        real_objects = Path(_git(root, ['rev-parse', '--git-path', 'objects']).strip())
        if not real_objects.is_absolute():
            real_objects = root / real_objects
        if real.is_file():
            # copy2 keeps the index's mtime, which git needs to spot racily clean entries: a
            # same-size edit made within the index's timestamp tick would otherwise be missed.
            shutil.copy2(real, temp)
        objects.mkdir()
        env = dict(os.environ, GIT_INDEX_FILE=str(temp), GIT_OBJECT_DIRECTORY=str(objects),
                   GIT_ALTERNATE_OBJECT_DIRECTORIES=str(real_objects))
        quiet = ['-c', 'core.splitIndex=false', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false']
        _git(root, [*quiet, 'add', '-A'], env)
        return _git(root, [*quiet, 'write-tree'], env).strip()
    finally:
        with mutex(paths.state_root):
            shutil.rmtree(attempt)


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_digest(root: Path, relative: str) -> str:
    from .state import context_path
    target = context_path(root, relative) if relative.startswith("state:") else root / relative
    if target.is_dir():
        lines = []
        for folder, directories, names in os.walk(target):
            if relative.startswith("state:") and any(not (Path(folder) / name).resolve().is_relative_to(target.resolve()) for name in [*directories, *names]):
                raise DelegationError("State input symlink escapes context: " + relative)
            for name in names:
                path = Path(folder) / name
                if relative.startswith("state:") and not path.resolve().is_relative_to(target.resolve()):
                    raise DelegationError("State input symlink escapes context: " + str(path))
                lines.append(f"{path.relative_to(target).as_posix()}\t{_file_sha(path)}\n")
        return hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()
    if target.is_file():
        return _file_sha(target)
    return "missing"


def tree_hash(root: Path, extra_inputs: Sequence[str] = ()) -> str:
    return with_extra_inputs(root, git_tree(root), extra_inputs)


def with_extra_inputs(root: Path, tree: str, extra_inputs: Sequence[str] = ()) -> str:
    """Combine a precomputed Git tree with current inputs without acquiring a mutex."""
    if not extra_inputs:
        return tree
    parts = [f"git {tree}\n"]
    parts.extend(f"{path}\t{_input_digest(root, path)}\n" for path in sorted(extra_inputs))
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()
