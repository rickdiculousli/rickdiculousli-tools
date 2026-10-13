"""Parse and lint the per-repo delegation overlay."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shlex

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
    "Locks",
    "Deps",
    "Rules",
    "Roles",
    "Rote scripts",
    "Host side effects",
    "Authoring",
    "Version",
)
AUTHORING_KEYS = ("roles", "scripts")
AUTHORING_VALUES = ("ask", "allowed")
DEFAULT_PARALLEL_LIMIT = 3
DEFAULT_RETURN_CAP = 400
DEFAULT_LEASE_TTL = 120.0
PROVIDER_KEY = "provider"
DEPS_COMMAND_KEY = "command"

_CANONICAL = {heading.lower(): heading for heading in KNOWN_HEADINGS}
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_VALIDATOR = re.compile(r"([^\s\[]+)\s*(?:\[([^\]]*)\])?\Z")
_REFERENCE = re.compile(r"validator:([A-Za-z0-9][A-Za-z0-9_-]*)")
_LEADING_INT = re.compile(r"(\d+)")
_PLATFORMS = re.compile(r"[a-z0-9]+(?:\|[a-z0-9]+)*\Z")
_VERSION = re.compile(r"\d+\.\d+\.\d+")


@dataclass(frozen=True)
class Validator:
    command: str
    cheap: bool = False
    timeout: float | None = None
    lock: str | None = None
    requires: tuple[str, ...] = ()
    needs_human: bool = False
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class Role:
    tier: str
    runbook: str
    max_uses: int | None = None
    max_context_bytes: int | None = None


@dataclass(frozen=True)
class Lock:
    slots: int = 1
    wait: float | None = None
    ttl: float = DEFAULT_LEASE_TTL


@dataclass(frozen=True)
class Overlay:
    path: Path
    exists: bool
    sections: dict[str, str]
    validators: dict[str, Validator]
    extra_inputs: tuple[str, ...]
    locks: dict[str, Lock]
    parallel_limit: int
    return_cap: int
    problems: tuple[str, ...]
    roles: dict[str, Role]
    warnings: tuple[str, ...] = ()
    authoring: dict[str, str] = field(default_factory=lambda: dict.fromkeys(AUTHORING_KEYS, "allowed"))
    version: str | None = None
    lock_provider: str | None = None
    rules: tuple[str, ...] = ()
    deps: dict[str, tuple[str, ...]] = field(default_factory=dict)
    deps_command: str | None = None


def overlay_path(root: Path) -> Path:
    return root / ".agents" / "delegation.md"


def _escapes(path: str) -> bool:
    if PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute() or PureWindowsPath(path).drive:
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


def _validator(number: int, command: str, attributes: str | None, problems: list[str]) -> Validator:
    """Parse `[cheap, timeout=<seconds>, lock=<name>, requires=<platform>|..., paths=<glob>|...]`; bad attributes are lint problems."""
    cheap, timeout, lock, requires, needs_human, paths = False, None, None, (), False, ()
    seen: set[str] = set()
    for item in filter(None, (part.strip() for part in (attributes or "").split(","))):
        key, eq, value = (part.strip() for part in item.partition("="))
        if key in seen:
            problems.append(f'line {number}: duplicate validator attribute "{key}"')
            continue
        seen.add(key)
        if item == "cheap":
            cheap = True
        elif item == "needs-human":
            needs_human = True
        elif key == "timeout" and eq:
            timeout = _positive(number, "timeout", value, problems)
        elif key == "lock" and eq:
            if _NAME.match(value):
                lock = value
            else:
                problems.append(f'line {number}: lock name must match [a-z0-9][a-z0-9_-]*, got "{value}"')
        elif key == "requires" and eq:
            if _PLATFORMS.match(value):
                requires = tuple(value.split("|"))
            else:
                problems.append(
                    f'line {number}: requires needs platform names like darwin or linux, separated by |, got "{value}"'
                )
        elif key == "paths" and eq:
            globs = tuple(x.strip() for x in value.split("|"))
            if all(globs) and not any(x.startswith("/") or ".." in x.split("/") for x in globs):
                paths = globs
            else:
                problems.append(f'line {number}: paths needs repository-relative globs separated by |, got "{value}"')
        else:
            problems.append(f'line {number}: unknown validator attribute "{item}"')
    return Validator(command, cheap, timeout, lock, requires, needs_human, paths)


def _roles(lines: list[tuple[int, str]], problems: list[str], warnings: list[str]) -> dict[str, Role]:
    roles = {}
    for number, text in lines:
        name, sep, attributes = (p.strip() for p in text.partition(":"))
        values = {}
        for item in attributes.split(","):
            key, eq, value = (p.strip() for p in item.partition("="))
            if not eq or key not in {"tier", "runbook", "max-uses", "max-context-bytes"} or key in values:
                problems.append(f'line {number}: invalid or duplicate role attribute "{item.strip()}"')
            values[key] = value
        tier, runbook = values.get("tier", ""), values.get("runbook", "")
        if not sep or not _NAME.fullmatch(name) or name in roles:
            problems.append(f'line {number}: invalid or duplicate role name "{name}"')
        if tier not in {"execute", "routine"}:
            problems.append(f'line {number}: role tier must be execute or routine')
        if runbook.startswith("state:"):
            problems.append(f'line {number}: outdated role runbook {runbook}; name a tracked source such as .agents/delegation/runbooks/{name}.md')
        elif not runbook or _escapes(runbook):
            problems.append(f'line {number}: role runbook needs a safe repository-relative source')
        elif not PurePosixPath(runbook.replace("\\", "/")).as_posix().startswith(".agents/delegation/"):
            warnings.append(f'line {number}: runbook source outside .agents/delegation/: {runbook}; general tool references are supported')
        caps = []
        for key in ("max-uses", "max-context-bytes"):
            value = values.get(key)
            try:
                cap = int(value) if value is not None and value.isascii() and value.isdigit() else None
            except ValueError:
                cap = None
            if value is not None and (cap is None or cap < 1):
                problems.append(f'line {number}: {key} needs a positive integer')
                caps.append(None)
            else:
                caps.append(cap)
        if all(cap is None for cap in caps):
            problems.append(f'line {number}: role needs max-uses and/or max-context-bytes')
        roles[name] = Role(tier, runbook, *caps)
    return roles


def _positive(number: int, key: str, value: str, problems: list[str]) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        parsed = None
    if parsed is None or not 0 < parsed < float("inf"):
        problems.append(f'line {number}: {key} needs a positive number, got "{value}"')
        return None
    return parsed


def _lock(number: int, attributes: str, problems: list[str]) -> Lock:
    """Parse `slots=<n>, wait=<seconds>, ttl=<seconds>`; all optional."""
    slots, wait, ttl = 1, None, DEFAULT_LEASE_TTL
    seen: set[str] = set()
    for item in filter(None, (part.strip() for part in attributes.split(","))):
        key, eq, value = (part.strip() for part in item.partition("="))
        if key in seen:
            problems.append(f'line {number}: duplicate lock attribute "{key}"')
            continue
        seen.add(key)
        if key == "slots" and eq:
            if value.isdigit() and int(value) >= 1:
                slots = int(value)
            else:
                problems.append(f'line {number}: slots needs a positive integer, got "{value}"')
        elif key == "wait" and eq:
            wait = _positive(number, "wait", value, problems)
        elif key == "ttl" and eq:
            ttl = _positive(number, "ttl", value, problems) or DEFAULT_LEASE_TTL
        else:
            problems.append(f'line {number}: unknown lock attribute "{item}"')
    return Lock(slots, wait, ttl)


def _quoted_command(number: int, key: str, value: str, problems: list[str]) -> str | None:
    """A command line, optionally in double quotes; it must split into at least one word."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    try:
        words = shlex.split(text)
    except ValueError as error:
        problems.append(f'line {number}: {key} command has unbalanced quoting: {error}')
        return None
    if not words:
        problems.append(f'line {number}: {key} needs a command, got "{value}"')
        return None
    return text


def _unit(number: int, value: str, problems: list[str]) -> str | None:
    """A repository-relative directory naming a dependency unit, without a trailing slash."""
    text = value.strip().strip("`").strip()
    if not text or _escapes(text):
        problems.append(f'line {number}: deps unit needs a repository-relative path, got "{value}"')
        return None
    return PurePosixPath(text.replace("\\", "/")).as_posix().rstrip("/") or None


def _deps(lines: list[tuple[int, str]], problems: list[str]) -> tuple[dict[str, tuple[str, ...]], str | None]:
    """Parse `<unit>: <dependent>, <dependent>` lines and at most one `command: <cmd>` line."""
    deps: dict[str, tuple[str, ...]] = {}
    command = None
    for number, text in lines:
        head, sep, body = (part.strip() for part in text.partition(":"))
        if not sep or not head:
            problems.append(f'line {number}: expected "<unit>: <dependent>, ..." or "command: <cmd>", got "{text}"')
            continue
        if head == DEPS_COMMAND_KEY:
            if command is not None:
                problems.append(f'line {number}: duplicate deps command')
            else:
                command = _quoted_command(number, "deps", body, problems)
            continue
        unit = _unit(number, head, problems)
        if unit is None:
            continue
        if unit in deps:
            problems.append(f'line {number}: duplicate deps unit "{unit}"')
            continue
        dependents = []
        for item in filter(None, (part.strip() for part in body.split(","))):
            dependent = _unit(number, item, problems)
            if dependent is not None and dependent != unit and dependent not in dependents:
                dependents.append(dependent)
        deps[unit] = tuple(dependents)
    return deps, command


def load_overlay(root: Path) -> Overlay:
    path = overlay_path(root)
    problems: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return Overlay(path, False, {}, {}, (), {}, DEFAULT_PARALLEL_LIMIT, DEFAULT_RETURN_CAP, (), {})

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

    validators: dict[str, Validator] = {}
    declared_at: dict[str, int] = {}
    for number, text in bodies.get("Validators", []):
        head, sep, command = text.partition(":")
        command = command.strip()
        match = _VALIDATOR.match(head.strip())
        if not sep or not command or not match or not _NAME.match(match.group(1)):
            problems.append(f'line {number}: expected "name: command", got "{text}"')
            continue
        name = match.group(1)
        if name in validators:
            problems.append(f'line {number}: duplicate validator "{name}"')
            continue
        validators[name] = _validator(number, command, match.group(2), problems)
        declared_at[name] = number

    extra: list[str] = []
    for number, text in bodies.get("Extra inputs", []):
        value = text.strip("`").strip()
        if not value:
            continue
        if _escapes(value.removeprefix("state:context/")) or (value.startswith("state:") and not value.startswith("state:context/")):
            problems.append(f"line {number}: extra input escapes the repository: {value}")
        else:
            extra.append(value)

    locks: dict[str, Lock] = {}
    lock_provider: str | None = None
    provider_seen = False
    for number, text in bodies.get("Locks", []):
        name, sep, attributes = (part.strip() for part in text.partition(":"))
        if sep and name == PROVIDER_KEY:
            if provider_seen:
                problems.append(f'line {number}: duplicate lock provider')
            else:
                provider_seen = True
                lock_provider = _quoted_command(number, "provider", attributes, problems)
        elif not sep or not _NAME.match(name):
            problems.append(f'line {number}: expected "name: slots=<n>, wait=<seconds>", got "{text}"')
        elif name in locks:
            problems.append(f'line {number}: duplicate lock "{name}"')
        else:
            locks[name] = _lock(number, attributes, problems)
    for name, validator in validators.items():
        if validator.lock and validator.lock not in locks:
            problems.append(f'line {declared_at[name]}: lock "{validator.lock}" is not declared under ## Locks')
        if validator.lock and validator.timeout is None:
            problems.append(f'line {declared_at[name]}: validator "{name}" holds a lock, so it needs a timeout')

    parallel = _read_int("Parallel limit", bodies.get("Parallel limit", []), DEFAULT_PARALLEL_LIMIT, problems)
    cap = _read_int("Return cap", bodies.get("Return cap", []), DEFAULT_RETURN_CAP, problems)

    for number, line in enumerate(raw.splitlines(), start=1):
        for match in _REFERENCE.finditer(line):
            if match.group(1) not in validators:
                problems.append(f'line {number}: unregistered validator "{match.group(1)}"')

    sections = {name: "\n".join(text for _, text in lines) for name, lines in bodies.items()}
    roles = _roles(bodies.get("Roles", []), problems, warnings)
    rules = tuple(text for _, text in bodies.get("Rules", []))
    deps, deps_command = _deps(bodies.get("Deps", []), problems)
    for number, text in bodies.get("Rote scripts", []):
        name, sep, body = (p.strip() for p in text.partition(":"))
        if not sep or not _NAME.fullmatch(name) or not body:
            problems.append(f'line {number}: rote script needs "name: command; what it replaces"')
        else:
            command = body.partition(';')[0].strip()
            try:
                words = shlex.split(command)
            except ValueError:
                warnings.append(f'line {number}: cannot inspect rote command quoting: {command}')
                continue
            if words:
                executable = words[0]
                if re.fullmatch(r'(?:python(?:\d+(?:\.\d+)*)?|sh|bash|zsh|node|ruby|perl)(?:\.exe)?', Path(executable).name):
                    # Interpreter options and ordinary command arguments are not script locations.
                    candidates = [word for word in words[1:] if not word.startswith('-')]
                    executable = '' if any(word in {'-c', '-m', '-e'} for word in words[1:]) else (candidates[0] if candidates else '')
                if Path(words[0]).name in {'uv', 'uv.exe'} and '--script' in words:
                    position = words.index('--script') + 1
                    executable = words[position] if position < len(words) else ''
                normalized = PurePosixPath(executable.replace('\\', '/')).as_posix()
                if '/' in executable or '\\' in executable or Path(executable).suffix in {'.py', '.sh', '.js', '.rb', '.pl', '.ps1', '.bat', '.cmd'}:
                    if not normalized.startswith('.agents/delegation/'):
                        warnings.append(f'line {number}: rote script outside .agents/delegation/: {executable}; general tools may stay in their own location')
    authoring = dict.fromkeys(AUTHORING_KEYS, "allowed")
    seen_authoring: set[str] = set()
    for number, text in bodies.get("Authoring", []):
        name, sep, value = (p.strip().lower() for p in text.partition(":"))
        if not sep or name not in AUTHORING_KEYS or value not in AUTHORING_VALUES:
            problems.append(f'line {number}: authoring needs "roles: ask|allowed" or "scripts: ask|allowed", got "{text}"')
        elif name in seen_authoring:
            problems.append(f'line {number}: duplicate authoring entry "{name}"')
        else:
            seen_authoring.add(name)
            authoring[name] = value
    version = None
    version_lines = bodies.get("Version", [])
    if version_lines:
        number, text = version_lines[0]
        if len(version_lines) > 1 or not _VERSION.fullmatch(text):
            problems.append(f'line {number}: Version needs one plugin version like 0.11.0, got "{text}"')
        else:
            version = text
    return Overlay(path, True, sections, validators, tuple(extra), locks, parallel, cap, tuple(problems), roles,
                   tuple(warnings), authoring, version, lock_provider, rules, deps, deps_command)
