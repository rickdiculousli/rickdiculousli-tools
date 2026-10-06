"""Module renderers: timeline, files, runs, claims, and figure dispatch."""

from html import escape
from itertools import groupby
from math import log1p
import posixpath

from .derive import EVIDENCE_LIMIT
from .markup import mark, plural

HUNK_LINES = 40
HUNKS_PER_FILE = 10
DIRECTORY_OPEN_LIMIT = 12
COLLAPSE_MIN = 3


def cap_lines(text: str, limit: int) -> tuple[str, str | None]:
    lines = text.split("\n")
    if len(lines) <= limit:
        return text, None
    return "\n".join(lines[:limit]), f"showing {limit} of {len(lines)} lines"


def item_attrs(item: dict, status: str, css: str = "") -> str:
    """id, classes, and data attributes shared by every item row."""
    classes = " ".join(c for c in (css, "asserted" if item["source"] == "asserted" else "") if c)
    attention = " data-attention" if item.get("attention") else ""
    return (f'id="{item["anchor"]}" class="{classes}" data-status="{status}" '
            f'data-source="{item["source"]}"{attention}')


def _open(flag: bool) -> str:
    return " open" if flag else ""


def _marker(text: str | None) -> str:
    return f'<p class="truncated">{escape(text)}</p>' if text else ""


def evidence_block(item: dict, open_: bool) -> str:
    evidence = item.get("evidence")
    if not evidence:
        return ""
    marker = None
    if len(evidence) > EVIDENCE_LIMIT:
        marker = f"truncated: {EVIDENCE_LIMIT:,} of {len(evidence):,} characters shown"
        evidence = evidence[:EVIDENCE_LIMIT]
    return (f'<details class="evidence"{_open(open_)}><summary>Evidence <span class="quoted">agent-quoted</span>'
            f'</summary><pre>{escape(evidence)}</pre>{_marker(marker)}</details>')


def backref_chips(anchor: str, derived) -> str:
    claims = derived.cited_by.get(anchor, [])
    if not claims:
        return ""
    chips = "".join(f'<a class="chip" href="#{claim}">claim {claim.split("-")[1]}</a>' for claim in claims)
    return f'<span class="chips backrefs" aria-label="cited by">cited by {chips}</span>'


def _heading(module: dict, default: str) -> str:
    return f'<h2>{escape(module.get("title", default))}</h2>'


def _section(module: dict, default: str, body: str) -> str:
    return (f'<section class="module module-{module["type"]}" id="{module["anchor"]}" data-type="{module["type"]}">'
            f'{_heading(module, default)}{body}</section>')


# Timeline ------------------------------------------------------------------

def _step_status(step: dict) -> str:
    if step["failure"] == "unresolved":
        return step["status"]
    if step["failure"] == "resolved":
        return "resolved"
    return step["status"]


def _step(step: dict, derived) -> str:
    status = _step_status(step)
    failing = step["failure"] == "unresolved"
    detail = ""
    if "detail" in step:
        detail = (f'<details class="detail"{_open(failing)}><summary>Detail</summary>'
                  f'<p>{escape(step["detail"])}</p></details>')
    return (f'<li {item_attrs(step, status, "step")} data-kind="{step["kind"]}">'
            f'{mark(status)}<span class="step-kind">{step["kind"]}</span>'
            f'<span class="step-label">{escape(step["label"])}</span>'
            f'{backref_chips(step["anchor"], derived)}{detail}{evidence_block(step, failing)}</li>')


def _collapsible(step: dict) -> bool:
    return step["status"] == "ok" and step["failure"] == "ok"


def _steps(steps: list[dict], derived) -> str:
    rows = []
    for (kind, quiet), run in groupby(steps, key=lambda s: (s["kind"], _collapsible(s))):
        run = list(run)
        inner = "".join(_step(s, derived) for s in run)
        if quiet and len(run) >= COLLAPSE_MIN:
            rows.append(f'<li class="step-group" data-status="ok"><details><summary>{mark("ok")}'
                        f'<span class="step-kind">{kind}</span> {kind} × {len(run)}</summary>'
                        f'<ol class="steps">{inner}</ol></details></li>')
        else:
            rows.append(inner)
    return f'<ol class="steps">{"".join(rows)}</ol>'


def _phase_summary(steps: list[dict]) -> str:
    failed = sum(1 for s in steps if s["failure"] == "unresolved")
    parts = [plural(len(steps), "step")]
    if failed:
        parts.append(f"{failed} failed")
    return " · ".join(parts)


def render_timeline(module: dict, derived) -> str:
    seen: set[str] = set()
    parts = []
    for anchor, group in groupby(module["steps"], key=lambda s: s.get("phase_anchor")):
        group = list(group)
        if anchor is None:
            parts.append(_steps(group, derived))
            continue
        failing = any(s["failure"] == "unresolved" for s in group)
        status = "fail" if failing else "ok"
        id_attr = "" if anchor in seen else f' id="{anchor}"'
        seen.add(anchor)
        parts.append(f'<details class="phase"{id_attr}{_open(failing)}><summary>{mark(status)}'
                     f'<span class="phase-name">{escape(group[0]["phase"])}</span>'
                     f'<span class="phase-counts">{_phase_summary(group)}</span></summary>'
                     f'{_steps(group, derived)}</details>')
    return _section(module, "Timeline", "".join(parts))


# Files ---------------------------------------------------------------------

CHANGE_ORDER = {"deleted": 0, "renamed": 1, "added": 2, "modified": 2}


def _hunks(item: dict) -> str:
    hunks = item.get("hunks") or []
    if not hunks:
        return ""
    blocks = []
    for hunk in hunks[:HUNKS_PER_FILE]:
        text, marker = cap_lines(hunk, HUNK_LINES)
        lines = "\n".join(f'<span class="{_diff_class(line)}">{escape(line)}</span>' for line in text.split("\n"))
        blocks.append(f'<pre class="diff"><code>{lines}</code></pre>{_marker(marker)}')
    hidden = len(hunks) - HUNKS_PER_FILE
    if hidden > 0:
        blocks.append(_marker(f"{plural(hidden, 'more hunk')} not shown"))
    return f'<details class="hunks"><summary>{plural(len(hunks), "hunk")}</summary>{"".join(blocks)}</details>'


def _diff_class(line: str) -> str:
    if line.startswith("+"):
        return "line-add"
    if line.startswith("-"):
        return "line-del"
    if line.startswith("@@"):
        return "line-hunk"
    return "line"


def _bar(item: dict, scale: float) -> str:
    if item.get("binary"):
        return '<span class="binary">binary</span>'
    total = item["added"] + item["removed"]
    width = 100.0 if scale == 0 else round(log1p(total) / scale * 100, 1)
    return (f'<span class="bar" style="width:{width}%">'
            f'<span class="bar-added" style="flex-grow:{item["added"]}"></span>'
            f'<span class="bar-removed" style="flex-grow:{item["removed"]}"></span></span>')


def _file(item: dict, scale: float, derived) -> str:
    status = "warn" if item["change"] == "deleted" else "ok"
    css = "file generated" if item.get("generated") else "file"
    renamed = (f'<span class="renamed-from">from {escape(item["from"])}</span>' if "from" in item else "")
    return (f'<li {item_attrs(item, status, css)} data-change="{item["change"]}">'
            f'<span class="change change-{item["change"]}">{item["change"]}</span>'
            f'<span class="path" title="{escape(item["path"])}">{escape(posixpath.basename(item["path"]))}</span>'
            f'{renamed}<span class="lines"><span class="added">+{item["added"]}</span> '
            f'<span class="removed">−{item["removed"]}</span></span>{_bar(item, scale)}'
            f'{backref_chips(item["anchor"], derived)}{_hunks(item)}{evidence_block(item, False)}</li>')


def render_files(module: dict, derived) -> str:
    files = module["files"]
    scale = log1p(max((f["added"] + f["removed"] for f in files), default=0))
    directories: dict[str, list[dict]] = {}
    for item in files:
        directories.setdefault(posixpath.dirname(item["path"]), []).append(item)
    groups = []
    for directory in sorted(directories):
        items = sorted(directories[directory], key=lambda f: CHANGE_ORDER[f["change"]])
        notable = any(f["change"] == "deleted" or f["anchor"] in derived.cited_by for f in items)
        open_ = len(items) <= DIRECTORY_OPEN_LIMIT or notable
        name = f"{directory}/" if directory else "./"
        dir_id = derived.ids.make("dir", directory or "root")
        totals = (f'{plural(len(items), "file")} · +{sum(f["added"] for f in items)} '
                  f'−{sum(f["removed"] for f in items)}')
        rows = "".join(_file(item, scale, derived) for item in items)
        groups.append(f'<details class="directory" id="{dir_id}"{_open(open_)}><summary>'
                      f'<span class="dir-name">{escape(name)}</span><span class="dir-totals">{totals}</span>'
                      f'</summary><ul class="files">{rows}</ul></details>')
    return _section(module, "Files changed", "".join(groups))


# Dispatch ------------------------------------------------------------------

def _placeholder(module: dict, derived) -> str:
    return _section(module, module["type"].capitalize(), "")


RENDERERS = {"timeline": render_timeline, "files": render_files}


def render_module(module: dict, derived) -> str:
    return RENDERERS.get(module["type"], _placeholder)(module, derived)
