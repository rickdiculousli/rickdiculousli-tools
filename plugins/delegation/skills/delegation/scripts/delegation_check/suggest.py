"""Map changed paths to the registered validators whose `paths=` scope they touch."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess

from . import DelegationError
from .overlay import Overlay, _escapes
from .tree import _git

DEPS_COMMAND_TIMEOUT_S = 120.0


def glob_regex(pattern: str) -> re.Pattern:
    """`**` crosses directories, `*` and `?` stay within one; a trailing `/` means everything below."""
    if pattern.endswith("/"):
        pattern += "**"
    out, index = "", 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out, index = out + "(?:.*/)?", index + 3
        elif pattern.startswith("**", index):
            out, index = out + ".*", index + 2
        elif pattern[index] == "*":
            out, index = out + "[^/]*", index + 1
        elif pattern[index] == "?":
            out, index = out + "[^/]", index + 1
        else:
            out, index = out + re.escape(pattern[index]), index + 1
    return re.compile(out + r"\Z")


def changed(root: Path, base: str | None) -> list[str]:
    """Paths differing from BASE (default HEAD) in the worktree, plus untracked, unignored files."""
    names = set(filter(None, _git(root, ["diff", "--name-only", "-z", "--no-renames", base or "HEAD"]).split("\0")))
    names |= set(filter(None, _git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).split("\0")))
    return sorted(names)


def _unit_of(path: str, units: list[str]) -> str | None:
    """The longest declared unit that contains `path`."""
    best = None
    for unit in units:
        if path == unit or path.startswith(unit + "/"):
            if best is None or len(unit) > len(best):
                best = unit
    return best


def _normal(unit: object) -> str | None:
    if not isinstance(unit, str) or not unit.strip() or _escapes(unit.strip()):
        return None
    value = PurePosixPath(unit.strip().replace("\\", "/")).as_posix().rstrip("/")
    return None if value in ("", ".") else value


def deps_map(root: Path, overlay: Overlay) -> tuple[dict[str, tuple[str, ...]], str | None]:
    """The `unit -> dependents` map and its source: `command` when the overlay names one, else `overlay`."""
    if overlay.deps_command:
        argv = shlex.split(overlay.deps_command)
        try:
            done = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  errors="replace", timeout=DEPS_COMMAND_TIMEOUT_S)
        except FileNotFoundError as error:
            raise DelegationError(f"deps command not found: {error.filename or argv[0]} (overlay ## Deps command)") from error
        except subprocess.TimeoutExpired as error:
            raise DelegationError(f"deps command gave no answer in {DEPS_COMMAND_TIMEOUT_S:g}s: {overlay.deps_command}") from error
        if done.returncode:
            tail = (done.stderr.strip() or done.stdout.strip()).splitlines()[-1:] or ["no output"]
            raise DelegationError(f"deps command failed (exit {done.returncode}): {tail[0]}")
        try:
            data = json.loads(done.stdout)
        except ValueError as error:
            raise DelegationError(f"deps command must print a JSON object of unit -> dependents: {error}") from error
        if not isinstance(data, dict) or not all(isinstance(v, list) for v in data.values()):
            raise DelegationError("deps command must print a JSON object whose values are lists of units")
        deps = {}
        for unit, dependents in data.items():
            key = _normal(unit)
            if key is None:
                raise DelegationError(f"deps command printed an unsafe unit: {unit!r}")
            cleaned = []
            for dependent in dependents:
                value = _normal(dependent)
                if value is None:
                    raise DelegationError(f"deps command printed an unsafe dependent of {key}: {dependent!r}")
                if value != key and value not in cleaned:
                    cleaned.append(value)
            deps[key] = tuple(cleaned)
        return deps, "command"
    if overlay.deps:
        return dict(overlay.deps), "overlay"
    return {}, None


def dependents_of(deps: dict[str, tuple[str, ...]], changed_paths: list[str]) -> list[dict]:
    """Changed units and their transitive dependents, in declaration order."""
    units = list(deps)
    touched = []
    for path in changed_paths:
        unit = _unit_of(path, units)
        if unit is not None and unit not in touched:
            touched.append(unit)
    out = []
    for unit in touched:
        closure, queue = [], list(deps.get(unit, ()))
        while queue:
            item = queue.pop(0)
            if item in closure or item == unit:
                continue
            closure.append(item)
            queue.extend(deps.get(item, ()))
        out.append({"unit": unit, "dependents": closure})
    return out


def _tracked_under(root: Path, unit: str) -> list[str]:
    return sorted(filter(None, _git(root, ["ls-files", "-z", "--", ":(literal)" + unit]).split("\0")))


def suggest(root: Path, overlay: Overlay, base: str | None = None, with_dependents: bool = False) -> dict:
    paths = changed(root, base)
    scoped, unscoped, idle = [], [], []
    dependents, source = [], None
    dependent_files: dict[str, list[str]] = {}
    if with_dependents:
        deps, source = deps_map(root, overlay)
        dependents = dependents_of(deps, paths)
        for item in dependents:
            for unit in item["dependents"]:
                dependent_files.setdefault(unit, _tracked_under(root, unit))
    for name, validator in overlay.validators.items():
        if not validator.paths:
            unscoped.append(name)
            continue
        patterns = [glob_regex(x) for x in validator.paths]
        matched = [path for path in paths if any(x.match(path) for x in patterns)]
        entry = {"validator": name, "paths": list(validator.paths), "matched": matched}
        if matched:
            if with_dependents:
                entry["via"] = "changed"
            scoped.append(entry)
            continue
        if with_dependents:
            hits = [unit for unit, files in dependent_files.items()
                    if any(x.match(f) for f in files for x in patterns)]
            if hits:
                entry.update(via="dependents", dependents=hits)
                scoped.append(entry)
                continue
        idle.append(entry)
    data = {"base": base or "HEAD", "changed": paths, "run": scoped, "unscoped": unscoped, "not_needed": idle}
    if with_dependents:
        data.update(deps_source=source, dependents=dependents)
    return data
