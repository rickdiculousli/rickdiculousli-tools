#!/usr/bin/env python3
"""Delegation evidence tooling: overlay lint, tree hash and the evidence ledger."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from delegation_check.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
