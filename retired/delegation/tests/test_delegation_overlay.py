from delegation_support import isolate_xdg, state_payload
from pathlib import Path
import tempfile
import unittest

from delegation_support import git_repo, run_cli, write_overlay

from delegation_check.overlay import Lock, Validator, load_overlay

SPEC_EXAMPLE = """# Delegation overlay: game-decomp
## Bulk work
Decompiling and naming functions per module file; porting simulation code to Rust against golden traces.
## Oracle
Golden-trace diff (per-tick thing state); the unit test suites.
## Validators
unit: uv run -m unittest discover -s tests -v
probes: uv run -m unittest discover -s research/probes/tests -v
refs: uv run --no-project python -I research/modules/check_refs.py
## Single writer
The Ghidra project (through ghidra-mcp); research/modules/functions.csv, then apply_annotations.py.
## Findings
research/findings.jsonl (existing schema, with status `refuted` added).
## Return fields
thing offsets touched (read/write); globals read/written; callers/callees.
## Tier hints
execute: naming one module file; one Rust plan task against traces.
routine: probe batches (--jobs 6 max); first-divergence triage; export_functions.py --check.
## Parallel limit
3 (ghidra-mcp concurrency unverified)
"""


class OverlayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        isolate_xdg(self, Path(tmp.name))
        self.root = git_repo(Path(tmp.name) / "repo")

    def test_missing_overlay_uses_defaults(self):
        o = load_overlay(self.root)
        self.assertFalse(o.exists)
        self.assertEqual((o.parallel_limit, o.return_cap), (3, 400))
        self.assertEqual(o.problems, ())

    def test_parses_spec_example(self):
        write_overlay(self.root, SPEC_EXAMPLE)
        o = load_overlay(self.root)
        self.assertTrue(o.exists)
        self.assertEqual(
            o.validators["refs"].command,
            "uv run --no-project python -I research/modules/check_refs.py",
        )
        self.assertEqual(set(o.validators), {"unit", "probes", "refs"})
        self.assertEqual(o.parallel_limit, 3)
        self.assertEqual(o.problems, ())

    def test_tolerant_parsing(self):
        text = (
            "# T\r\n## validators  \r\n- unit: x\r\n"
            "## EXTRA INPUTS\r\n- `golden/trace.bin`\r\n"
        )
        write_overlay(self.root, text)
        o = load_overlay(self.root)
        self.assertEqual(o.validators, {"unit": Validator("x")})
        self.assertEqual(o.extra_inputs, ("golden/trace.bin",))
        self.assertEqual(o.problems, ())

    def test_validator_attributes(self):
        text = (
            "## Validators\n"
            "lint [cheap]: cargo clippy -- -D warnings\n"
            "test [timeout=1800, lock=cargo]: cargo test --workspace\n"
            "fmt []: cargo fmt --check\n"
            "probes [requires=darwin]: xcrun probe\n"
            "either [requires=darwin|linux, cheap]: true\n"
            "## Oracle\nvalidator:test\n"
            "## Locks\ncargo: slots=2, wait=600\nmem:\n"
        )
        write_overlay(self.root, text)
        o = load_overlay(self.root)
        self.assertEqual(o.problems, ())
        self.assertEqual(o.validators, {
            "lint": Validator("cargo clippy -- -D warnings", cheap=True),
            "test": Validator("cargo test --workspace", timeout=1800.0, lock="cargo"),
            "fmt": Validator("cargo fmt --check"),
            "probes": Validator("xcrun probe", requires=("darwin",)),
            "either": Validator("true", cheap=True, requires=("darwin", "linux")),
        })
        self.assertEqual(o.locks, {"cargo": Lock(2, 600.0), "mem": Lock(1, None)})

    def test_validator_attribute_problems(self):
        text = (
            "## Validators\n"
            "a [fast]: x\n"
            "b [timeout=0]: x\n"
            "c [timeout=soon]: x\n"
            "d [lock=Big Lock]: x\n"
            "e [cheap, cheap]: x\n"
            "f [cheap=yes]: x\n"
            "g [cheap: x\n"
            "h [requires=Mac OS]: x\n"
            "i [requires=]: x\n"
            "j [requires=darwin|]: x\n"
        )
        write_overlay(self.root, text)
        o = load_overlay(self.root)
        problems = "\n".join(o.problems)
        for needle in (
            'line 2: unknown validator attribute "fast"',
            'line 3: timeout needs a positive number, got "0"',
            'line 4: timeout needs a positive number, got "soon"',
            "line 5: lock name must match",
            'line 6: duplicate validator attribute "cheap"',
            'line 7: unknown validator attribute "cheap=yes"',
            'line 8: expected "name: command"',
            'line 9: requires needs platform names like darwin or linux, separated by |, got "Mac OS"',
            'line 10: requires needs platform names like darwin or linux, separated by |, got ""',
            'line 11: requires needs platform names like darwin or linux, separated by |, got "darwin|"',
        ):
            self.assertIn(needle, problems)
        self.assertNotIn("g", o.validators)

    def test_lock_problems(self):
        text = (
            "## Validators\n"
            "a [lock=ghost, timeout=5]: x\n"
            "b [lock=cargo]: x\n"
            "## Locks\n"
            "cargo: slots=0\n"
            "cargo: slots=1\n"
            "disk: wait=never\n"
            "net: fast\n"
            "Bad Name: slots=1\n"
        )
        write_overlay(self.root, text)
        problems = "\n".join(load_overlay(self.root).problems)
        for needle in (
            'line 2: lock "ghost" is not declared under ## Locks',
            'line 3: validator "b" holds a lock, so it needs a timeout',
            'line 5: slots needs a positive integer, got "0"',
            'line 6: duplicate lock "cargo"',
            'line 7: wait needs a positive number, got "never"',
            'line 8: unknown lock attribute "fast"',
            'line 9: expected "name: slots=<n>, wait=<seconds>"',
        ):
            self.assertIn(needle, problems)

    def test_lint_problems(self):
        text = (
            "## Bogus\nx\n"
            "## Oracle\nfoo\n## Oracle\nbar\n"
            "## Validators\nunit: x\nbad line\nunit: y\n"
            "## Parallel limit\nmany\n"
            "## Extra inputs\n../x\n"
            "## Tier hints\nroutine: run validator:trace-diff\n"
        )
        write_overlay(self.root, text)
        o = load_overlay(self.root)
        problems = "\n".join(o.problems)
        for needle in (
            'unknown heading "Bogus"',
            'duplicate heading "Oracle"',
            'expected "name: command"',
            'duplicate validator "unit"',
            "Parallel limit",
            "escapes the repository: ../x",
            'unregistered validator "trace-diff"',
        ):
            self.assertIn(needle, problems)
        self.assertIn("line 1: unknown heading", problems)
        self.assertEqual(o.parallel_limit, 3)

    def test_cli_lint_exit_codes(self):
        r = run_cli(self.root, "lint")
        self.assertEqual(r.returncode, 0)
        self.assertIn("base defaults apply", r.stdout)
        write_overlay(self.root, SPEC_EXAMPLE)
        r = run_cli(self.root, "lint")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Overlay OK", r.stdout)
        write_overlay(self.root, "## Bogus\n")
        r = run_cli(self.root, "lint")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Bogus", r.stdout)


if __name__ == "__main__":
    unittest.main()
