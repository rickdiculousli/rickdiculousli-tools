"""Parse and lint the per-repo delegation overlay."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

KNOWN_HEADINGS: tuple[str, ...] = (
    "Bulk work",
    "Oracle",
    "Validators",
    "Single writer",
    "Findings",
    "Return fields",
    "Tier hints",
    "Parallel limit",
    "Return cap",
    "Extra inputs",
)
DEFAULT_PARALLEL_LIMIT = 3
DEFAULT_RETURN_CAP = 400

_CANONICAL = {heading.lower(): heading for heading in KNOWN_HEADINGS}
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_REFERENCE = re.compile(r"validator:([A-Za-z0-9][A-Za-z0-9_-]*)")
_LEADING_INT = re.compile(r"(\d+)")


@dataclass(frozen=True)
class Overlay:
    path: Path
    exists: bool
    sections: dict[str, str]
    validators: dict[str, str]
    extra_inputs: tuple[str, ...]
    parallel_limit: int
    return_cap: int
    problems: tuple[str, ...]


def overlay_path(root: Path) -> Path:
    return root / ".agents" / "delegation.md"


def _escapes(path: str) -> bool:
    if PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute():
        return True
    return ".." in PurePosixPath(path.replace("\\", "/")).parts


def _read_int(heading: str, lines: list[tuple[int, str]], default: int, problems: list[str]) -> int:
    if not lines:
        return default
    number, text = lines[0]
    match = _LEADING_INT.match(text)
    if not match or int(match.group(1)) < 1:
        problems.append(f'line {number}: {heading} needs a positive integer, got "{text}"')
        return default
    return int(match.group(1))


def load_overlay(root: Path) -> Overlay:
    path = overlay_path(root)
    problems: list[str] = []
    if not path.is_file():
        return Overlay(path, False, {}, {}, (), DEFAULT_PARALLEL_LIMIT, DEFAULT_RETURN_CAP, ())

    raw = path.read_bytes().decode("utf-8", errors="replace")
    bodies: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    for number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        heading = re.match(r"##(?!#)\s*(.*)\Z", stripped)
        if heading:
            title = heading.group(1).strip()
            canonical = _CANONICAL.get(title.lower())
            if canonical is None:
                problems.append(f'line {number}: unknown heading "{title}"')
                current = None
            elif canonical in bodies:
                problems.append(f'line {number}: duplicate heading "{canonical}"')
                current = canonical
            else:
                bodies[canonical] = []
                current = canonical
            continue
        if stripped.startswith("#") or not stripped or current is None:
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if stripped:
            bodies[current].append((number, stripped))

    validators: dict[str, str] = {}
    for number, text in bodies.get("Validators", []):
        name, sep, command = text.partition(":")
        name, command = name.strip(), command.strip()
        if not sep or not command or not _NAME.match(name):
            problems.append(f'line {number}: expected "name: command", got "{text}"')
        elif name in validators:
            problems.append(f'line {number}: duplicate validator "{name}"')
        else:
            validators[name] = command

    extra: list[str] = []
    for number, text in bodies.get("Extra inputs", []):
        value = text.strip("`").strip()
        if not value:
            continue
        if _escapes(value):
            problems.append(f"line {number}: extra input escapes the repository: {value}")
        else:
            extra.append(value)

    parallel = _read_int("Parallel limit", bodies.get("Parallel limit", []), DEFAULT_PARALLEL_LIMIT, problems)
    cap = _read_int("Return cap", bodies.get("Return cap", []), DEFAULT_RETURN_CAP, problems)

    for number, line in enumerate(raw.splitlines(), start=1):
        for match in _REFERENCE.finditer(line):
            if match.group(1) not in validators:
                problems.append(f'line {number}: unregistered validator "{match.group(1)}"')

    sections = {name: "\n".join(text for _, text in lines) for name, lines in bodies.items()}
    return Overlay(path, True, sections, validators, tuple(extra), parallel, cap, tuple(problems))
