"""SVG figures: the run strip and the figure module."""

import base64
from html import escape
from math import ceil

from .markup import plural

STRIP_LIMIT = 120
STRIP_WIDTH = 720  # Preferred total width; marks grow up to STRIP_MAX_PITCH for short sessions.
STRIP_MIN_PITCH = 6
STRIP_MAX_PITCH = 16
STRIP_HEIGHT = 16
LISTED_FAILURES = 10


def _rank(step: dict) -> int:
    if step["failure"] == "unresolved":
        return 3 if step["status"] == "fail" else 2
    return 1 if step["status"] == "retry" else 0


MARK_CLASS = {3: "fail", 2: "warn", 1: "retry", 0: "ok"}


def _shape(rank: int, x: float, pitch: float) -> str:
    size = min(pitch - 1, 10)
    half = size / 2
    cx, cy = round(x + pitch / 2, 2), STRIP_HEIGHT / 2
    if rank == 3:
        return f'<rect x="{cx - half:g}" y="{cy - half:g}" width="{size:g}" height="{size:g}"/>'
    if rank in (1, 2):
        return f'<path d="M{cx:g} {cy - half:g}L{cx + half:g} {cy + half:g}L{cx - half:g} {cy + half:g}Z"/>'
    return f'<circle cx="{cx:g}" cy="{cy:g}" r="{half * 0.8:g}"/>'


LEGEND = ('<details class="legend"><summary>Key</summary><ul>'
          '<li><span class="mark mark-ok" aria-hidden="true"></span>ok, passed, verified, or resolved</li>'
          '<li><span class="mark mark-fail" aria-hidden="true"></span>failed or refuted</li>'
          '<li><span class="mark mark-warn" aria-hidden="true"></span>warning or retried</li>'
          '<li><span class="mark mark-expected" aria-hidden="true"></span>expected failure</li>'
          '<li><span class="legend-asserted">dashed outline</span>agent-asserted, not backed by observed evidence</li>'
          '</ul></details>')


def run_strip(steps: list[dict]) -> str:
    """One mark per step (bucketed above STRIP_LIMIT) plus a text summary."""
    if not steps:
        return ""
    size = ceil(len(steps) / STRIP_LIMIT)
    buckets = [steps[i:i + size] for i in range(0, len(steps), size)]
    pitch = round(max(STRIP_MIN_PITCH, min(STRIP_MAX_PITCH, STRIP_WIDTH / len(buckets))), 2)
    marks = []
    for index, bucket in enumerate(buckets):
        worst = max(bucket, key=_rank)
        rank = _rank(worst)
        shape = _shape(rank, index * pitch, pitch)
        span = f"Step {bucket[0]['n']}" if size == 1 else f"Steps {bucket[0]['n']}–{bucket[-1]['n']}"
        group = f'<g class="strip-mark mark-{MARK_CLASS[rank]}"'
        if rank >= 2:
            label = f"{span}: {'failed' if rank == 3 else 'warning'}"
            hit = (f'<rect class="strip-hit" x="{index * pitch + pitch / 2 - 6:g}" y="0" '
                   f'width="12" height="{STRIP_HEIGHT}"/>')
            marks.append(f'<a href="#{worst["anchor"]}" aria-label="{escape(label)}">{hit}{group}>'
                         f'<title>{escape(label)}: {escape(worst["label"])}</title>{shape}</g></a>')
        else:
            marks.append(f'{group} aria-hidden="true">{shape}</g>')
    width = round(len(buckets) * pitch, 2)
    failed = [s["n"] for s in steps if _rank(s) == 3]
    warned = [s["n"] for s in steps if _rank(s) == 2]
    summary = f"{plural(len(steps), 'step')}: {len(failed)} failed"
    if failed:
        listed = ", ".join(str(n) for n in failed[:LISTED_FAILURES]) + (", …" if len(failed) > LISTED_FAILURES else "")
        summary += f" ({'step' if len(failed) == 1 else 'steps'} {listed})"
    if warned:
        summary += f", {plural(len(warned), 'warning')}"
    return (f'<div class="strip"><svg class="run-strip" viewBox="0 0 {width:g} {STRIP_HEIGHT}" '
            f'width="{width:g}" height="{STRIP_HEIGHT}" preserveAspectRatio="xMinYMid meet" '
            f'aria-labelledby="strip-summary" role="group">{"".join(marks)}</svg>'
            f'<p class="strip-summary" id="strip-summary">{escape(summary)}</p>{LEGEND}</div>')


# Figure module -------------------------------------------------------------

ROW = 24
LABEL_WIDTH = 180
BAR_WIDTH = 380
INDENT = 20
NODE_WIDTH = 150
NODE_HEIGHT = 34
LAYER_GAP = 70
NODE_GAP = 22
NODE_CHARS = 20


def _status(item: dict) -> str:
    return item.get("status", "ok")


def _short(label: str, limit: int) -> str:
    return label if len(label) <= limit else label[:limit - 1] + "…"


def _svg(width: float, height: float, body: str, alt: str) -> str:
    return (f'<svg class="figure-svg" viewBox="0 0 {width:g} {height:g}" width="{width:g}" role="img" '
            f'aria-label="{escape(alt)}" xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def _bars(module: dict) -> tuple[str, str]:
    bars = module["bars"]
    top = max((b["value"] for b in bars), default=0) or 1
    rows, cells = [], []
    for index, bar in enumerate(bars):
        y = index * ROW
        width = max(bar["value"] / top * BAR_WIDTH, 1)
        rows.append(f'<g class="fig-bar status-{_status(bar)}">'
                    f'<text class="fig-label" x="{LABEL_WIDTH - 8}" y="{y + 16}" text-anchor="end">'
                    f'{escape(_short(bar["label"], 28))}</text>'
                    f'<rect x="{LABEL_WIDTH}" y="{y + 5}" width="{width:.1f}" height="{ROW - 10}" rx="2"/>'
                    f'<text class="fig-value" x="{LABEL_WIDTH + width + 6:.1f}" y="{y + 16}">{bar["value"]:g}</text></g>')
        cells.append(f"<tr><td>{escape(bar['label'])}</td><td>{bar['value']:g}</td>"
                     f"<td>{_status(bar)}</td></tr>")
    svg = _svg(LABEL_WIDTH + BAR_WIDTH + 60, len(bars) * ROW, "".join(rows), module["alt"])
    table = f"<table><tr><th>label</th><th>value</th><th>status</th></tr>{''.join(cells)}</table>"
    return svg, table


def _tree(module: dict) -> tuple[str, str]:
    rows: list[str] = []
    widest = [0]

    def walk(node: dict, depth: int, parent_y: float | None) -> str:
        y = len(rows) * ROW + ROW / 2
        x = depth * INDENT + 8
        widest[0] = max(widest[0], x)
        elbow = (f'<path class="tree-link" d="M{x - INDENT} {parent_y}V{y}H{x - 5}"/>'
                 if parent_y is not None else "")
        rows.append(f'<g class="tree-node status-{_status(node)}">{elbow}<circle cx="{x}" cy="{y}" r="4.5"/>'
                    f'<text x="{x + 12}" y="{y + 4.5}">{escape(node["label"])}</text></g>')
        children = "".join(walk(child, depth + 1, y) for child in node.get("children", []))
        children = f"<ul>{children}</ul>" if children else ""
        return f"<li>{escape(node['label'])} ({_status(node)}){children}</li>"

    listing = f"<ul>{walk(module['tree'], 0, None)}</ul>"
    return _svg(widest[0] + 320, len(rows) * ROW, "".join(rows), module["alt"]), listing


def layer_flow(nodes: list[dict], edges: list[dict]) -> list[list[str]]:
    """Longest-path layering; nodes keep input order within a layer."""
    order = [node["id"] for node in nodes]
    predecessors: dict[str, list[str]] = {node_id: [] for node_id in order}
    for edge in edges:
        predecessors[edge["to"]].append(edge["from"])
    layer: dict[str, int] = {}

    def depth(node_id: str) -> int:
        if node_id not in layer:
            layer[node_id] = 1 + max((depth(p) for p in predecessors[node_id]), default=-1)
        return layer[node_id]

    for node_id in order:
        depth(node_id)
    layers: list[list[str]] = [[] for _ in range(max(layer.values()) + 1)]
    for node_id in order:
        layers[layer[node_id]].append(node_id)
    return layers


def _flow(module: dict) -> tuple[str, str]:
    flow = module["flow"]
    by_id = {node["id"]: node for node in flow["nodes"]}
    position = {}
    layers = layer_flow(flow["nodes"], flow["edges"])
    for column, ids in enumerate(layers):
        for row, node_id in enumerate(ids):
            position[node_id] = (column * (NODE_WIDTH + LAYER_GAP), row * (NODE_HEIGHT + NODE_GAP))
    parts, listing = [], []
    arrow = f"arrow-{module['anchor']}"
    for edge in flow["edges"]:
        (x1, y1), (x2, y2) = position[edge["from"]], position[edge["to"]]
        x1, y1, y2 = x1 + NODE_WIDTH, y1 + NODE_HEIGHT / 2, y2 + NODE_HEIGHT / 2
        middle = x1 + LAYER_GAP / 2
        label = ""
        if "label" in edge:
            label = (f'<text class="flow-edge-label" x="{x1 + 6}" y="{y1 - 6}">'
                     f'{escape(_short(edge["label"], 14))}</text>')
        parts.append(f'<path class="flow-edge" d="M{x1} {y1}H{middle}V{y2}H{x2 - 6}" '
                     f'marker-end="url(#{arrow})"/>{label}')
        names = f"{by_id[edge['from']]['label']} → {by_id[edge['to']]['label']}"
        listing.append(f"<li>{escape(names)}{escape(' (' + edge['label'] + ')') if 'label' in edge else ''}</li>")
    for node_id, (x, y) in position.items():
        node = by_id[node_id]
        parts.append(f'<g class="flow-node status-{_status(node)}"><title>{escape(node["label"])}</title>'
                     f'<rect x="{x}" y="{y}" width="{NODE_WIDTH}" height="{NODE_HEIGHT}" rx="4"/>'
                     f'<text x="{x + 10}" y="{y + 21}">{escape(_short(node["label"], NODE_CHARS))}</text></g>')
    defs = (f'<defs><marker id="{arrow}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" '
            'orient="auto"><path d="M0 0L8 4L0 8Z" class="flow-arrow"/></marker></defs>')
    width = len(layers) * (NODE_WIDTH + LAYER_GAP) - LAYER_GAP
    height = max(len(ids) for ids in layers) * (NODE_HEIGHT + NODE_GAP) - NODE_GAP
    nodes_listing = "".join(f"<li>{escape(n['label'])} ({_status(n)})</li>" for n in flow["nodes"])
    return (_svg(width, height, defs + "".join(parts), module["alt"]),
            f"<ul>{nodes_listing}</ul><ul>{''.join(listing)}</ul>")


def render_figure(module: dict) -> str:
    if module["kind"] == "custom":
        data = base64.b64encode(module["svg"].encode("utf-8")).decode("ascii")
        return (f'<figure class="figure figure-custom"><img src="data:image/svg+xml;base64,{data}" '
                f'alt="{escape(module["alt"])}"></figure>')
    svg, hidden = {"bar": _bars, "tree": _tree, "flow": _flow}[module["kind"]](module)
    return (f'<figure class="figure figure-{module["kind"]}"><div class="figure-frame">{svg}</div>'
            f'<div class="sr-only">{hidden}</div></figure>')
