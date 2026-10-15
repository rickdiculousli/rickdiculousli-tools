from delegation_support import isolate_xdg
import json
from pathlib import Path
import tempfile
import unittest

from delegation_support import git, git_repo, run_cli, write_overlay

from delegation_check.ledger import read_events
from delegation_check.overlay import load_overlay

OVERLAY = """## Validators
ok: echo hello
bad: echo oops; exit 3
ghidra-sync [paths=ghidra/**|exports/*.json]: echo sync
docs [paths=docs/]: echo docs
## Parallel limit
2
"""


class CheckerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        isolate_xdg(self, Path(tmp.name))
        self.root = git_repo(Path(tmp.name) / "repo")
        write_overlay(self.root, OVERLAY)
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "overlay")
        self.brief = Path(tmp.name) / "brief.md"
        self.brief.write_text("brief\n")

    def cli(self, *args, code=0):
        result = run_cli(self.root, *args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result


class JudgeRunTests(CheckerTest):
    def test_judge_run_records_and_closes_without_a_brief(self):
        line = self.cli("run", "ok", "--judge").stdout.split()[0]
        delegation = line.split("#")[0]
        self.assertTrue(delegation.startswith("judge-"))
        self.assertEqual(json.loads(self.cli("pending", "--json").stdout), {"pending": []})
        results = json.loads(self.cli("query", "--delegation", delegation, "--tree", "current", "--json").stdout)["results"]
        self.assertEqual([x["id"] for x in results], [line])
        self.assertTrue(results[0]["ok"] and results[0]["stable"])
        close = [e for e in read_events(self.root) if e["event"] == "close" and e["delegation"] == delegation]
        self.assertEqual(close[0]["note"], "judge run")

    def test_failed_judge_run_still_closes(self):
        self.cli("run", "bad", "--judge", code=1)
        self.assertEqual(json.loads(self.cli("pending", "--json").stdout), {"pending": []})

    def test_judge_run_needs_exactly_one_mode_and_no_open_writer(self):
        self.assertIn("exactly one", self.cli("run", "ok", code=2).stderr)
        self.cli("open", "--delegation", "d1", "--tier", "execute", "--brief", str(self.brief))
        self.assertIn("exactly one", self.cli("run", "ok", "--judge", "--delegation", "d1", code=2).stderr)
        self.cli("run", "ok", "--judge")  # readers may stay open
        self.cli("close", "--delegation", "d1", "--outcome", "done")
        self.cli("open", "--delegation", "w1", "--tier", "execute", "--brief", str(self.brief), "--writes")
        self.assertIn("writer w1 is open", self.cli("run", "ok", "--judge", code=2).stderr)


class SuggestTests(CheckerTest):
    def test_paths_attribute_parses_and_rejects_escapes(self):
        overlay = load_overlay(self.root)
        self.assertEqual(overlay.validators["ghidra-sync"].paths, ("ghidra/**", "exports/*.json"))
        write_overlay(self.root, "## Validators\nx [paths=../out]: true\n")
        self.assertTrue(load_overlay(self.root).problems)

    def test_suggest_maps_changed_paths(self):
        self.assertIn("No changed paths", self.cli("suggest").stdout)
        (self.root / "ghidra").mkdir()
        (self.root / "ghidra" / "labels.txt").write_text("x\n")
        (self.root / "a.txt").write_text("changed\n")
        data = json.loads(self.cli("suggest", "--json").stdout)
        self.assertEqual(data["changed"], ["a.txt", "ghidra/labels.txt"])
        self.assertEqual([x["validator"] for x in data["run"]], ["ghidra-sync"])
        self.assertEqual(data["run"][0]["matched"], ["ghidra/labels.txt"])
        self.assertEqual(data["unscoped"], ["ok", "bad"])
        self.assertEqual([x["validator"] for x in data["not_needed"]], ["docs"])
        text = self.cli("suggest").stdout
        self.assertIn("run ghidra-sync: ghidra/labels.txt", text)
        self.assertIn("skip docs", text)


if __name__ == "__main__":
    unittest.main()
