"""Shared helpers for visual-audit renderer tests."""

from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/visual-audit/skills/audit-report"
SCRIPTS = SKILL / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def minimal_report(**overrides) -> dict:
    report = {"version": 1, "title": "T", "goal": "G", "outcome": "pass", "modules": []}
    report.update(overrides)
    return report


def render_html(report: dict) -> str:
    import audit_report

    return audit_report.render_report(report, rendered_at="2026-01-01T00:00:00Z")


class _DetailsFinder(HTMLParser):
    def __init__(self, element_id: str):
        super().__init__()
        self.element_id = element_id
        self.depth = 0  # Depth inside the target element; 0 means outside.
        self.result = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if self.result is not None:
            return
        if self.depth:
            if tag == "details":
                self.result = "open" in attributes
                return
            if tag not in VOID:
                self.depth += 1
        elif attributes.get("id") == self.element_id:
            if tag == "details":
                self.result = "open" in attributes
            elif tag not in VOID:
                self.depth = 1

    def handle_endtag(self, tag):
        if self.depth and tag not in VOID:
            self.depth -= 1


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def details_open(html: str, element_id: str):
    """Return whether the first <details> inside the element with this id is open."""
    finder = _DetailsFinder(element_id)
    finder.feed(html)
    return finder.result
