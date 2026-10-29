"""Tests for the recursive-refinement script: the conversation reader, the weekly cap and the surfacer."""

import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/recursive-refinement/skills/recursive-refinement/scripts/refine.py"
spec = importlib.util.spec_from_file_location("refine", SCRIPT)
refine = importlib.util.module_from_spec(spec)
sys.modules["refine"] = refine
spec.loader.exec_module(refine)

NOW = "2099-01-01T00:00:00Z"


def rec(kind, content, **extra):
    return json.dumps({"type": kind, "timestamp": NOW, "entrypoint": "cli",
                       "message": {"content": content}, **extra})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(refine.os.environ, {"XDG_STATE_HOME": str(self.root / "state"),
                                             "XDG_CACHE_HOME": str(self.root / "cache"),
                                             "XDG_CONFIG_HOME": str(self.root / "config")})
        env.start()
        self.addCleanup(env.stop)

    def repo(self, name, rules="paused: no"):
        r = self.root / name
        (r / "docs" / "refinement" / "specs").mkdir(parents=True)
        (r / "docs" / "refinement" / "rules.md").write_text(f"---\n{rules}\n---\n# rules\n")
        return r

    def conf(self, *repos, **over):
        return {**refine.DEFAULTS, "repos": [{"path": str(r)} for r in repos], **over}


class ConversationsTest(Base):
    def write_session(self, folder, name, lines):
        d = self.root / "projects" / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.jsonl").write_text("\n".join(lines) + "\n")

    def test_reads_only_what_the_user_typed_and_the_reply_they_read(self):
        repo = self.root / "my_repo"
        self.write_session(refine.slug(str(repo.resolve())), "s1", [
            rec("user", "<system-reminder>hook text</system-reminder>"),
            rec("user", "check on the widget"),
            rec("assistant", [{"type": "text", "text": "working"}]),
            rec("user", [{"type": "tool_result", "content": "x"}]),
            rec("assistant", [{"type": "text", "text": "the widget is fine"}]),
            rec("user", "<task-notification>done</task-notification>"),
        ])
        out = refine.conversations(str(repo), 7, 1500, 600, 60000, None, self.conf(), self.root / "projects")
        self.assertIn("check on the widget", out)
        self.assertIn("reply: the widget is fine", out)
        self.assertNotIn("working", out)
        self.assertNotIn("hook text", out)
        self.assertIn("1 sessions, 1 messages", out)

    def test_skips_headless_jobs_agent_briefs_and_other_repos(self):
        repo = self.root / "my_repo"
        here = refine.slug(str(repo.resolve()))
        self.write_session(here, "job", [rec("user", "file this", entrypoint="sdk-cli")])
        self.write_session(here, "brief", [rec("user", "Act as the review sub-agent"), rec("user", "more")])
        self.write_session(refine.slug(str((self.root / "other").resolve())), "x", [rec("user", "elsewhere")])
        out = refine.conversations(str(repo), 7, 1500, 600, 60000, None, self.conf(), self.root / "projects")
        self.assertIn("0 sessions", out)

    def test_session_paths_take_globs(self):
        repo = self.root / "my_repo"
        self.write_session(refine.slug(str(self.root / "trees" / "my_repo" / "t1")), "s", [rec("user", "in a tree")])
        conf = {**refine.DEFAULTS, "repos": [{"path": str(repo), "session_paths": [str(self.root / "trees/my_repo/*")]}]}
        out = refine.conversations(str(repo), 7, 1500, 600, 60000, None, conf, self.root / "projects")
        self.assertIn("in a tree", out)


class RunTest(Base):
    def fake(self, cost):
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"total_cost_usd": cost, "result": "done"}), "")
        return runner, calls

    def ledger(self):
        return refine.ledger_rows(self.root / "state" / "rickdiculousli-tools" / "recursive-refinement")

    def test_stops_at_the_weekly_cap_and_passes_each_pass_what_is_left(self):
        a, b, c = self.repo("a"), self.repo("b"), self.repo("c")
        runner, calls = self.fake(45.0)
        refine.run(self.conf(a, b, c, weekly_cap_usd=100, pass_cap_usd=60), None, None, runner)
        self.assertEqual(len(calls), 3)
        self.assertEqual([cmd[cmd.index("--max-budget-usd") + 1] for cmd in calls], ["60.00", "55.00", "10.00"])
        runner, calls = self.fake(1.0)
        refine.run(self.conf(a, b, c), "a", None, runner)
        self.assertEqual(calls, [])   # the cap is spent for the week
        self.assertEqual(sum(r["cost_usd"] for r in self.ledger()), 135.0)

    def test_skips_paused_repos_and_repos_already_passed_unless_named(self):
        a, p = self.repo("a"), self.repo("p", rules="paused: yes")
        runner, calls = self.fake(2.0)
        refine.run(self.conf(a, p), None, None, runner)
        refine.run(self.conf(a, p), None, None, runner)
        self.assertEqual(len(calls), 1)
        refine.run(self.conf(a, p), "a", None, runner)
        self.assertEqual(len(calls), 2)

    def test_a_dry_run_names_its_output_and_an_unreadable_result_costs_the_cap(self):
        a = self.repo("a")
        calls = []

        def runner(cmd, **kw):
            calls.append((cmd, kw["cwd"]))
            return subprocess.CompletedProcess(cmd, 1, "not json", "boom")
        refine.run(self.conf(a, pass_cap_usd=8), None, self.root / "dry", runner)
        cmd, cwd = calls[0]
        self.assertIn(f"mode=dry-run {self.root / 'dry' / 'a.md'}", cmd[2])
        self.assertNotEqual(Path(cwd).resolve(), a.resolve())   # the pass never runs inside the repo
        self.assertEqual(self.ledger()[0]["cost_usd"], 8)
        self.assertFalse(self.ledger()[0]["ok"])


class SurfaceTest(Base):
    def test_notes_show_once_open_specs_every_time_and_served_repos_join(self):
        here, served = self.repo("here"), self.repo("lib")
        (here / "docs/refinement/notes.md").write_text("# notes\n\n- 2099-01-01: the check-in is shorter\n")
        (served / "docs/refinement/notes.md").write_text("- 2099-01-01: search is faster\n")
        (here / "docs/refinement/specs/x.md").write_text("---\nstatus: open\n---\n# Merge the two watchlists\n")
        (here / "docs/refinement/specs/y.md").write_text("---\nstatus: rejected\n---\n# No\n")
        conf = {**refine.DEFAULTS, "repos": [{"path": str(here)}, {"path": str(served), "surface_in": [str(here)]}]}
        first = refine.surface(conf, str(here))
        self.assertIn("the check-in is shorter", first)
        self.assertIn("search is faster (lib)", first)
        self.assertIn("Merge the two watchlists", first)
        self.assertNotIn("# No", first)
        self.assertIn(refine.REMINDER, first)
        second = refine.surface(conf, str(here))
        self.assertNotIn("shorter", second)
        self.assertIn("Merge the two watchlists", second)

    def test_nothing_to_show_prints_nothing(self):
        self.assertEqual(refine.surface(self.conf(), str(self.repo("quiet"))), "")


class InstallTest(Base):
    def test_plist_parses_and_keeps_the_mac_awake(self):
        p = plistlib.loads(refine.plist(refine.DEFAULTS, Path("/x y/refine.py")).encode())
        self.assertEqual(p["ProgramArguments"][:2], ["/usr/bin/caffeinate", "-i"])
        self.assertIn("'/x y/refine.py' run", p["ProgramArguments"][-1])
        self.assertEqual(p["StartCalendarInterval"][0], {"Weekday": 6, "Hour": 4, "Minute": 0})


if __name__ == "__main__":
    unittest.main()
