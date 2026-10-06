"""Validate and normalize agent-written audit report JSON."""

import copy

OUTCOMES = ("pass", "partial", "blocked")
SOURCES = ("observed", "asserted")
STEP_KINDS = ("read", "search", "edit", "run", "think", "other")
STEP_STATUSES = ("ok", "fail", "warn", "retry")
CHANGES = ("added", "modified", "deleted", "renamed")
CLAIM_STATUSES = ("verified", "unverified", "refuted")
FIGURE_KINDS = ("bar", "tree", "flow", "custom")
FIGURE_STATUSES = ("ok", "fail", "warn", "retry")
CONTEXT_KEYS = ("repo", "branch", "base_commit", "head_commit", "session_id", "host", "started", "ended")
SVG_NAMESPACE = 'xmlns="http://www.w3.org/2000/svg"'


class ReportError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


# Checkers append "<path>: <message>" to errors and return whether the value is usable.
def _string(value, path, errors, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        errors.append(f"{path}: expected {'a non-empty ' if nonempty else 'a '}string, got {value!r}"[:200])
        return False
    return True


def _integer(value, path, errors, minimum=None):
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{path}: expected integer, got {value!r}"[:200])
        return False
    if minimum is not None and value < minimum:
        errors.append(f"{path}: must be at least {minimum}, got {value}")
        return False
    return True


def _number(value, path, errors):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        errors.append(f"{path}: expected a non-negative number, got {value!r}"[:200])
        return False
    return True


def _boolean(value, path, errors):
    if not isinstance(value, bool):
        errors.append(f"{path}: expected true or false, got {value!r}"[:200])
        return False
    return True


def _enum(value, path, errors, choices):
    if value not in choices:
        errors.append(f"{path}: expected one of {', '.join(choices)}, got {value!r}"[:200])
        return False
    return True


def _list(value, path, errors, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        errors.append(f"{path}: expected a {'non-empty ' if nonempty else ''}list")
        return False
    return True


def _object(value, path, errors):
    if not isinstance(value, dict):
        errors.append(f"{path}: expected an object")
        return False
    return True


def _keys(item, path, errors, allowed, required=()):
    for key in item:
        if key not in allowed:
            errors.append(f"{_join(path, key)}: unknown key")
    for key in required:
        if key not in item:
            errors.append(f"{_join(path, key)}: required")


def _join(path, key):
    return f"{path}.{key}" if path else key


SHARED_ITEM_KEYS = ("source", "evidence")


def _shared_item(item, path, errors):
    source = item.get("source", "asserted")
    _enum(source, _join(path, "source"), errors, SOURCES)
    if "evidence" in item:
        _string(item["evidence"], _join(path, "evidence"), errors, nonempty=False)
    if source == "observed" and not (isinstance(item.get("evidence"), str) and item["evidence"].strip()):
        errors.append(f"{_join(path, 'evidence')}: required (non-empty) when source is observed")


def _step(item, path, errors):
    _keys(item, path, errors, ("kind", "label", "status", "phase", "detail", "resolved") + SHARED_ITEM_KEYS,
          ("kind", "label"))
    _shared_item(item, path, errors)
    if "kind" in item:
        _enum(item["kind"], _join(path, "kind"), errors, STEP_KINDS)
    if "label" in item:
        _string(item["label"], _join(path, "label"), errors)
    status = item.get("status", "ok")
    _enum(status, _join(path, "status"), errors, STEP_STATUSES)
    for key in ("phase", "detail"):
        if key in item:
            _string(item[key], _join(path, key), errors)
    if "resolved" in item and _boolean(item["resolved"], _join(path, "resolved"), errors):
        if status not in ("fail", "warn"):
            errors.append(f"{_join(path, 'resolved')}: only allowed on fail or warn steps")


def _file(item, path, errors):
    _keys(item, path, errors, ("path", "change", "added", "removed", "from", "hunks", "generated", "binary")
          + SHARED_ITEM_KEYS, ("path", "change", "added", "removed"))
    _shared_item(item, path, errors)
    if "path" in item:
        _string(item["path"], _join(path, "path"), errors)
    if "change" in item:
        _enum(item["change"], _join(path, "change"), errors, CHANGES)
    for key in ("added", "removed"):
        if key in item:
            _integer(item[key], _join(path, key), errors, minimum=0)
    if "from" in item:
        _string(item["from"], _join(path, "from"), errors)
    elif item.get("change") == "renamed":
        errors.append(f"{_join(path, 'from')}: required when change is renamed")
    if "hunks" in item and _list(item["hunks"], _join(path, "hunks"), errors):
        for index, hunk in enumerate(item["hunks"]):
            _string(hunk, f"{_join(path, 'hunks')}[{index}]", errors, nonempty=False)
    for key in ("generated", "binary"):
        if key in item:
            _boolean(item[key], _join(path, key), errors)


def _suite(item, path, errors):
    if not _object(item, path, errors):
        return
    _keys(item, path, errors, ("name", "passed", "failed", "skipped"), ("name", "passed", "failed", "skipped"))
    if "name" in item:
        _string(item["name"], _join(path, "name"), errors)
    for key in ("passed", "failed", "skipped"):
        if key in item:
            _integer(item[key], _join(path, key), errors, minimum=0)


def _run(item, path, errors):
    _keys(item, path, errors, ("command", "exit", "expect_fail", "duration_ms", "suites", "excerpt", "resolved")
          + SHARED_ITEM_KEYS, ("command", "exit"))
    _shared_item(item, path, errors)
    if "command" in item:
        _string(item["command"], _join(path, "command"), errors)
    exit_ok = "exit" in item and _integer(item["exit"], _join(path, "exit"), errors)
    expect_fail = item.get("expect_fail", False)
    if "expect_fail" in item:
        _boolean(expect_fail, _join(path, "expect_fail"), errors)
    if "duration_ms" in item:
        _integer(item["duration_ms"], _join(path, "duration_ms"), errors, minimum=0)
    if "suites" in item and _list(item["suites"], _join(path, "suites"), errors):
        for index, suite in enumerate(item["suites"]):
            _suite(suite, f"{_join(path, 'suites')}[{index}]", errors)
    if "excerpt" in item:
        _string(item["excerpt"], _join(path, "excerpt"), errors, nonempty=False)
    if "resolved" in item and _boolean(item["resolved"], _join(path, "resolved"), errors) and exit_ok:
        failed = (item["exit"] != 0) != (expect_fail is True)
        if not failed:
            errors.append(f"{_join(path, 'resolved')}: only allowed on failed runs")


def _claim(item, path, errors):
    _keys(item, path, errors, ("claim", "status", "refs") + SHARED_ITEM_KEYS, ("claim", "status"))
    _shared_item(item, path, errors)
    if "claim" in item:
        _string(item["claim"], _join(path, "claim"), errors)
    if "status" in item and _enum(item["status"], _join(path, "status"), errors, CLAIM_STATUSES):
        if item["status"] == "verified" and item.get("source", "asserted") != "observed":
            errors.append(f"{_join(path, 'source')}: a verified claim must be observed")
    if "refs" in item and _object(item["refs"], _join(path, "refs"), errors):
        refs = item["refs"]
        _keys(refs, _join(path, "refs"), errors, ("steps", "runs", "files"))
        for key in ("steps", "runs"):
            if key in refs and _list(refs[key], _join(path, f"refs.{key}"), errors):
                for index, value in enumerate(refs[key]):
                    _integer(value, f"{_join(path, f'refs.{key}')}[{index}]", errors, minimum=1)
        if "files" in refs and _list(refs["files"], _join(path, "refs.files"), errors):
            for index, value in enumerate(refs["files"]):
                _string(value, f"{_join(path, 'refs.files')}[{index}]", errors)


def _status_label(item, path, errors):
    if "label" in item:
        _string(item["label"], _join(path, "label"), errors)
    if "status" in item:
        _enum(item["status"], _join(path, "status"), errors, FIGURE_STATUSES)


def _tree(node, path, errors, depth=0):
    if not _object(node, path, errors):
        return
    _keys(node, path, errors, ("label", "status", "children"), ("label",))
    _status_label(node, path, errors)
    if depth > 50:
        errors.append(f"{path}: tree is nested too deeply")
        return
    if "children" in node and _list(node["children"], _join(path, "children"), errors):
        for index, child in enumerate(node["children"]):
            _tree(child, f"{_join(path, 'children')}[{index}]", errors, depth + 1)


def _flow(flow, path, errors):
    if not _object(flow, path, errors):
        return
    _keys(flow, path, errors, ("nodes", "edges"), ("nodes", "edges"))
    ids = set()
    if "nodes" in flow and _list(flow["nodes"], _join(path, "nodes"), errors, nonempty=True):
        for index, node in enumerate(flow["nodes"]):
            node_path = f"{_join(path, 'nodes')}[{index}]"
            if not _object(node, node_path, errors):
                continue
            _keys(node, node_path, errors, ("id", "label", "status"), ("id", "label"))
            _status_label(node, node_path, errors)
            if "id" in node and _string(node["id"], _join(node_path, "id"), errors):
                if node["id"] in ids:
                    errors.append(f"{_join(node_path, 'id')}: duplicate node id {node['id']!r}")
                ids.add(node["id"])
    graph = {node_id: [] for node_id in ids}
    if "edges" in flow and _list(flow["edges"], _join(path, "edges"), errors):
        for index, edge in enumerate(flow["edges"]):
            edge_path = f"{_join(path, 'edges')}[{index}]"
            if not _object(edge, edge_path, errors):
                continue
            _keys(edge, edge_path, errors, ("from", "to", "label"), ("from", "to"))
            if "label" in edge:
                _string(edge["label"], _join(edge_path, "label"), errors)
            ends_ok = True
            for key in ("from", "to"):
                if key in edge and edge[key] not in ids:
                    errors.append(f"{_join(edge_path, key)}: unknown node {edge[key]!r}"[:200])
                    ends_ok = False
            if ends_ok and "from" in edge and "to" in edge:
                graph[edge["from"]].append(edge["to"])
    if _has_cycle(graph):
        errors.append(f"{_join(path, 'edges')}: flow contains a cycle")


def _has_cycle(graph: dict) -> bool:
    state = {}  # node -> 1 visiting, 2 done

    def visit(node):
        state[node] = 1
        for target in graph[node]:
            if state.get(target) == 1 or (target not in state and visit(target)):
                return True
        state[node] = 2
        return False

    return any(node not in state and visit(node) for node in sorted(graph))


FIGURE_DATA = {"bar": "bars", "tree": "tree", "flow": "flow", "custom": "svg"}


def _figure(module, path, errors):
    kind = module.get("kind")
    data_key = FIGURE_DATA.get(kind)
    _keys(module, path, errors, ("type", "title", "kind", "alt") + ((data_key,) if data_key else ()),
          ("kind", "alt") + ((data_key,) if data_key else ()))
    if "kind" in module:
        _enum(kind, _join(path, "kind"), errors, FIGURE_KINDS)
    if "alt" in module:
        _string(module["alt"], _join(path, "alt"), errors)
    if data_key not in module:
        return
    value = module[data_key]
    data_path = _join(path, data_key)
    if kind == "bar" and _list(value, data_path, errors, nonempty=True):
        for index, bar in enumerate(value):
            bar_path = f"{data_path}[{index}]"
            if _object(bar, bar_path, errors):
                _keys(bar, bar_path, errors, ("label", "value", "status"), ("label", "value"))
                _status_label(bar, bar_path, errors)
                if "value" in bar:
                    _number(bar["value"], _join(bar_path, "value"), errors)
    elif kind == "tree":
        _tree(value, data_path, errors)
    elif kind == "flow":
        _flow(value, data_path, errors)
    elif kind == "custom" and _string(value, data_path, errors):
        if SVG_NAMESPACE not in value:
            errors.append(f"{data_path}: custom SVG must declare {SVG_NAMESPACE}")


ITEM_MODULES = {"timeline": ("steps", _step), "files": ("files", _file), "runs": ("runs", _run),
                "claims": ("claims", _claim)}
MODULE_TYPES = tuple(ITEM_MODULES) + ("figure",)


def validate(data: object) -> list[str]:
    """Return every validation error as '<path>: <message>'."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["$: expected a JSON object at the top level"]
    _keys(data, "", errors, ("version", "title", "goal", "outcome", "blockers", "next_steps", "context", "modules"),
          ("version", "title", "goal", "outcome", "modules"))
    if "version" in data and data["version"] != 1:
        errors.append(f"version: expected 1, got {data['version']!r}"[:200])
    for key in ("title", "goal"):
        if key in data:
            _string(data[key], key, errors)
    outcome = data.get("outcome")
    if "outcome" in data:
        _enum(outcome, "outcome", errors, OUTCOMES)
    for key in ("blockers", "next_steps"):
        if key in data and _list(data[key], key, errors):
            for index, value in enumerate(data[key]):
                _string(value, f"{key}[{index}]", errors)
    if outcome in ("partial", "blocked") and not (isinstance(data.get("blockers"), list) and data["blockers"]):
        errors.append("blockers: required (non-empty) when outcome is not pass")
    if "context" in data and _object(data["context"], "context", errors):
        _keys(data["context"], "context", errors, CONTEXT_KEYS)
        for key in CONTEXT_KEYS:
            if key in data["context"]:
                _string(data["context"][key], f"context.{key}", errors)
    if "modules" in data and _list(data["modules"], "modules", errors):
        _validate_modules(data["modules"], errors)
    return errors


def _validate_modules(modules: list, errors: list[str]) -> None:
    counts = {"steps": 0, "runs": 0}
    file_paths: set[str] = set()
    claims = []
    for index, module in enumerate(modules):
        path = f"modules[{index}]"
        if not _object(module, path, errors):
            continue
        kind = module.get("type")
        if kind not in MODULE_TYPES:
            errors.append(f"{path}.type: expected one of {', '.join(MODULE_TYPES)}, got {kind!r}"[:200])
            continue
        if "title" in module:
            _string(module["title"], f"{path}.title", errors)
        if kind == "figure":
            _figure(module, path, errors)
            continue
        key, check = ITEM_MODULES[kind]
        _keys(module, path, errors, ("type", "title", key), (key,))
        if key not in module or not _list(module[key], f"{path}.{key}", errors):
            continue
        for item_index, item in enumerate(module[key]):
            item_path = f"{path}.{key}[{item_index}]"
            if not _object(item, item_path, errors):
                continue
            check(item, item_path, errors)
            if kind == "files" and isinstance(item.get("path"), str):
                if item["path"] in file_paths:
                    errors.append(f"{item_path}.path: duplicate file path {item['path']!r}"[:200])
                file_paths.add(item["path"])
            elif kind == "claims":
                claims.append((item, item_path))
        if key in counts:
            counts[key] += len(module[key])
    for claim, path in claims:
        refs = claim.get("refs")
        if not isinstance(refs, dict):
            continue
        for key in ("steps", "runs"):
            for index, value in enumerate(refs.get(key) or []):
                if isinstance(value, int) and not isinstance(value, bool) and not 1 <= value <= counts[key]:
                    errors.append(f"{path}.refs.{key}[{index}]: no {key[:-1]} {value} (report has {counts[key]})")
        for index, value in enumerate(refs.get("files") or []):
            if isinstance(value, str) and value not in file_paths:
                errors.append(f"{path}.refs.files[{index}]: no file {value!r} in a files module"[:200])


def normalize(data: dict) -> dict:
    """Return a deep copy of valid report data with defaults applied."""
    report = copy.deepcopy(data)
    report.setdefault("blockers", [])
    report.setdefault("next_steps", [])
    report.setdefault("context", {})
    for module in report["modules"]:
        if module["type"] in ITEM_MODULES:
            for item in module[ITEM_MODULES[module["type"]][0]]:
                item.setdefault("source", "asserted")
                if module["type"] == "timeline":
                    item.setdefault("status", "ok")
    return report


def load(data: object) -> dict:
    errors = validate(data)
    if errors:
        raise ReportError(errors)
    return normalize(data)
