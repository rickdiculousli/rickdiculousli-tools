"""Command line interface for check.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DelegationError
from .ledger import close_delegation, open_delegation, pending, OUTCOMES, TIERS
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


def _open(root: Path, args: argparse.Namespace) -> int:
    overlay = load_overlay(root)
    event = open_delegation(
        root, args.delegation, args.tier, args.brief, args.writes,
        overlay.parallel_limit, overlay.extra_inputs,
    )
    role = "writer" if args.writes else "reader"
    print(f"opened {args.delegation} ({args.tier}, {role}) at {event['tree'][:12]}")
    return 0


def _close(root: Path, args: argparse.Namespace) -> int:
    close_delegation(root, args.delegation, args.outcome, args.note)
    print(f"closed {args.delegation} ({args.outcome})")
    return 0


def _pending(root: Path, args: argparse.Namespace) -> int:
    items = pending(root)
    if args.json:
        payload = [
            {
                "delegation": e["delegation"],
                "tier": e["tier"],
                "writes": e["writes"],
                "opened": e["timestamp"],
                "tree": e["tree"],
            }
            for e in items
        ]
        print(json.dumps({"pending": payload}))
    elif not items:
        print("No open delegations.")
    else:
        for e in items:
            role = "writer" if e["writes"] else "reader"
            print(f"{e['delegation']} {e['tier']} {role} opened {e['timestamp']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check.py", description=__doc__)
    parser.add_argument("--root", type=Path, help="Worktree root (default: the git root of the cwd)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lint", help="Report overlay problems")
    commands.add_parser("tree", help="Print the current tree hash")
    opener = commands.add_parser("open", help="Record a delegation as started")
    opener.add_argument("--delegation", required=True)
    opener.add_argument("--tier", required=True, choices=TIERS)
    opener.add_argument("--brief", required=True, type=Path)
    opener.add_argument("--writes", action="store_true", help="The delegation may edit the worktree")
    closer = commands.add_parser("close", help="Record a delegation as finished")
    closer.add_argument("--delegation", required=True)
    closer.add_argument("--outcome", required=True, choices=OUTCOMES)
    closer.add_argument("--note")
    lister = commands.add_parser("pending", help="List open delegations")
    lister.add_argument("--json", action="store_true")
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
        if args.command == "open":
            return _open(root, args)
        if args.command == "close":
            return _close(root, args)
        if args.command == "pending":
            return _pending(root, args)
    except DelegationError as error:
        print(f"check.py: {error}", file=sys.stderr)
        return 2
    return 2
