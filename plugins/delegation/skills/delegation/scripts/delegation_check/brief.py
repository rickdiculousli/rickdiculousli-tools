"""The fixed parts of a brief, which `check.py brief` appends to the judge's text."""

from __future__ import annotations

import json
from pathlib import Path
import shlex

from . import DelegationError
from .overlay import Overlay

CHECK_PY = Path(__file__).resolve().parents[1] / "check.py"
INSTRUCTIONS = Path(__file__).resolve().parents[2] / "reference" / "tier-instructions.json"

RETURN_FORMAT = """Result: one paragraph.
Claims:
  - <claim> [checked: <ledger id>] | [cited: <refs>] | [asserted]
Fields: <the overlay's return fields>
Surprises: <anything unexpected>
Ruled out: <approaches tried and rejected, and why>"""


def command(root: Path, *args: str) -> str:
    """A check.py command line with absolute paths, safe to paste into a shell."""
    parts = ["python3", str(CHECK_PY), "--root", str(root.resolve()), *args]
    return " ".join(shlex.quote(part) for part in parts)


def task_line(root: Path, delegation: str, with_instructions: bool = False) -> str:
    flag = ["--with-instructions"] if with_instructions else []
    loader = command(root, "brief", *flag, "--delegation", delegation)
    return f"Run `{loader}` and follow the brief it prints exactly."


def tier_instructions(tier: str) -> str:
    """The generated instructions for a tier, which agent definitions otherwise carry."""
    try:
        tiers = json.loads(INSTRUCTIONS.read_text(encoding="utf-8"))["tiers"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DelegationError(f"cannot read tier instructions from {INSTRUCTIONS}: {error}") from error
    if not isinstance(tiers.get(tier), str):
        raise DelegationError(f"no instructions for tier {tier!r} in {INSTRUCTIONS}")
    return tiers[tier]


def footer(root: Path, delegation: str, overlay: Overlay) -> str:
    run = command(root, "run", "<validator>", "--delegation", delegation)
    fields = overlay.sections.get("Return fields", "").strip() or "none"
    cheap = ", ".join(name for name, v in overlay.validators.items() if v.cheap) or "none"
    locks = []
    if overlay.locks:
        names = ", ".join(f"{name} ({lock.slots} slot{'s' if lock.slots != 1 else ''})"
                          for name, lock in overlay.locks.items())
        exec_line = command(root, "exec", "--lock", "<lock>", "--timeout", "<seconds>",
                            "--delegation", delegation, "--", "<command>")
        locks = [
            f"Locks: {names}. Validators wait for theirs. Run any other command that needs",
            "one (a heavy build or test) through this, which waits for a free slot:",
            "",
            f"    {exec_line}",
            "",
        ]
    return "\n".join(
        [
            f"Delegation id: {delegation}",
            "",
            "Evidence: run validators only with this command, and cite the printed id as",
            f'[checked: {delegation}#<n>] only when it printed PASS and not "unstable".',
            "The overlay's timeouts apply; add `--timeout <seconds>` when the brief gives another:",
            "",
            f"    {run}",
            "",
            f"Order: run the cheap validators ({cheap}) while you work, and fix what they report",
            "before running anything slower. After your final edit, run the brief's validators",
            "cheapest first and stop at the first failure; fix it, then start that pass again.",
            "A failed run prints the path of its full output; search or slice it",
            "(grep, tail -n) rather than reading it whole, and don't rerun to see it.",
            "",
            *locks,
            "Return format:",
            "",
            "```",
            RETURN_FORMAT,
            "```",
            "",
            f"Return fields: {fields}",
            f"Return cap: {overlay.return_cap} words",
            "",
        ]
    )
