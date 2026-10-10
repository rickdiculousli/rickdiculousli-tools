import hashlib
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from delegation_support import SCRIPTS, git_repo, run_cli, write_overlay

from delegation_check.ledger import ledger_path, read_events


class LedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = git_repo(Path(tmp.name) / "repo")
        self.brief = Path(tmp.name) / "brief.md"
        self.brief.write_text("do the thing\n")

    def open(self, delegation, tier="execute", writes=False):
        args = ["open", "--delegation", delegation, "--tier", tier, "--brief", str(self.brief)]
        if writes:
            args.append("--writes")
        return run_cli(self.root, *args)

    def pending(self):
        result = run_cli(self.root, "pending", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["pending"]

    def ledger_bytes(self):
        path = ledger_path(self.root)
        return path.read_bytes() if path.exists() else b""

    def test_open_close_pending_roundtrip(self):
        self.assertEqual(self.open("d1").returncode, 0)
        r = self.open("d2", tier="routine")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"\Aopened d2 \(routine, reader\) at [0-9a-f]{12}\n\Z")
        text = run_cli(self.root, "pending").stdout
        self.assertIn("d1 execute reader opened ", text)
        self.assertIn("d2 routine reader opened ", text)
        r = run_cli(self.root, "close", "--delegation", "d1", "--outcome", "done", "--note", "ok")
        self.assertEqual(r.returncode, 0, r.stderr)
        pending = self.pending()
        self.assertEqual([p["delegation"] for p in pending], ["d2"])
        self.assertEqual(set(pending[0]), {"delegation", "tier", "writes", "opened", "tree"})
        events = read_events(self.root)
        self.assertEqual([e["event"] for e in events], ["open", "open", "close"])
        self.assertEqual(events[2]["outcome"], "done")
        self.assertEqual(events[2]["note"], "ok")

    def test_pending_json_empty(self):
        r = run_cli(self.root, "pending", "--json")
        self.assertEqual(json.loads(r.stdout), {"pending": []})
        self.assertIn("No open delegations.", run_cli(self.root, "pending").stdout)

    def test_open_records_tree_and_brief_hash(self):
        self.open("d1", writes=True)
        (event,) = read_events(self.root)
        self.assertEqual(event["tree"], run_cli(self.root, "tree").stdout.strip())
        self.assertEqual(event["brief_sha256"], hashlib.sha256(self.brief.read_bytes()).hexdigest())
        self.assertEqual(event["schema"], 1)
        self.assertTrue(event["writes"])
        self.assertEqual(event["tier"], "execute")
        self.assertRegex(event["timestamp"], r"\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")

    def test_brief_prints_recorded_brief(self):
        self.open("d1")
        r = run_cli(self.root, "brief", "--delegation", "d1")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "do the thing\n", ""))

    def test_brief_refusals(self):
        r = run_cli(self.root, "brief", "--delegation", "d1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("delegation is not open: d1", r.stderr)
        self.open("d1")
        self.brief.write_text("do another thing\n")
        r = run_cli(self.root, "brief", "--delegation", "d1")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("brief changed since open", r.stderr)
        self.brief.unlink()
        r = run_cli(self.root, "brief", "--delegation", "d1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("brief not found", r.stderr)
        self.brief.write_text("do the thing\n")
        run_cli(self.root, "close", "--delegation", "d1", "--outcome", "done")
        r = run_cli(self.root, "brief", "--delegation", "d1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("delegation is not open: d1", r.stderr)

    def test_refusals(self):
        self.assertEqual(self.open("d1").returncode, 0)
        run_cli(self.root, "close", "--delegation", "d1", "--outcome", "done")
        before = self.ledger_bytes()
        cases = [
            self.open("bad id"),
            self.open("-x"),
            self.open("d2", tier="judge"),
            run_cli(self.root, "open", "--delegation", "d3", "--tier", "execute",
                    "--brief", str(self.brief.with_name("missing.md"))),
            self.open("d1"),  # already used, even though closed
            run_cli(self.root, "close", "--delegation", "never", "--outcome", "done"),
            run_cli(self.root, "close", "--delegation", "d1", "--outcome", "done"),
        ]
        for result in cases:
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.ledger_bytes(), before)

    def test_writer_rules(self):
        self.assertEqual(self.open("r1").returncode, 0)
        self.assertEqual(self.open("w1", writes=True).returncode, 2)
        run_cli(self.root, "close", "--delegation", "r1", "--outcome", "done")
        self.assertEqual(self.open("w1", writes=True).returncode, 0)
        self.assertEqual(self.open("r2").returncode, 2)
        self.assertEqual(self.open("w2", writes=True).returncode, 2)
        run_cli(self.root, "close", "--delegation", "w1", "--outcome", "abandoned")
        for name in ("a", "b", "c"):
            self.assertEqual(self.open(name).returncode, 0)
        before = self.ledger_bytes()
        self.assertEqual(self.open("d").returncode, 2)
        self.assertEqual(self.ledger_bytes(), before)

    def test_overlay_raises_parallel_limit(self):
        write_overlay(self.root, "## Parallel limit\n4\n")
        for name in ("a", "b", "c", "d"):
            self.assertEqual(self.open(name).returncode, 0, name)
        self.assertEqual(self.open("e").returncode, 2)

    def test_relative_brief_resolves_against_root(self):
        (self.root / "briefs").mkdir()
        (self.root / "briefs/b.md").write_text("x\n")
        elsewhere = self.brief.parent
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "check.py"), "--root", str(self.root),
             "open", "--delegation", "rel", "--tier", "execute", "--brief", "briefs/b.md"],
            cwd=elsewhere, capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        (event,) = read_events(self.root)
        self.assertEqual(event["brief"], "briefs/b.md")

    def test_malformed_ledger_is_an_error(self):
        self.open("d1")
        with ledger_path(self.root).open("a") as handle:
            handle.write("not json\n")
        r = run_cli(self.root, "pending")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ledger line 2", r.stderr)


if __name__ == "__main__":
    unittest.main()
