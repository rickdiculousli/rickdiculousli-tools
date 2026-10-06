"""Render agent-written audit report JSON into one self-contained HTML page."""

from .derive import derive
from .page import render_page
from .schema import ReportError, load

__all__ = ["ReportError", "render_report"]


def render_report(data: object, rendered_at: str) -> str:
    """Validate report data and return the full HTML page; raises ReportError."""
    report = load(data)
    return render_page(report, derive(report), rendered_at)
