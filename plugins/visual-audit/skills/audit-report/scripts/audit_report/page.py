"""Assemble the full HTML page."""

from html import escape
from pathlib import Path
from string import Template

from .figures import LEGEND, run_strip
from .markup import mark, plural
from .modules import render_module

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def render_page(report: dict, derived, rendered_at: str) -> str:
    return Template(_template("page.html")).substitute(
        title=escape(report["title"]),
        css=_template("report.css"),
        js=_template("report.js"),
        band=render_band(report, derived, rendered_at),
        main_attrs=" data-all-asserted" if derived.all_asserted else "",
        attention=render_attention(derived),
        modules="\n".join(render_module(module, derived) for module in report["modules"]),
        rendered_at=escape(rendered_at),
    )


OUTCOME_MARK = {"pass": "ok", "partial": "warn", "blocked": "fail"}
OUTCOME_TEXT = {"pass": "Pass", "partial": "Partial", "blocked": "Blocked"}
ATTENTION_KIND = {"run": "failed run", "step": "failed step", "warning": "warning", "refuted": "refuted claim",
                  "unverified": "unverified claim", "deleted": "deleted file", "truncated": "evidence truncated"}
CONTEXT_LABELS = (("repo", "repo"), ("branch", "branch"), ("base_commit", "base"), ("head_commit", "head"),
                  ("session_id", "session"), ("host", "host"), ("started", "started"), ("ended", "ended"))


def _first_module(report: dict, kind: str) -> str:
    return next(m["anchor"] for m in report["modules"] if m["type"] == kind)


def _list(title: str, items: list[str], css: str) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f'<section class="{css}"><h2>{title}</h2><ul>{rows}</ul></section>'


def _counts(report: dict, derived) -> str:
    rows = []
    if derived.commands is None:
        rows.append(("Commands", '<span class="not-reported">not reported</span>'))
    else:
        runs = derived.runs
        parts = [f'<a class="count" href="#{_first_module(report, "runs")}">{plural(derived.commands, "command")}</a>']
        failed = plural(runs["unresolved"], "failed run")
        parts.append(f'<a class="count" href="#attention">{failed}</a>' if runs["unresolved"] else failed)
        parts += [f"{runs[key]} {key}" for key in ("resolved", "expected") if runs[key]]
        rows.append(("Commands", " · ".join(parts)))
    if derived.all_steps:
        unresolved = [s for s in derived.all_steps if s["failure"] == "unresolved"]
        failed = sum(1 for s in unresolved if s["status"] == "fail")
        text = plural(failed, "failed step")
        parts = [f'<a class="count" href="#attention">{text}</a>' if failed else text]
        warned = len(unresolved) - failed
        if warned:
            parts.append(f'<a class="count" href="#attention">{plural(warned, "warning")}</a>')
        if derived.steps["resolved"]:
            parts.append(f"{derived.steps['resolved']} resolved")
        rows.append(("Steps", " · ".join(parts)))
    if derived.files is None:
        rows.append(("Files", '<span class="not-reported">not reported</span>'))
    else:
        rows.append(("Files", f'<a class="count" href="#{_first_module(report, "files")}">'
                              f'{plural(derived.files, "file")}</a> · '
                              f'<span class="added">+{derived.lines_added}</span> '
                              f'<span class="removed">−{derived.lines_removed}</span>'))
    if derived.countable:
        rows.append(("Provenance", f"{derived.asserted} of {derived.countable} asserted"))
    return '<dl class="counts">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows) + "</dl>"


def render_band(report: dict, derived, rendered_at: str) -> str:
    outcome = report["outcome"]
    parts = [f'<header class="band band-{outcome}">',
             f'<p class="outcome">{mark(OUTCOME_MARK[outcome], "")}{OUTCOME_TEXT[outcome]}</p>',
             f'<h1>{escape(report["title"])}</h1>', f'<p class="goal">{escape(report["goal"])}</p>']
    if derived.contradictions:
        count = plural(len(derived.contradictions), "item")
        parts.append(f'<p class="contradiction">{mark("fail", "")}<span>Pass, but '
                     f'<a href="#attention">contradicted by {count}</a></span></p>')
    parts.append(_list("Blockers", report["blockers"], "blockers"))
    parts.append(_list("Next steps", report["next_steps"], "next-steps"))
    parts.append(_counts(report, derived))
    if derived.all_asserted:
        parts.append('<p class="banner-asserted">Everything in this report is the agent\'s own account: '
                     'no item is backed by observed evidence.</p>')
    parts.append(run_strip(derived.all_steps) or f'<div class="strip">{LEGEND}</div>')
    context = "".join(f"<div><dt>{label}</dt><dd>{escape(report['context'][key])}</dd></div>"
                      for key, label in CONTEXT_LABELS if key in report["context"])
    parts.append(f'<dl class="context">{context}<div><dt>rendered</dt><dd>{escape(rendered_at)}</dd></div></dl>')
    parts.append("</header>")
    return "\n".join(part for part in parts if part)


def render_attention(derived) -> str:
    if not derived.attention:
        body = '<p class="all-clear">Nothing needs attention</p>'
    else:
        rows = "".join(f'<li data-kind="{item.kind}"><a href="#{item.anchor}">{escape(item.label)}</a> '
                       f'<span class="kind">{ATTENTION_KIND[item.kind]}</span></li>' for item in derived.attention)
        body = f"<ol>{rows}</ol>"
    return f'<section id="attention" class="attention"><h2>Needs attention</h2>{body}</section>'
