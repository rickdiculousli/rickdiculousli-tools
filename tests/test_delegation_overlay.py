from pathlib import Path
import tempfile
import unittest

from delegation_support import git_repo, run_cli, write_overlay

from delegation_check.overlay import load_overlay

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
            o.validators["refs"],
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
        self.assertEqual(o.validators, {"unit": "x"})
        self.assertEqual(o.extra_inputs, ("golden/trace.bin",))
        self.assertEqual(o.problems, ())

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
