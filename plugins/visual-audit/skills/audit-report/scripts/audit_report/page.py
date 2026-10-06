"""Assemble the full HTML page."""

from html import escape
from pathlib import Path
from string import Template

from .modules import render_module

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def render_page(report: dict, derived, rendered_at: str) -> str:
    return Template(_template("page.html")).substitute(
        title=escape(report["title"]),
        css=_template("report.css"),
        js=_template("report.js"),
        band="",
        attention="",
        modules="\n".join(render_module(module, derived) for module in report["modules"]),
        rendered_at=escape(rendered_at),
    )
