"""Repository-wide work labels and the pattern log behind role and script proposals.

Both files live under the repository key, so every worktree and session of a
repository shares them. They describe what kinds of work recur; they are never
validator evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from . import DelegationError
from . import state

LABEL = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LABEL_MAX = 48
STATUSES = ("proposed", "approved", "declined")
RETENTION_DAYS = 180
DEFAULT_MIN = 3
LIST_LIMIT = 25
_FIELD = re.compile(r"^(Tier|Inputs|May write|Done when):\s*(.*)$", re.MULTILINE | re.IGNORECASE)
_PATHLIKE = re.compile(r"[\w.@-]*[/\\][\w./\\@*-]*|[\w@-]+\.[A-Za-z][\w]{0,7}\b")


def registry_path(paths: state.Paths) -> Path:
    return paths.repo / "kinds.json"


def log_path(paths: state.Paths) -> Path:
    return paths.repo / "patterns.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def check_label(label: str) -> list[str]:
    """Refuse malformed labels; return warnings for instance-shaped ones."""
    if not LABEL.match(label) or len(label) > LABEL_MAX:
        raise DelegationError(
            f'invalid kind "{label}": use lowercase words joined by hyphens, at most {LABEL_MAX} characters'
        )
    if any(part.isdigit() for part in label.split("-")):
        return [f'kind "{label}" ends in or contains a number; a kind names a task type one runbook could cover, not one instance']
    return []


def _empty() -> dict:
    return {"version": 1, "kinds": {}, "aliases": {}}


def load_registry(paths: state.Paths) -> dict:
    data = state.read(registry_path(paths), None)
    if data is None:
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("kinds"), dict) or not isinstance(data.get("aliases"), dict):
        raise DelegationError("Malformed kind registry; inspect " + str(registry_path(paths)))
    return data


def load_log(paths: state.Paths) -> list[dict]:
    return state.events_at(log_path(paths))


def resolve(registry: dict, label: str) -> str:
    """Follow merge and rename aliases to the label they now count under."""
    seen = set()
    while label in registry["aliases"] and label not in seen:
        seen.add(label)
        label = registry["aliases"][label]
    return label


def fingerprint(brief: bytes, tier: str, writes: bool) -> str:
    """A coarse shape of a brief: tier, writes, and where it reads, writes and checks.

    File names collapse to their directory and extension and digit runs to `#`,
    so the same task on another module or item shares a fingerprint.
    """
    fields = {name.lower(): value.strip() for name, value in _FIELD.findall(brief.decode("utf-8", errors="replace"))}

    def shapes(text: str) -> list[str]:
        found = set()
        for token in _PATHLIKE.findall(text):
            path = PurePosixPath(token.replace("\\", "/").strip("`'\"*.,;:()"))
            if not path.name:
                continue
            parent = re.sub(r"\d+", "#", path.parent.as_posix())
            found.add(f"{parent}/*{path.suffix}" if path.suffix else re.sub(r"\d+", "#", path.as_posix()))
        return sorted(found)

    done = fields.get("done when", "")
    validators = done.partition("validators:")[2] if "validators:" in done else ""
    shape = {
        "tier": tier,
        "writes": writes,
        "inputs": shapes(fields.get("inputs", "")),
        "may_write": shapes(fields.get("may write", "")),
        "validators": sorted(set(re.findall(r"[a-z0-9][a-z0-9_-]*", validators)) - {"none", "and", "or"}),
    }
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def similar(registry: dict, label: str) -> list[str]:
    """Existing labels a new one may duplicate: close spellings or shared words."""
    names = list(registry["kinds"]) + list(registry["aliases"])
    stems = {word[:4] for word in label.split("-") if len(word) >= 3}
    close = difflib.get_close_matches(label, names, n=5, cutoff=0.6)
    overlap = sorted((name for name in names if stems & {word[:4] for word in name.split("-") if len(word) >= 3}),
                     key=lambda name: -len(stems & {word[:4] for word in name.split("-")}))
    recent = sorted(registry["kinds"], key=lambda name: registry["kinds"][name].get("created", ""), reverse=True)
    ordered = []
    for name in close + overlap + recent:
        target = resolve(registry, name)
        if target not in ordered:
            ordered.append(target)
    return ordered[:5]


def choose(paths: state.Paths, kind: str | None, new_kind: str | None, role: str | None) -> tuple[str | None, str | None, list[str]]:
    """Validate a label before opening; return (label, description to register, warnings)."""
    registry = load_registry(paths)
    warnings: list[str] = []
    if role:
        if kind and resolve(registry, kind) != role:
            raise DelegationError(f'--role {role} records kind "{role}"; drop --kind or pass --kind {role}')
        if new_kind and role in registry["kinds"]:
            raise DelegationError(f'kind "{role}" is already registered; drop --new-kind')
        description = None if role in registry["kinds"] else (new_kind or f"work done by the {role} role")
        return role, description, warnings
    if new_kind is not None and not kind:
        raise DelegationError("--new-kind needs --kind <label>")
    if not kind:
        return None, None, warnings
    warnings += check_label(kind)
    target = resolve(registry, kind)
    if target != kind:
        warnings.append(f'kind "{kind}" now counts as "{target}"')
    if target in registry["kinds"]:
        if new_kind is not None:
            raise DelegationError(
                f'kind "{target}" is already registered ({registry["kinds"][target]["description"]}); drop --new-kind'
            )
        return target, None, warnings
    if new_kind is None or not new_kind.strip():
        hint = similar(registry, kind)
        listed = "; ".join(f'{name} ({registry["kinds"][name]["description"]})' for name in hint if name in registry["kinds"])
        raise DelegationError(
            f'unknown kind "{kind}". Reuse an existing kind if one fits'
            + (f": {listed}" if listed else " (check.py kinds lists them)")
            + f'. To register a new one, add --new-kind "<one-line description>".'
        )
    return kind, " ".join(new_kind.split()), warnings


def record_open(paths: state.Paths, event: dict, kind: str | None, description: str | None, brief: bytes) -> list[str]:
    """Register a new kind and log the open; the caller already opened the delegation."""
    warnings = []
    shape = fingerprint(brief, event["tier"], event["writes"])
    with state.mutex(paths.state_root):
        paths.check()
        registry = load_registry(paths)
        if kind and kind not in registry["kinds"]:
            registry["kinds"][kind] = {"description": description or kind, "created": _stamp(_now())}
            state.atomic(registry_path(paths), registry)
        elif description and kind and registry["kinds"][kind]["description"] != description:
            warnings.append(f'kind "{kind}" was registered meanwhile as: {registry["kinds"][kind]["description"]}')
        log = load_log(paths)
        matches: dict[str, int] = {}
        for item in log:
            if item.get("event") == "open" and item.get("fingerprint") == shape and item.get("kind"):
                label = resolve(registry, item["kind"])
                if label != kind:
                    matches[label] = matches.get(label, 0) + 1
        for label, count in sorted(matches.items(), key=lambda pair: -pair[1]):
            warnings.append(f'brief shape matches kind "{label}" ({count} earlier use{"s" if count != 1 else ""}); merge kinds if they are the same task')
        if not kind:
            warnings.append("no --kind given; this brief is counted by shape only")
        line = {"event": "open", "kind": kind, "fingerprint": shape, "tier": event["tier"],
                "writes": event["writes"], "role": event.get("role"), "delegation": event["delegation"],
                "worktree": paths.worktree_key, "brief_sha256": event["brief_sha256"],
                **({"lane": event["lane"]} if event.get("lane") else {}),
                "timestamp": _stamp(_now())}
        _append(paths, line)
    return warnings


def record_close(paths: state.Paths, delegation: str, outcome: str) -> None:
    with state.mutex(paths.state_root):
        paths.check()
        if any(item.get("event") == "open" and item.get("delegation") == delegation
               and item.get("worktree") == paths.worktree_key for item in load_log(paths)):
            _append(paths, {"event": "close", "delegation": delegation, "worktree": paths.worktree_key,
                            "outcome": outcome, "timestamp": _stamp(_now())})


def _append(paths: state.Paths, line: dict) -> None:
    target = log_path(paths)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.is_symlink():
        raise DelegationError("Unsafe pattern log symlink; inspect " + str(target))
    if not (paths.repo / "identity.json").exists():
        state.atomic(paths.repo / "identity.json", {**paths.repo_identity, "created": _now().timestamp()})
    with target.open("ab") as handle:
        handle.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
        handle.flush()


def _write(paths: state.Paths, registry: dict) -> None:
    state.atomic(registry_path(paths), registry)


def merge(paths: state.Paths, old: str, into: str) -> str:
    with state.mutex(paths.state_root):
        paths.check()
        registry = load_registry(paths)
        source, target = resolve(registry, old), resolve(registry, into)
        if source not in registry["kinds"]:
            raise DelegationError(f'unknown kind "{old}"')
        if target not in registry["kinds"]:
            raise DelegationError(f'unknown kind "{into}"')
        if source == target:
            raise DelegationError(f'"{old}" already counts as "{target}"')
        entry = registry["kinds"].pop(source)
        kept = registry["kinds"][target]
        if entry.get("archived"):
            archived = kept.setdefault("archived", {"count": 0, "first": entry["archived"]["first"]})
            archived["count"] += entry["archived"]["count"]
            archived["first"] = min(archived["first"], entry["archived"]["first"])
        if "status" in entry and "status" not in kept:
            kept["status"] = entry["status"]
        registry["aliases"][source] = target
        _write(paths, registry)
        return f'merged "{source}" into "{target}"; past and future uses of "{source}" count as "{target}"'


def rename(paths: state.Paths, old: str, new: str) -> str:
    check_label(new)
    with state.mutex(paths.state_root):
        paths.check()
        registry = load_registry(paths)
        source = resolve(registry, old)
        if source not in registry["kinds"]:
            raise DelegationError(f'unknown kind "{old}"')
        if new in registry["kinds"] or new in registry["aliases"]:
            raise DelegationError(f'kind "{new}" already exists; use kinds merge')
        registry["kinds"][new] = registry["kinds"].pop(source)
        registry["aliases"][source] = new
        _write(paths, registry)
        return f'renamed "{source}" to "{new}"'


def mark(paths: state.Paths, label: str, status: str, note: str | None) -> str:
    if status not in STATUSES:
        raise DelegationError(f"status must be one of {', '.join(STATUSES)}")
    with state.mutex(paths.state_root):
        paths.check()
        registry = load_registry(paths)
        target = resolve(registry, label)
        if target not in registry["kinds"]:
            raise DelegationError(f'unknown kind "{label}"')
        registry["kinds"][target]["status"] = {"status": status, "note": note, "at": _stamp(_now())}
        _write(paths, registry)
        return f'marked "{target}" {status}'


def summary(paths: state.Paths, roles: set[str], since_days: float | None = None, minimum: int = DEFAULT_MIN) -> dict:
    """Group the log by resolved kind, and unlabeled opens by fingerprint."""
    registry = load_registry(paths)
    log = load_log(paths)
    cutoff = _now() - timedelta(days=since_days) if since_days else None
    closes = {(item.get("worktree"), item.get("delegation")): item.get("outcome")
              for item in log if item.get("event") == "close"}
    groups: dict[str, dict] = {}
    shapes: dict[str, dict] = {}
    for item in log:
        if item.get("event") != "open" or (cutoff and _parse(item["timestamp"]) < cutoff):
            continue
        if item.get("kind"):
            name = resolve(registry, item["kind"])
            group = groups.setdefault(name, {"kind": name, "count": 0, "worktrees": set(), "days": set(),
                                             "outcomes": {}, "tiers": set(), "lanes": set(), "last": item["timestamp"]})
        else:
            group = shapes.setdefault(item["fingerprint"], {"fingerprint": item["fingerprint"], "count": 0,
                                                            "worktrees": set(), "days": set(), "outcomes": {},
                                                            "tiers": set(), "lanes": set(), "last": item["timestamp"]})
        group["count"] += 1
        if item.get("lane"):
            group["lanes"].add(item["lane"])
        group["worktrees"].add(item.get("worktree"))
        group["days"].add(item["timestamp"][:10])
        group["tiers"].add(item.get("tier"))
        group["last"] = max(group["last"], item["timestamp"])
        outcome = closes.get((item.get("worktree"), item.get("delegation")), "open")
        group["outcomes"][outcome] = group["outcomes"].get(outcome, 0) + 1
    kinds = []
    for name, entry in registry["kinds"].items():
        group = groups.get(name, {"kind": name, "count": 0, "worktrees": set(), "days": set(),
                                  "outcomes": {}, "tiers": set(), "lanes": set(), "last": None})
        archived = 0 if cutoff else entry.get("archived", {}).get("count", 0)
        status = entry.get("status", {}).get("status")
        role = name in roles
        total = group["count"] + archived
        kinds.append({
            "kind": name, "description": entry["description"], "count": total,
            "worktrees": len(group["worktrees"]), "days": len(group["days"]),
            "outcomes": group["outcomes"], "tiers": sorted(t for t in group["tiers"] if t),
            "lanes": sorted(group["lanes"]),
            "last": group["last"], "role": role, "status": status,
            "candidate": total >= minimum and not role and status not in ("approved", "declined"),
        })
    kinds.sort(key=lambda item: (item["last"] or "", item["count"]), reverse=True)
    unlabeled = [
        {"fingerprint": key, "count": group["count"], "worktrees": len(group["worktrees"]),
         "days": len(group["days"]), "outcomes": group["outcomes"], "tiers": sorted(t for t in group["tiers"] if t),
         "lanes": sorted(group["lanes"]), "last": group["last"]}
        for key, group in shapes.items() if group["count"] >= minimum
    ]
    unlabeled.sort(key=lambda item: item["count"], reverse=True)
    return {"version": 1, "minimum": minimum, "since_days": since_days, "kinds": kinds,
            "unlabeled": unlabeled, "aliases": dict(registry["aliases"])}


def prune(repo: Path, apply: bool, now: datetime | float | None = None) -> dict | None:
    """Fold opens older than the retention window into per-kind archived counts.

    The caller holds the root mutex. Unlabeled shapes past retention are dropped.
    """
    log = repo / "patterns.jsonl"
    if not log.is_file() or log.is_symlink():
        return None
    now = _now() if now is None else (datetime.fromtimestamp(now, timezone.utc) if isinstance(now, (int, float)) else now)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    events = state.events_at(log)
    old = [item for item in events if _parse(item["timestamp"]) < cutoff]
    if not old:
        return None
    entry = {"path": str(log), "action": "prune", "reason": f"pattern entries older than {RETENTION_DAYS} days",
             "entries": len(old)}
    if not apply:
        return entry
    registry_file = repo / "kinds.json"
    registry = state.read(registry_file, None) or _empty()
    for item in old:
        if item.get("event") == "open" and item.get("kind"):
            name = resolve(registry, item["kind"])
            if name in registry["kinds"]:
                archived = registry["kinds"][name].setdefault("archived", {"count": 0, "first": item["timestamp"]})
                archived["count"] += 1
                archived["first"] = min(archived["first"], item["timestamp"])
    if registry["kinds"]:
        state.atomic(registry_file, registry)
    kept = [item for item in events if _parse(item["timestamp"]) >= cutoff]
    temporary = log.with_name(".patterns.jsonl.write")
    temporary.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in kept), encoding="utf-8")
    temporary.replace(log)
    return entry
