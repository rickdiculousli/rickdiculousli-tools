"""Map changed paths to the registered validators whose `paths=` scope they touch."""

from __future__ import annotations

import re
from pathlib import Path

from .overlay import Overlay
from .tree import _git


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


def suggest(root: Path, overlay: Overlay, base: str | None = None) -> dict:
    paths = changed(root, base)
    scoped, unscoped, idle = [], [], []
    for name, validator in overlay.validators.items():
        if not validator.paths:
            unscoped.append(name)
            continue
        patterns = [glob_regex(x) for x in validator.paths]
        matched = [path for path in paths if any(x.match(path) for x in patterns)]
        (scoped if matched else idle).append({"validator": name, "paths": list(validator.paths), "matched": matched})
    return {"base": base or "HEAD", "changed": paths, "run": scoped, "unscoped": unscoped, "not_needed": idle}
