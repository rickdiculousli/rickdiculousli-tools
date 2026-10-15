"""Compare a checkout's delegation files with the installed plugin's current contract.

Only the current layout is known here; anything else is reported, never rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path

from .overlay import Overlay

POINTER = ".agents/delegation.md"
MATERIAL = ("runbooks", "scripts")


@dataclass(frozen=True)
class Item:
    kind: str  # missing, unexpected or outdated
    path: str
    message: str
    remedy: str
    severity: str = "warning"

    def json(self) -> dict:
        return asdict(self)


def installed_version(start: Path | None = None) -> str | None:
    """The nearest plugin manifest above this package names the installed version."""
    here = (start or Path(__file__)).resolve()
    for folder in here.parents:
        for name in ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            try:
                data = json.loads((folder / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("name") == "delegation" and isinstance(data.get("version"), str):
                return data["version"]
    return None


def _minor(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".")[:2])


def version_status(overlay: Overlay, installed: str | None) -> dict:
    """`current`, `mismatch` (older or missing tag), `newer`, or `unknown`/`none` when unchecked."""
    if not overlay.exists:
        status = "none"
    elif installed is None:
        status = "unknown"
    elif overlay.version is None or _minor(overlay.version) < _minor(installed):
        status = "mismatch"
    elif _minor(overlay.version) > _minor(installed):
        status = "newer"
    else:
        status = "current"
    return {"installed": installed, "tagged": overlay.version, "status": status}


def version_message(version: dict) -> str | None:
    tagged = version["tagged"] or "untagged"
    if version["status"] == "mismatch":
        return (f"version-mismatch: delegation plugin is {version['installed']}, repo overlay is {tagged}; "
                "offer to run delegation:migrate")
    if version["status"] == "newer":
        return (f"version-newer: repo overlay is {tagged} but the installed delegation plugin is "
                f"{version['installed']}; update the plugin instead of migrating")
    return None


def layout(root: Path, overlay: Overlay) -> list[Item]:
    items: list[Item] = []
    stray = root / ".delegation"
    if stray.exists() or stray.is_symlink():
        items.append(Item("unexpected", ".delegation", "Checkout-local delegation state is not part of the current layout.",
                          "Delete it after approval; plugin state lives under the XDG state root (check.py paths)."))
    ignore = root / ".gitignore"
    if ignore.is_file():
        for number, line in enumerate(ignore.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.strip().strip("/") == ".delegation":
                items.append(Item("unexpected", f".gitignore:{number}", "Ignore rule for the old .delegation/ directory.",
                                  "Remove the line after approval."))
    if not overlay.exists:
        return items
    text = overlay.path.read_text(encoding="utf-8", errors="replace")
    material = root / ".agents" / "delegation"
    if material.is_dir():
        for entry in sorted(material.iterdir()):
            relative = entry.relative_to(root).as_posix()
            if entry.name not in MATERIAL or not entry.is_dir():
                items.append(Item("unexpected", relative, "Only runbooks/ and scripts/ belong under .agents/delegation/.",
                                  "Move approved material into runbooks/ or scripts/, or delete it after approval."))
                continue
            for item in sorted(p for p in entry.rglob("*") if p.is_file()):
                name = item.relative_to(root).as_posix()
                if name not in text:
                    owner = "## Roles" if entry.name == "runbooks" else "## Rote scripts"
                    items.append(Item("unexpected", name, f"Not referenced by the overlay's {owner}.",
                                      f"Register it under {owner}, or delete it after approval."))
    for name, role in overlay.roles.items():
        if not role.runbook.startswith("state:") and not (root / role.runbook).is_file():
            items.append(Item("missing", role.runbook, f'Role "{name}" names a runbook that does not exist.',
                              "Create and git add the runbook, or remove the role.", "error"))
    agents = root / "AGENTS.md"
    if not agents.is_file() or POINTER not in agents.read_text(encoding="utf-8", errors="replace"):
        items.append(Item("missing", "AGENTS.md", "AGENTS.md has no delegation pointer.",
                          "Add: Delegation: follow the delegation skill; this repo's overlay is .agents/delegation.md."))
    claude = root / "CLAUDE.md"
    if claude.is_file():
        body = claude.read_text(encoding="utf-8", errors="replace")
        if "@AGENTS.md" not in body and POINTER not in body:
            items.append(Item("missing", "CLAUDE.md", "CLAUDE.md does not reach the delegation pointer.",
                              "Add @AGENTS.md or the pointer line to CLAUDE.md."))
    return items
