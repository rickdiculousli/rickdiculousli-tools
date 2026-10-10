"""Command line interface for check.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import DelegationError
from .overlay import load_overlay
from .tree import repo_root, tree_hash


def _lint(root: Path) -> int:
    overlay = load_overlay(root)
    if not overlay.exists:
        print(f"No overlay at {overlay.path}; base defaults apply.")
        return 0
    if overlay.problems:
        for problem in overlay.problems:
            print(problem)
        return 1
    print(f"Overlay OK: {overlay.path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check.py", description=__doc__)
    parser.add_argument("--root", type=Path, help="Worktree root (default: the git root of the cwd)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lint", help="Report overlay problems")
    commands.add_parser("tree", help="Print the current tree hash")
    return parser


def _resolve_root(given: Path | None) -> Path:
    return repo_root(given.resolve() if given else Path.cwd())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = _resolve_root(args.root)
        if args.command == "lint":
            return _lint(root)
        if args.command == "tree":
            print(tree_hash(root, load_overlay(root).extra_inputs))
            return 0
    except DelegationError as error:
        print(f"check.py: {error}", file=sys.stderr)
        return 2
    return 2
