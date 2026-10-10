"""Command line interface for check.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DelegationError
from .ledger import OUTCOMES, TIERS, close_delegation, load_brief, open_delegation, pending, query, run_validator
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


def _brief(root: Path, args: argparse.Namespace) -> int:
    sys.stdout.flush()
    sys.stdout.buffer.write(load_brief(root, args.delegation))
    sys.stdout.buffer.flush()
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


def _run(root: Path, args: argparse.Namespace) -> int:
    overlay = load_overlay(root)
    command = overlay.validators.get(args.validator)
    if command is None:
        known = ", ".join(sorted(overlay.validators)) or "none"
        raise DelegationError(f'unknown validator "{args.validator}"; registered: {known}')
    result = run_validator(
        root, args.delegation, args.validator, command, overlay.extra_inputs, args.timeout
    )
    print(_result_line(result))
    if not result["ok"]:
        if result["output_tail"]:
            print(result["output_tail"])
        return 1
    return 0


def _result_line(result: dict) -> str:
    status = "PASS" if result["ok"] else "FAIL"
    code = "timeout" if result["timed_out"] else result["exit"]
    line = f"{result['id']} {status} exit={code} tree={result['tree'][:12]}"
    return line if result["stable"] else line + " unstable"


def _query(root: Path, args: argparse.Namespace) -> int:
    tree = args.tree
    if tree == "current":
        tree = tree_hash(root, load_overlay(root).extra_inputs)
    results = query(root, args.delegation, tree)
    if args.json:
        print(json.dumps({"tree": tree, "results": results}))
    else:
        for result in results:
            print(_result_line(result))
        if not results:
            print(_no_results(root, args.delegation, tree), file=sys.stderr)
    return 0


def _no_results(root: Path, delegation: str, tree: str | None) -> str:
    runs = query(root, delegation, None)
    if not runs:
        return f"no runs recorded for {delegation}"
    last = runs[-1]
    status = "PASS" if last["ok"] else "FAIL"
    latest = f"{last['id']} {status} at tree {last['tree'][:12]}"
    if not last["stable"]:
        latest += " unstable"
    return f"no stable results at tree {tree[:12]}; latest: {latest}"


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
    loader = commands.add_parser("brief", help="Print an open delegation's brief, checked against its hash")
    loader.add_argument("--delegation", required=True)
    closer = commands.add_parser("close", help="Record a delegation as finished")
    closer.add_argument("--delegation", required=True)
    closer.add_argument("--outcome", required=True, choices=OUTCOMES)
    closer.add_argument("--note")
    lister = commands.add_parser("pending", help="List open delegations")
    lister.add_argument("--json", action="store_true")
    runner = commands.add_parser("run", help="Run a registered validator and record the result")
    runner.add_argument("validator")
    runner.add_argument("--delegation", required=True)
    runner.add_argument("--timeout", type=float)
    asker = commands.add_parser("query", help="List recorded validator results")
    asker.add_argument("--delegation", required=True)
    asker.add_argument("--tree", help='A tree hash, or "current" to recompute it')
    asker.add_argument("--json", action="store_true")
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
        if args.command == "brief":
            return _brief(root, args)
        if args.command == "close":
            return _close(root, args)
        if args.command == "run":
            return _run(root, args)
        if args.command == "query":
            return _query(root, args)
        if args.command == "pending":
            return _pending(root, args)
    except DelegationError as error:
        print(f"check.py: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"check.py: cannot access {error.filename or 'a file'}: {error.strerror or error}", file=sys.stderr)
        return 2
    return 2
