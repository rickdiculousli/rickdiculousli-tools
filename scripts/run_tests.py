#!/usr/bin/env python3
"""Run the unittest suite in parallel processes, a few tests per process.

Most tests spend their time waiting on git and CLI subprocesses, and each test
works in its own temporary directory, so tests run independently. The suite is
split into chunks of at most --chunk tests from one module; each chunk runs as
`python3 -m unittest <test ids>` with tests/ first on sys.path, as discovery
would. No test uses setUpClass or setUpModule, which chunking would repeat.

    python3 scripts/run_tests.py                    # whole suite
    python3 scripts/run_tests.py 'test_delegation_*.py' -j 4 --chunk 8
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fnmatch
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
RAN = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


def chunks(patterns, size):
    """Group discovered test ids by module, then split each module into chunks of at most size."""
    sys.path.insert(0, str(TESTS))
    modules = {}
    for test in test_ids(unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(TESTS))):
        module = test.split(".")[0]
        if test.startswith("unittest.loader."):   # a module that failed to import: run it to report why
            module = test.rsplit(".", 1)[-1]
            test = module
        if any(fnmatch.fnmatch(module + ".py", pattern) for pattern in patterns):
            modules.setdefault(module, []).append(test)
    return [(module, tests[i:i + size]) for module, tests in modules.items() for i in range(0, len(tests), size)]


def run(module, tests):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(TESTS), os.environ.get("PYTHONPATH")])))
    result = subprocess.run([sys.executable, "-m", "unittest", *tests], cwd=ROOT, env=env,
                            capture_output=True, text=True)
    ran = RAN.search(result.stderr)
    return module, result, int(ran.group(1)) if ran else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("patterns", nargs="*", default=["test*.py"], help="module file patterns (default test*.py)")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4, help="processes at once (default: CPU count)")
    parser.add_argument("--chunk", type=int, default=4, help="most tests per process (default 4)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every process's output")
    args = parser.parse_args(argv)
    started = time.monotonic()
    work = chunks(args.patterns, args.chunk)
    if not work:
        print("no test modules match", file=sys.stderr)
        return 1
    total, failed = 0, set()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in as_completed([pool.submit(run, module, tests) for module, tests in work]):
            module, result, ran = future.result()
            total += ran
            if result.returncode or not ran:
                failed.add(module)
                print(f"FAIL {module}", flush=True)
            if args.verbose or result.returncode or not ran:
                sys.stdout.write(result.stdout + result.stderr)
    print(f"Ran {total} tests in {len(work)} processes in {time.monotonic() - started:.1f}s")
    print(f"FAILED: {', '.join(sorted(failed))}" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
