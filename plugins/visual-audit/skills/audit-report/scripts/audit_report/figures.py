"""SVG figures: the run strip and the figure module."""

from html import escape
from math import ceil

from .markup import plural

STRIP_LIMIT = 120
STRIP_PITCH = 6
STRIP_HEIGHT = 16
LISTED_FAILURES = 10


def _rank(step: dict) -> int:
    if step["failure"] == "unresolved":
        return 3 if step["status"] == "fail" else 2
    return 1 if step["status"] == "retry" else 0


MARK_CLASS = {3: "fail", 2: "warn", 1: "retry", 0: "ok"}


def _shape(rank: int, x: float) -> str:
    cx, cy = x + STRIP_PITCH / 2, STRIP_HEIGHT / 2
    if rank == 3:
        return f'<rect x="{x + 0.5}" y="{cy - 2.5}" width="5" height="5"/>'
    if rank in (1, 2):
        return f'<path d="M{cx} {cy - 3}L{cx + 3} {cy + 2.5}L{cx - 3} {cy + 2.5}Z"/>'
    return f'<circle cx="{cx}" cy="{cy}" r="2.5"/>'


def run_strip(steps: list[dict]) -> str:
    """One mark per step (bucketed above STRIP_LIMIT) plus a text summary."""
    if not steps:
        return ""
    size = ceil(len(steps) / STRIP_LIMIT)
    buckets = [steps[i:i + size] for i in range(0, len(steps), size)]
    marks = []
    for index, bucket in enumerate(buckets):
        worst = max(bucket, key=_rank)
        rank = _rank(worst)
        shape = _shape(rank, index * STRIP_PITCH)
        title = worst["label"] if size == 1 else f"steps {bucket[0]['n']}–{bucket[-1]['n']}"
        group = f'<g class="strip-mark mark-{MARK_CLASS[rank]}"'
        if rank >= 2:
            marks.append(f'<a href="#{worst["anchor"]}">{group}><title>{escape(title)}</title>{shape}</g></a>')
        else:
            marks.append(f'{group} aria-hidden="true">{shape}</g>')
    width = len(buckets) * STRIP_PITCH
    failed = [s["n"] for s in steps if _rank(s) == 3]
    warned = [s["n"] for s in steps if _rank(s) == 2]
    summary = f"{plural(len(steps), 'step')}: {len(failed)} failed"
    if failed:
        listed = ", ".join(str(n) for n in failed[:LISTED_FAILURES]) + (", …" if len(failed) > LISTED_FAILURES else "")
        summary += f" ({'step' if len(failed) == 1 else 'steps'} {listed})"
    if warned:
        summary += f", {plural(len(warned), 'warning')}"
    return (f'<div class="strip"><svg class="run-strip" viewBox="0 0 {width} {STRIP_HEIGHT}" '
            f'width="100%" height="{STRIP_HEIGHT}" preserveAspectRatio="xMinYMid meet" '
            f'aria-labelledby="strip-summary" role="img">{"".join(marks)}</svg>'
            f'<p class="strip-summary" id="strip-summary">{escape(summary)}</p></div>')
