"""Small HTML helpers shared by the page, module, and figure renderers."""

from html import escape

STATUS_TEXT = {"ok": "ok", "fail": "failed", "warn": "warning", "retry": "retried", "expected": "expected failure",
               "asserted": "asserted", "resolved": "resolved"}


def mark(status: str, label: str | None = None) -> str:
    """A status shape plus its text for screen readers."""
    text = STATUS_TEXT.get(status, status) if label is None else label
    return (f'<span class="mark mark-{status}" aria-hidden="true"></span>'
            f'<span class="sr-only">{escape(text)}</span>')


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"
