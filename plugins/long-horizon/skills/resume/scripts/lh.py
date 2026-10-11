#!/usr/bin/env python3
"""Portable long-horizon entry point (Python 3.10+)."""
import sys

# Inspection must also work from a read-only installed plugin without bytecode files.
sys.dont_write_bytecode = True
from long_horizon.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
