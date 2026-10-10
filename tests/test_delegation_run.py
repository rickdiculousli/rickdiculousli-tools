import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from delegation_support import SCRIPTS, git, git_repo, run_cli, write_overlay

from delegation_check.ledger import read_events

OVERLAY = """## Validators
ok: echo hello
bad: echo oops; exit 3
edit: echo x >> a.txt
slow: sleep 0.2
hang: sleep 5
capped [timeout=0.3]: sleep 5
## Parallel limit
4
"""


class RunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = git_repo(Path(tmp.name) / "repo")
        write_overlay(self.root, OVERLAY)
        self.brief = Path(tmp.name) / "brief.md"
        self.brief.write_text("brief\n")

    def open(self, delegation="d1", tier="execute"):
        r = run_cli(self.root, "open", "--delegation", delegation, "--tier", tier,
                    "--brief", str(self.brief))
        self.assertEqual(r.returncode, 0, r.stderr)

    def results(self):
        return [e for e in read_events(self.root) if e["event"] == "result"]

    def query(self, *args, delegation="d1"):
        r = run_cli(self.root, "query", "--delegation", delegation, "--json", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_unwritable_state_dir_exits_2(self):
        import os
        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        self.root.chmod(0o555)
        self.addCleanup(self.root.chmod, 0o755)
        r = run_cli(self.root, "pending")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("check.py: cannot access", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_run_appends_result(self):
        self.open()
        r = run_cli(self.root, "run", "ok", "--delegation", "d1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"\Ad1#1 PASS exit=0 tree=[0-9a-f]{12}\n\Z")
        (event,) = self.results()
        self.assertEqual(event["id"], "d1#1")
        self.assertEqual(event["event"], "result")
        self.assertEqual(event["validator"], "ok")
        self.assertEqual(event["command"], "echo hello")
        self.assertEqual(event["exit"], 0)
        self.assertTrue(event["ok"])
        self.assertTrue(event["stable"])
        self.assertFalse(event["timed_out"])
        self.assertEqual(event["output_tail"], "hello")
        self.assertEqual(len(event["output_sha256"]), 64)
        self.assertEqual(event["log"], ".delegation/logs/d1/1.log")
        self.assertEqual((self.root / event["log"]).read_text(), "hello\n")
        self.assertIsNone(event["timeout_s"])
        self.assertIsNone(event["lock"])
        self.assertEqual(event["tree"], run_cli(self.root, "tree").stdout.strip())
        run_cli(self.root, "run", "ok", "--delegation", "d1")
        self.assertEqual([e["id"] for e in self.results()], ["d1#1", "d1#2"])

    def test_failing_validator_exits_1(self):
        self.open()
        r = run_cli(self.root, "run", "bad", "--delegation", "d1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL exit=3", r.stdout)
        self.assertIn("oops", r.stdout)
        self.assertEqual(self.results()[0]["exit"], 3)
        self.assertFalse(self.results()[0]["ok"])

    def test_unknown_validator_lists_registered(self):
        self.open()
        r = run_cli(self.root, "run", "nope", "--delegation", "d1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ok", r.stderr)
        self.assertIn("slow", r.stderr)

    def test_query_filters_by_delegation_and_tree(self):
        self.open("d1")
        self.open("d2")
        run_cli(self.root, "run", "ok", "--delegation", "d1")
        run_cli(self.root, "run", "ok", "--delegation", "d2")
        old = self.query("--tree", "current")
        self.assertEqual([r["id"] for r in old["results"]], ["d1#1"])
        (self.root / "a.txt").write_text("changed\n")
        self.assertEqual(self.query("--tree", "current")["results"], [])
        self.assertEqual(len(self.query()["results"]), 1)
        self.assertIsNone(self.query()["tree"])
        by_hash = self.query("--tree", old["tree"])
        self.assertEqual([r["id"] for r in by_hash["results"]], ["d1#1"])
        text = run_cli(self.root, "query", "--delegation", "d1")
        self.assertIn("d1#1 PASS", text.stdout)

    def test_query_explains_empty_result(self):
        self.open("d1")
        r = run_cli(self.root, "query", "--delegation", "d1", "--tree", "current")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", "no runs recorded for d1\n"))
        run_cli(self.root, "run", "bad", "--delegation", "d1")
        old = run_cli(self.root, "tree").stdout.strip()
        (self.root / "a.txt").write_text("changed\n")
        new = run_cli(self.root, "tree").stdout.strip()
        r = run_cli(self.root, "query", "--delegation", "d1", "--tree", "current")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(
            r.stderr, f"no stable results at tree {new[:12]}; latest: d1#1 FAIL at tree {old[:12]}\n"
        )
        r = run_cli(self.root, "query", "--delegation", "d1", "--tree", "current", "--json")
        self.assertEqual(r.stderr, "")

    def test_validator_that_edits_tree_is_unstable(self):
        self.open()
        before = run_cli(self.root, "tree").stdout.strip()
        run_cli(self.root, "run", "edit", "--delegation", "d1")
        after = run_cli(self.root, "tree").stdout.strip()
        self.assertNotEqual(before, after)
        (event,) = self.results()
        self.assertFalse(event["stable"])
        for tree in (before, after):
            self.assertEqual(self.query("--tree", tree)["results"], [])
        self.assertEqual(self.query("--tree", "current")["results"], [])
        self.assertEqual(len(self.query()["results"]), 1)

    def spawn(self, delegation, validator):
        return subprocess.Popen(
            [sys.executable, str(SCRIPTS / "check.py"), "run", validator,
             "--delegation", delegation],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def finish(self, procs):
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, out + err)

    def assert_clean_lines(self):
        raw = (self.root / ".delegation/ledger.jsonl").read_text()
        for line in raw.splitlines():
            json.loads(line)

    def test_concurrent_runs_get_distinct_ids(self):
        names = ["d1", "d2", "d3", "d4"]
        for name in names:
            self.open(name)
        self.finish([self.spawn(name, "slow") for name in names])
        ids = [e["id"] for e in self.results()]
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 4)
        self.assert_clean_lines()

    def test_concurrent_runs_in_one_delegation_number_sequentially(self):
        self.open("d1")
        self.finish([self.spawn("d1", "slow") for _ in range(4)])
        ids = sorted(e["id"] for e in self.results())
        self.assertEqual(ids, ["d1#1", "d1#2", "d1#3", "d1#4"])
        self.assert_clean_lines()

    def test_run_requires_open_delegation(self):
        r = run_cli(self.root, "run", "ok", "--delegation", "ghost")
        self.assertEqual(r.returncode, 2)
        self.open()
        run_cli(self.root, "close", "--delegation", "d1", "--outcome", "done")
        self.assertEqual(run_cli(self.root, "run", "ok", "--delegation", "d1").returncode, 2)
        self.assertEqual(self.results(), [])

    def test_delegation_closed_during_run_is_refused(self):
        self.open()
        proc = self.spawn("d1", "slow")
        import time
        time.sleep(0.1)
        run_cli(self.root, "close", "--delegation", "d1", "--outcome", "abandoned")
        out, err = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 2, out + err)
        self.assertEqual(self.results(), [])

    def test_timeout_is_recorded(self):
        self.open()
        r = run_cli(self.root, "run", "hang", "--delegation", "d1", "--timeout", "0.3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stdout)
        (event,) = self.results()
        self.assertIsNone(event["exit"])
        self.assertTrue(event["timed_out"])
        self.assertFalse(event["ok"])

    def test_overlay_timeout_applies_unless_overridden(self):
        self.open()
        r = run_cli(self.root, "run", "capped", "--delegation", "d1")
        self.assertEqual(r.returncode, 1)
        r = run_cli(self.root, "run", "capped", "--delegation", "d1", "--timeout", "0.1")
        self.assertEqual(r.returncode, 1)
        first, second = self.results()
        self.assertTrue(first["timed_out"])
        self.assertEqual((first["timeout_s"], second["timeout_s"]), (0.3, 0.1))

    def run_both(self, overlay, env=None):
        """Run validator `heavy` at the same time in this worktree and a second one."""
        write_overlay(self.root, overlay)
        git(self.root, "add", ".agents")
        git(self.root, "commit", "-q", "-m", "overlay")
        other = self.root.parent / "other"
        git(self.root, "worktree", "add", "-q", str(other))
        for root in (self.root, other):
            r = run_cli(root, "open", "--delegation", "d1", "--tier", "routine", "--brief", str(self.brief))
            self.assertEqual(r.returncode, 0, r.stderr)
        procs = [
            subprocess.Popen(
                [sys.executable, str(SCRIPTS / "check.py"), "run", "heavy", "--delegation", "d1"],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, **(env or {})},
            )
            for root in (self.root, other)
        ]
        outputs = [proc.communicate(timeout=60) for proc in procs]
        events = [e for root in (self.root, other) for e in read_events(root) if e["event"] == "result"]
        return procs, outputs, events

    def test_lock_is_shared_across_worktrees(self):
        procs, outputs, events = self.run_both(
            "## Locks\nmem:\n## Validators\nheavy [lock=mem, timeout=10]: sleep 0.5\n"
        )
        self.assertEqual([p.returncode for p in procs], [0, 0], outputs)
        self.assertEqual([e["lock"] for e in events], ["mem", "mem"])
        self.assertEqual([e["lock_slot"] for e in events], [0, 0])
        self.assertGreater(max(e["lock_wait_s"] for e in events), 0.3)
        self.assertIn("waiting for lock mem: mem.0 held by d1", "".join(err for _, err in outputs))

    def test_lock_slots_admit_that_many(self):
        procs, outputs, events = self.run_both(
            "## Locks\nmem: slots=2\n## Validators\nheavy [lock=mem, timeout=10]: sleep 0.5\n"
        )
        self.assertEqual(sorted(e["lock_slot"] for e in events), [0, 1])
        self.assertLess(max(e["lock_wait_s"] for e in events), 0.3)

    def test_environment_overrides_slots(self):
        procs, outputs, events = self.run_both(
            "## Locks\nmem: slots=1\n## Validators\nheavy [lock=mem, timeout=10]: sleep 0.5\n",
            env={"DELEGATION_LOCK_MEM": "2"},
        )
        self.assertEqual(sorted(e["lock_slot"] for e in events), [0, 1])

    def test_lock_wait_limit_refuses_without_a_result(self):
        procs, outputs, events = self.run_both(
            "## Locks\nmem: wait=0.2\n## Validators\nheavy [lock=mem, timeout=10]: sleep 1\n"
        )
        self.assertEqual(sorted(p.returncode for p in procs), [0, 2])
        self.assertIn("lock mem still busy after 0.2s", "".join(err for _, err in outputs))
        self.assertEqual(len(events), 1)

    def test_exec_holds_lock_and_passes_exit_code(self):
        write_overlay(self.root, "## Locks\nmem:\n")
        holder = subprocess.Popen(
            [sys.executable, str(SCRIPTS / "check.py"), "exec", "--lock", "mem", "--timeout", "10",
             "--delegation", "d9", "--", "sleep", "1"],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        import time
        deadline = time.monotonic() + 5
        while "held by d9" not in run_cli(self.root, "locks").stdout:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)
        r = run_cli(self.root, "locks")
        self.assertRegex(r.stdout, r"\Amem: 1 slot\n  mem\.0 held by d9 \(pid \d+, since [^)]+\): sleep 1\n\Z")
        r = run_cli(self.root, "exec", "--lock", "mem", "--timeout", "10", "--", "sh", "-c", "echo ran; exit 7")
        holder.communicate(timeout=10)
        self.assertEqual((r.returncode, r.stdout), (7, "ran\n"))
        self.assertIn("waiting for lock mem", r.stderr)
        self.assertEqual(run_cli(self.root, "locks").stdout, "mem: 1 slot\n  mem.0 free\n")
        r = run_cli(self.root, "exec", "--lock", "mem", "--timeout", "0.2", "--", "sleep", "3")
        self.assertEqual(r.returncode, 124)
        self.assertIn("timed out after 0.2s", r.stderr)
        r = run_cli(self.root, "exec", "--lock", "ghost", "--timeout", "1", "--", "true")
        self.assertEqual(r.returncode, 2)
        self.assertIn('unknown lock "ghost"; declared: mem', r.stderr)
        self.assertNotEqual(run_cli(self.root, "exec", "--lock", "mem", "--", "true").returncode, 0)

    def test_failed_run_prints_full_log_path(self):
        write_overlay(self.root, "## Validators\nlong: seq 1 500; exit 1\n")
        self.open()
        r = run_cli(self.root, "run", "long", "--delegation", "d1")
        self.assertEqual(r.returncode, 1)
        log = self.root.resolve() / ".delegation/logs/d1/1.log"
        self.assertTrue(r.stdout.endswith(f"full output: {log}\n"))
        self.assertEqual(len(log.read_text().splitlines()), 500)

    def test_output_tail_is_capped(self):
        write_overlay(self.root, "## Validators\nlong: seq 1 500\n")
        self.open()
        run_cli(self.root, "run", "long", "--delegation", "d1")
        tail = self.results()[0]["output_tail"]
        self.assertEqual(tail.splitlines()[-1], "500")
        self.assertEqual(len(tail.splitlines()), 40)
        self.assertLessEqual(len(tail), 4000)


if __name__ == "__main__":
    unittest.main()
