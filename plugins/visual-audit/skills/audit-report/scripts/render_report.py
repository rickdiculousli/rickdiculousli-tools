#!/usr/bin/env python3
"""Render an audit report JSON file into a self-contained HTML page."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_report import ReportError, render_report  # noqa: E402


def ensure_gitignore(directory: Path) -> None:
    """Keep reports out of version control without editing any user file."""
    if directory.name == ".audit":
        ignore = directory / ".gitignore"
        if not ignore.exists():
            directory.mkdir(parents=True, exist_ok=True)
            ignore.write_text("*\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Report JSON written by the agent")
    parser.add_argument("-o", "--output", type=Path, help="HTML path (default: next to the JSON)")
    args = parser.parse_args(argv)
    output = args.output or args.report.with_suffix(".html")
    try:
        for directory in dict.fromkeys((args.report.resolve().parent, output.resolve().parent)):
            ensure_gitignore(directory)
        data = json.loads(args.report.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        print(f"Cannot read {args.report}: {error}", file=sys.stderr)
        return 1
    try:
        html = render_report(data, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except ReportError as error:
        print(f"{args.report} has {len(error.errors)} problem(s); fix them and re-run:", file=sys.stderr)
        for message in error.errors:
            print(f"  {message}", file=sys.stderr)
        return 1
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html, encoding="utf-8")
    except OSError as error:
        print(f"Cannot write {output}: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
