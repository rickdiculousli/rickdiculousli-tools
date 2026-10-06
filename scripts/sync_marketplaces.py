#!/usr/bin/env python3
"""Generate host metadata from catalog.json and portable plugin manifests."""

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def read_object(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def require_name(value: object, label: str) -> None:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase kebab-case name")


def load_catalog(root: Path) -> tuple[dict, list[tuple[Path, dict]]]:
    root = root.resolve()
    catalog = read_object(root / "catalog.json")
    require_name(catalog.get("name"), "Marketplace name")
    owner = catalog.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner["name"].strip():
        raise ValueError("Catalog owner.name is required")
    paths = catalog.get("plugins")
    if not isinstance(paths, list) or not paths:
        raise ValueError("Catalog plugins must be a nonempty list of relative paths")
    plugins = []
    names = set()
    for value in paths:
        if not isinstance(value, str):
            raise ValueError("Plugin paths must be strings")
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 2 or path.parts[0] != "plugins":
            raise ValueError(f"Plugin path must be plugins/<name>: {value}")
        directory = root / path
        if directory.is_symlink() or not directory.resolve().is_relative_to(root):
            raise ValueError(f"Plugin path escapes the repository or is a symlink: {value}")
        manifest = read_object(directory / "plugin.json")
        name = manifest.get("name")
        require_name(name, f"Plugin name in {value}")
        if name != path.name:
            raise ValueError(f"Plugin name {name} must match directory {path.name}")
        if name in names:
            raise ValueError(f"Duplicate plugin name: {name}")
        names.add(name)
        for key in ("version", "description"):
            if not isinstance(manifest.get(key), str) or not manifest[key].strip():
                raise ValueError(f"Plugin {name} requires a nonempty {key}")
        if not any((directory / "skills").glob("*/SKILL.md")):
            raise ValueError(f"Plugin {name} must include at least one skills/<name>/SKILL.md")
        plugins.append((path, manifest))
    return catalog, plugins


def render_outputs(root: Path) -> dict[Path, str]:
    catalog, plugins = load_catalog(root)
    claude = {key: catalog[key] for key in ("name", "owner", "description") if key in catalog}
    codex = {"name": catalog["name"]}
    claude["plugins"] = []
    codex["plugins"] = []
    outputs = {}
    for path, portable in plugins:
        identity = {key: portable[key] for key in ("name", "version", "description", "author", "keywords") if key in portable}
        source = "./" + path.as_posix()
        claude["plugins"].append({**identity, "source": source})
        codex["plugins"].append({
            "name": portable["name"],
            "source": {"source": "local", "path": source},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        })
        outputs[path / ".claude-plugin/plugin.json"] = identity
        outputs[path / ".codex-plugin/plugin.json"] = {**identity, "skills": "./skills/"}
    outputs[Path(".claude-plugin/marketplace.json")] = claude
    outputs[Path(".agents/plugins/marketplace.json")] = codex
    return {root / path: json.dumps(data, indent=2, ensure_ascii=False) + "\n" for path, data in outputs.items()}


def sync(root: Path, check: bool = False) -> bool:
    outputs = render_outputs(root)  # Validate every input before touching outputs.
    matches = True
    for path, content in outputs.items():
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        matches = False
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return matches if check else True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="Fail on drift without writing files")
    args = parser.parse_args()
    try:
        if not sync(args.root, args.check):
            print("Generated metadata differs; run scripts/sync_marketplaces.py", file=sys.stderr)
            return 1
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print("Generated metadata is current." if args.check else "Generated host metadata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
