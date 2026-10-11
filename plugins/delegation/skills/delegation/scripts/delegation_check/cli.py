"""Command line interface for check.py."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from . import DelegationError
from .brief import footer, task_line, tier_instructions
from . import locks
from .ledger import OUTCOMES, TIERS, close_delegation, execute, load_brief, open_delegation, pending, query, run_validator
from .overlay import Validator, load_overlay
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
    if overlay.problems:
        raise DelegationError('overlay lint problems: ' + '; '.join(overlay.problems))
    event = open_delegation(
        root, args.delegation, args.tier, args.brief, args.writes,
        overlay.parallel_limit, overlay.extra_inputs,
        args.continued_from, args.role, overlay.roles,
    )
    role = "writer" if args.writes else "reader"
    print(f"opened {args.delegation} ({args.tier}, {role}) at {event['tree'][:12]}")
    print(f"task: {task_line(root, args.delegation)}")
    print(f"task with instructions: {task_line(root, args.delegation, with_instructions=True)}")
    if args.continued_from:
        print(f"follow-up: SendMessage (Claude Code) / followup_task (Codex) to the agent mapped to {event['agent_session']}: {task_line(root, args.delegation)}")
    return 0


def _brief(root: Path, args: argparse.Namespace) -> int:
    event, data = load_brief(root, args.delegation)
    text = data.decode("utf-8", errors="replace").rstrip("\n")
    head = f"{tier_instructions(event['tier'])}\n\n" if args.with_instructions else ""
    if event.get('role'):
        text += '\n\nRole runbook: read ' + event['role_runbook']
    print(f"{head}{text}\n\n{footer(root, args.delegation, load_overlay(root))}", end="")
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
    validator = overlay.validators.get(args.validator)
    if validator is None:
        known = ", ".join(sorted(overlay.validators)) or "none"
        raise DelegationError(f'unknown validator "{args.validator}"; registered: {known}')
    result = run_validator(
        root, args.delegation, args.validator, validator, overlay.locks.get(validator.lock or ""),
        overlay.extra_inputs, args.timeout,
    )
    print(_result_line(result))
    if not result["ok"]:
        if result["output_tail"]:
            print(result["output_tail"])
        print(f"full output: {root.resolve() / result['log']}")
        return 1
    return 0


def _declared(root: Path, name: str):
    overlay = load_overlay(root)
    if name not in overlay.locks:
        known = ", ".join(sorted(overlay.locks)) or "none"
        raise DelegationError(f'unknown lock "{name}"; declared: {known}')
    return overlay.locks[name]


def _exec(root: Path, args: argparse.Namespace) -> int:
    command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not command:
        raise DelegationError("exec needs a command after --")
    lock = _declared(root, args.lock)
    if args.delegation:
        overlay = load_overlay(root)
        result = run_validator(root, args.delegation, None,
                               Validator(shlex.join(command), timeout=args.timeout, lock=args.lock),
                               lock, overlay.extra_inputs, args.timeout, argv=command)
        if result['output_tail']:
            print(result['output_tail'])
        print(_result_line(result))
        print(f"full output: {root.resolve() / result['log']}")
        return 124 if result['timed_out'] else (result['exit'] if result['exit'] is not None else 1)
    holder = {"delegation": args.delegation, "command": " ".join(command)}
    with locks.hold(root, args.lock, lock, holder):
        code, timed_out, _ = execute(root, command, args.timeout, capture=False)
    if timed_out:
        print(f"check.py: timed out after {args.timeout:g}s: {holder['command']}", file=sys.stderr)
        return 124
    return code if code is not None else 1


def _locks(root: Path, args: argparse.Namespace) -> int:
    overlay = load_overlay(root)
    if not overlay.locks:
        print("No locks declared.")
    for name, lock in overlay.locks.items():
        count = locks.slots(name, lock)
        source = f" ({locks.env_name(name)})" if count != lock.slots else ""
        wait = f", wait {lock.wait:g}s" if lock.wait is not None else ""
        print(f"{name}: {count} slot{'s' if count != 1 else ''}{source}{wait}")
        for line in locks.status(root, name, lock):
            print(f"  {line}")
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
    opener.add_argument("--role", help="Role declared in the overlay")
    opener.add_argument("--continue", dest="continued_from", help="Prior role delegation id; reuse its agent")
    loader = commands.add_parser("brief", help="Print an open delegation's brief, checked against its hash")
    loader.add_argument("--delegation", required=True)
    loader.add_argument("--with-instructions", action="store_true",
                        help="Print the tier's instructions first, for a subagent without a tier definition")
    closer = commands.add_parser("close", help="Record a delegation as finished")
    closer.add_argument("--delegation", required=True)
    closer.add_argument("--outcome", required=True, choices=OUTCOMES)
    closer.add_argument("--note")
    lister = commands.add_parser("pending", help="List open delegations")
    lister.add_argument("--json", action="store_true")
    runner = commands.add_parser("run", help="Run a registered validator and record the result")
    runner.add_argument("validator")
    runner.add_argument("--delegation", required=True)
    runner.add_argument("--timeout", type=float, help="Seconds; overrides the overlay's timeout")
    execer = commands.add_parser(
        "exec", help="Run a command under a lock; --delegation records caller evidence"
    )
    execer.add_argument("--lock", required=True)
    execer.add_argument("--timeout", required=True, type=float, help="Seconds; a lock is never held without one")
    execer.add_argument("--delegation", help="Open caller delegation for command evidence and lock holder")
    execer.add_argument("argv", nargs=argparse.REMAINDER, metavar="-- command", help="The command and its arguments")
    commands.add_parser("locks", help="List declared locks and who holds each slot")
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
        if args.command == "exec":
            return _exec(root, args)
        if args.command == "locks":
            return _locks(root, args)
    except DelegationError as error:
        print(f"check.py: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"check.py: cannot access {error.filename or 'a file'}: {error.strerror or error}", file=sys.stderr)
        return 2
    return 2
