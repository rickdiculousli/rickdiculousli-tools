"""Delegation 0.11.0: lock provider leases, dependents, brief rules and lane tags."""
from delegation_support import isolate_xdg
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from delegation_support import ROOT, SCRIPTS, git, git_repo, run_cli, write_overlay

from delegation_check.brief import footer
from delegation_check.ledger import read_events
from delegation_check.overlay import load_overlay
from delegation_check.state import Paths

FAKE = ROOT / "tests" / "fake_lease_provider.py"
PROVIDER = shlex.join([sys.executable, str(FAKE)])


class LanesCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        isolate_xdg(self, self.tmp)
        self.root = git_repo(self.tmp / "repo")
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("# Delegation d1\n\nTier: routine\nGoal: test\n", encoding="utf-8")

    def cli(self, *args, code=0, root=None):
        result = run_cli(root or self.root, *args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def open(self, delegation="d1", *extra):
        return self.cli("open", "--delegation", delegation, "--tier", "routine", "--brief", str(self.brief), *extra)

    def results(self):
        return [e for e in read_events(self.root) if e["event"] == "result"]


class OverlayParsingTests(LanesCase):
    def test_repo_without_new_sections_sees_defaults(self):
        write_overlay(self.root, "## Locks\nmem: slots=2\n## Validators\nok: echo hi\n")
        overlay = load_overlay(self.root)
        self.assertEqual(overlay.problems, ())
        self.assertIsNone(overlay.lock_provider)
        self.assertEqual(overlay.rules, ())
        self.assertEqual(overlay.deps, {})
        self.assertIsNone(overlay.deps_command)
        self.assertEqual(overlay.locks["mem"].ttl, 120.0)
        text = footer(self.root, "d1", overlay)
        self.assertNotIn("Rules", text)
        self.assertNotIn("lane", text)
        self.assertTrue(text.startswith("Delegation id: d1\n"))

    def test_provider_line_is_parsed_quoted_or_bare(self):
        write_overlay(self.root, '## Locks\nprovider: "lane lease"\ncargo: slots=3, wait=60, ttl=30\n')
        overlay = load_overlay(self.root)
        self.assertEqual(overlay.problems, ())
        self.assertEqual(overlay.lock_provider, "lane lease")
        self.assertEqual((overlay.locks["cargo"].slots, overlay.locks["cargo"].wait, overlay.locks["cargo"].ttl), (3, 60.0, 30.0))
        self.assertNotIn("provider", overlay.locks)
        write_overlay(self.root, "## Locks\n- provider: lane lease --verbose\n- cargo:\n")
        self.assertEqual(load_overlay(self.root).lock_provider, "lane lease --verbose")

    def test_provider_problems(self):
        write_overlay(self.root, '## Locks\nprovider: ""\nprovider: lane lease\ncargo: ttl=0\n')
        problems = load_overlay(self.root).problems
        self.assertEqual(len(problems), 3, problems)
        self.assertIn('line 2: provider needs a command', problems[0])
        self.assertIn('line 3: duplicate lock provider', problems[1])
        self.assertIn('line 4: ttl needs a positive number', problems[2])
        self.assertEqual(self.cli("lint", code=1).returncode, 1)

    def test_a_lock_named_provider_is_a_lint_problem(self):
        write_overlay(self.root, "## Locks\nprovider: slots=2, wait=5\n")
        overlay = load_overlay(self.root)
        self.assertIsNone(overlay.lock_provider)
        self.assertEqual(overlay.locks, {})
        self.assertEqual(overlay.problems, ('line 2: "provider" is reserved for the lock provider command; rename this lock',))

    def test_rules_and_deps_sections(self):
        write_overlay(self.root, "## Rules\n- Never print the word skip in test output.\n- Scratch goes under the cache root.\n"
                                 "## Deps\n- crates/app-core/: crates/app-ui, crates/app-cli/\n- crates/app-ui: crates/app-cli, crates/app-ui\n"
                                 "- command: python3 -I tools/dependents.py\n")
        overlay = load_overlay(self.root)
        self.assertEqual(overlay.problems, ())
        self.assertEqual(overlay.rules, ("Never print the word skip in test output.", "Scratch goes under the cache root."))
        self.assertEqual(overlay.deps, {"crates/app-core": ("crates/app-ui", "crates/app-cli"), "crates/app-ui": ("crates/app-cli",)})
        self.assertEqual(overlay.deps_command, "python3 -I tools/dependents.py")

    def test_deps_problems(self):
        write_overlay(self.root, "## Deps\nnonsense\n../up: a\ncrates/a: /abs\ncrates/a: b\ncommand: x\ncommand: y\n./: crates/a\n")
        problems = load_overlay(self.root).problems
        self.assertEqual([p.split(":")[0] for p in problems], ["line 2", "line 3", "line 4", "line 5", "line 7", "line 8"], problems)
        self.assertIn('expected "<unit>: <dependent>, ..."', problems[0])
        self.assertIn("deps unit needs a repository-relative directory", problems[1])
        self.assertIn("deps unit needs a repository-relative directory", problems[2])
        self.assertIn('duplicate deps unit "crates/a"', problems[3])
        self.assertIn("duplicate deps command", problems[4])
        self.assertIn("deps unit needs a repository-relative directory", problems[5])
        self.assertNotIn("validator", " ".join(problems))


class LeaseProviderTests(LanesCase):
    def setUp(self):
        super().setUp()
        self.store = self.tmp / "leases"
        self.log = self.tmp / "provider.log"
        patched = patch.dict(os.environ, FAKE_LEASE_DIR=str(self.store), FAKE_LEASE_LOG=str(self.log))
        patched.start()
        self.addCleanup(patched.stop)

    def overlay(self, locks="cargo: wait=1", validators="heavy [lock=cargo, timeout=10]: echo built\n"):
        write_overlay(self.root, f'## Locks\nprovider: "{PROVIDER}"\n{locks}\n## Validators\n{validators}')

    def calls(self):
        """Provider calls without holder details; `holders()` has those."""
        return [line.partition(" | ")[0] for line in self.holders()]

    def holders(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def wait_for(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(predicate(), "condition not met in time")

    def test_run_takes_a_lease_instead_of_a_native_slot(self):
        self.overlay()
        self.open()
        out = self.cli("run", "heavy", "--delegation", "d1").stdout
        self.assertIn("d1#1 PASS", out)
        event = self.results()[0]
        self.assertEqual(event["lock"], "cargo")
        self.assertIsNone(event["lock_slot"])
        self.assertEqual(event["lease"]["key"], "cargo.0")
        self.assertEqual(event["lease"]["ttl_s"], 120.0)
        self.assertEqual(event["lease"]["provider"], PROVIDER)
        self.assertFalse(event["lease"]["lost"])
        self.assertEqual(self.calls(), ["acquire cargo --ttl 120", "release cargo.0"])
        self.assertEqual(self.holders()[0].partition(" | ")[2],
                         "DELEGATION_LEASE_DELEGATION=d1 DELEGATION_LEASE_COMMAND=heavy")
        self.assertEqual(sorted(self.store.iterdir()), [])
        self.assertFalse(list(Paths(self.root).locks.glob("*.lock")))

    def test_ttl_is_rounded_up_to_whole_seconds(self):
        self.overlay("cargo: ttl=2.1")
        self.open()
        self.cli("run", "heavy", "--delegation", "d1")
        self.assertEqual(self.calls(), ["acquire cargo --ttl 3", "release cargo.0"])
        self.assertEqual(self.results()[0]["lease"]["ttl_s"], 2.1)

    def test_release_failure_is_reported_but_not_fatal(self):
        self.overlay()
        self.open()
        with patch.dict(os.environ, FAKE_LEASE_MODE="norelease"):
            result = self.cli("run", "heavy", "--delegation", "d1")
        self.assertIn("d1#1 PASS", result.stdout)
        self.assertIn("lock provider could not release cargo lease cargo.0: release refused", result.stderr)

    def test_lease_is_renewed_at_a_third_of_the_ttl(self):
        self.overlay("cargo: ttl=0.9", "heavy [lock=cargo, timeout=10]: sleep 1\n")
        self.open()
        self.cli("run", "heavy", "--delegation", "d1")
        event = self.results()[0]
        self.assertGreaterEqual(event["lease"]["renewals"], 1)
        self.assertFalse(event["lease"]["lost"])
        self.assertIn("renew cargo.0 --ttl 1", self.calls())
        self.assertEqual(self.calls()[0], "acquire cargo --ttl 1")
        self.assertEqual(self.calls()[-1], "release cargo.0")

    def test_lost_lease_is_recorded_and_the_run_still_completes(self):
        self.overlay("cargo: ttl=0.6", "heavy [lock=cargo, timeout=10]: sleep 1\n")
        self.open()
        self.store.mkdir()
        proc = subprocess.Popen([sys.executable, str(SCRIPTS / "check.py"), "run", "heavy", "--delegation", "d1"],
                                cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.wait_for((self.store / "cargo.0").exists)
        (self.store / "cargo.0").unlink()
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("could not renew cargo lease cargo.0", err)
        self.assertTrue(self.results()[0]["lease"]["lost"])
        self.assertTrue(self.results()[0]["ok"])

    def test_busy_provider_is_polled_until_wait_runs_out(self):
        self.overlay("cargo: wait=1.5")
        self.open()
        self.store.mkdir()
        (self.store / "cargo.0").write_text("someone else\n", encoding="utf-8")
        result = self.cli("run", "heavy", "--delegation", "d1", code=2)
        self.assertIn("waiting for lock cargo from provider: all slots of cargo are leased", result.stderr)
        self.assertIn("lock cargo still busy after 1.5s", result.stderr)
        self.assertEqual(self.results(), [])
        self.assertGreaterEqual(self.calls().count("acquire cargo --ttl 120"), 2)
        self.assertNotIn("release cargo.0", self.calls())

    def test_busy_provider_admits_once_a_slot_frees(self):
        self.overlay("cargo: wait=10")
        self.open()
        self.store.mkdir()
        (self.store / "cargo.0").write_text("someone else\n", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, str(SCRIPTS / "check.py"), "run", "heavy", "--delegation", "d1"],
                                cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.wait_for(lambda: self.calls().count("acquire cargo --ttl 120") >= 2)
        (self.store / "cargo.0").unlink()
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("d1#1 PASS", out)
        self.assertIn("waiting for lock cargo from provider", err)
        self.assertGreater(self.results()[0]["lock_wait_s"], 0.5)
        self.assertEqual(self.calls()[-1], "release cargo.0")

    def test_exec_waits_for_a_busy_provider_too(self):
        self.overlay("cargo: wait=1")
        self.store.mkdir()
        (self.store / "cargo.0").write_text("someone else\n", encoding="utf-8")
        result = self.cli("exec", "--lock", "cargo", "--timeout", "10", "--", "echo", "hi", code=2)
        self.assertIn("lock cargo still busy after 1s", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_provider_errors_refuse_without_a_result(self):
        self.overlay()
        self.open()
        with patch.dict(os.environ, FAKE_LEASE_MODE="fail"):
            result = self.cli("run", "heavy", "--delegation", "d1", code=2)
        self.assertIn("lock provider failed to acquire cargo (exit 7): lease store unreachable", result.stderr)
        with patch.dict(os.environ, FAKE_LEASE_MODE="nokey"):
            result = self.cli("run", "heavy", "--delegation", "d1", code=2)
        self.assertIn("printed no lease key", result.stderr)
        write_overlay(self.root, '## Locks\nprovider: "/nonexistent/lane lease"\ncargo:\n## Validators\nheavy [lock=cargo, timeout=10]: echo built\n')
        result = self.cli("run", "heavy", "--delegation", "d1", code=2)
        self.assertIn("lock provider not found: /nonexistent/lane", result.stderr)
        self.assertEqual(self.results(), [])

    def test_exec_and_judge_runs_use_the_provider(self):
        self.overlay()
        result = self.cli("exec", "--lock", "cargo", "--timeout", "10", "--", sys.executable, "-c", "import sys; sys.exit(4)", code=4)
        self.assertEqual(self.calls(), ["acquire cargo --ttl 120", "release cargo.0"])
        self.log.unlink()
        self.cli("run", "heavy", "--judge")
        self.assertEqual(self.calls(), ["acquire cargo --ttl 120", "release cargo.0"])
        self.assertEqual(self.results()[0]["lease"]["key"], "cargo.0")
        self.log.unlink()
        self.open("d2")
        result = self.cli("exec", "--lock", "cargo", "--timeout", "10", "--delegation", "d2", "--", "echo", "hi")
        self.assertIn("d2#1 PASS", result.stdout)
        self.assertEqual(self.calls(), ["acquire cargo --ttl 120", "release cargo.0"])

    def test_locks_lists_the_provider(self):
        self.overlay("cargo: slots=3, wait=60, ttl=30\ngames: slots=6")
        out = self.cli("locks").stdout
        self.assertEqual(out, f"provider: {PROVIDER} (leases; slots and holders are the provider's)\n"
                              "cargo: lease ttl 30s, wait 60s\ngames: lease ttl 120s\n")

    def test_without_provider_native_locks_are_unchanged(self):
        write_overlay(self.root, "## Locks\ncargo:\n## Validators\nheavy [lock=cargo, timeout=10]: echo built\n")
        self.open()
        self.cli("run", "heavy", "--delegation", "d1")
        event = self.results()[0]
        self.assertEqual(event["lock_slot"], 0)
        self.assertNotIn("lease", event)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.cli("locks").stdout, "cargo: 1 slot\n  cargo.0 free\n")


DEPS_OVERLAY = """## Validators
core [paths=crates/app-core/**]: echo core
ui [paths=crates/app-ui/**]: echo ui
cli [paths=crates/app-cli/src/*.rs]: echo cli
docs [paths=docs/**]: echo docs
all: echo all
## Deps
crates/app-core: crates/app-ui
crates/app-ui: crates/app-cli
crates/app-cli: crates/app-core
"""


class DependentsTests(LanesCase):
    def setUp(self):
        super().setUp()
        for path in ("crates/app-core/src/lib.rs", "crates/app-ui/src/lib.rs", "crates/app-cli/src/main.rs", "docs/index.md"):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("x\n", encoding="utf-8")
        write_overlay(self.root, DEPS_OVERLAY)
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "crates")
        (self.root / "crates/app-core/src/lib.rs").write_text("y\n", encoding="utf-8")

    def suggest(self, *args):
        return json.loads(self.cli("suggest", "--json", *args).stdout)

    def test_without_the_flag_output_is_unchanged(self):
        data = self.suggest()
        self.assertEqual(sorted(data), ["base", "changed", "not_needed", "run", "unscoped"])
        self.assertEqual([item["validator"] for item in data["run"]], ["core"])
        self.assertEqual(sorted(data["run"][0]), ["matched", "paths", "validator"])
        self.assertEqual([item["validator"] for item in data["not_needed"]], ["ui", "cli", "docs"])

    def test_with_dependents_adds_their_validators_transitively(self):
        data = self.suggest("--with-dependents")
        self.assertEqual(data["deps_source"], "overlay")
        self.assertEqual(data["dependents"], [{"unit": "crates/app-core", "dependents": ["crates/app-ui", "crates/app-cli"]}])
        self.assertEqual([(item["validator"], item["via"]) for item in data["run"]],
                         [("core", "changed"), ("ui", "dependents"), ("cli", "dependents")])
        self.assertEqual(data["run"][1]["dependents"], ["crates/app-ui"])
        self.assertEqual(data["run"][2]["dependents"], ["crates/app-cli"])
        self.assertEqual(data["run"][1]["matched"], [])
        self.assertEqual([item["validator"] for item in data["not_needed"]], ["docs"])
        self.assertEqual(data["unscoped"], ["all"])
        text = self.cli("suggest", "--with-dependents").stdout
        self.assertIn("dependents of crates/app-core: crates/app-ui, crates/app-cli\n", text)
        self.assertIn("run ui: dependent: crates/app-ui\n", text)

    def test_deps_command_supplies_the_map(self):
        script = self.root / "tools" / "dependents.py"
        script.parent.mkdir()
        script.write_text('import json; print(json.dumps({"crates/app-core/": ["crates/app-cli/", "crates/app-core"]}))\n', encoding="utf-8")
        write_overlay(self.root, DEPS_OVERLAY + f"command: {shlex.join([sys.executable, '-I', 'tools/dependents.py'])}\n")
        data = self.suggest("--with-dependents")
        self.assertEqual(data["deps_source"], "command")
        self.assertEqual(data["dependents"], [{"unit": "crates/app-core", "dependents": ["crates/app-cli"]}])
        self.assertEqual([item["validator"] for item in data["run"]], ["core", "cli"])
        script.write_text("import sys; print('boom', file=sys.stderr); sys.exit(5)\n", encoding="utf-8")
        result = self.cli("suggest", "--with-dependents", code=2)
        self.assertIn("deps command failed (exit 5): boom", result.stderr)
        script.write_text("print('[1]')\n", encoding="utf-8")
        self.assertIn("JSON object", self.cli("suggest", "--with-dependents", code=2).stderr)
        script.write_text('import json; print(json.dumps({"crates/app-core": ["../out"]}))\n', encoding="utf-8")
        self.assertIn("unsafe dependent", self.cli("suggest", "--with-dependents", code=2).stderr)

    def test_without_deps_the_flag_is_a_no_op(self):
        write_overlay(self.root, DEPS_OVERLAY.partition("## Deps")[0])
        data = self.suggest("--with-dependents")
        self.assertIsNone(data["deps_source"])
        self.assertEqual(data["dependents"], [])
        self.assertEqual([item["validator"] for item in data["run"]], ["core"])
        self.assertIn("no ## Deps section", self.cli("suggest", "--with-dependents").stdout)


class RulesAndLaneTests(LanesCase):
    def test_rules_are_injected_into_every_brief(self):
        write_overlay(self.root, "## Rules\n- Never print the word skip in test output.\n- A regenerated fixture gets a new cache key.\n")
        self.open()
        text = self.cli("brief", "--delegation", "d1").stdout
        self.assertIn("Rules (overlay ## Rules); these apply to everything you do here:\n"
                      "- Never print the word skip in test output.\n- A regenerated fixture gets a new cache key.\n", text)
        self.assertLess(text.index("Do not commit"), text.index("Rules (overlay"))
        self.assertLess(text.index("Rules (overlay"), text.index("Scratch:"))

    def test_open_lane_is_recorded_everywhere(self):
        write_overlay(self.root, "## Validators\nok: echo hi\n")
        self.open("d1", "--lane", "core", "--kind", "port-module", "--new-kind", "Port one module")
        self.assertIn("opened d1 (routine, reader, kind port-module, lane core)", self.cli("open", "--delegation", "d0", "--tier", "routine",
                      "--brief", str(self.brief), "--lane", "core", "--kind", "port-module").stdout.replace("d0", "d1"))
        opened = [e for e in read_events(self.root) if e["event"] == "open" and e["delegation"] == "d1"][0]
        self.assertEqual(opened["lane"], "core")
        pending = json.loads(self.cli("pending", "--json").stdout)["pending"]
        self.assertEqual([item["lane"] for item in pending], ["core", "core"])
        self.assertIn("d1 routine reader lane core opened", self.cli("pending").stdout)
        self.assertTrue(self.cli("brief", "--delegation", "d1").stdout.find("Delegation id: d1 (lane core)") >= 0)
        paths = Paths(self.root)
        lines = [json.loads(line) for line in (paths.repo / "patterns.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([line.get("lane") for line in lines], ["core", "core"])
        kinds = json.loads(self.cli("patterns", "--json").stdout)["kinds"]
        self.assertEqual(kinds[0]["lanes"], ["core"])
        self.open("d2", "--lane", "ui", "--kind", "port-module")
        kinds = json.loads(self.cli("patterns", "--json", "--min", "1").stdout)["kinds"]
        self.assertEqual(kinds[0]["lanes"], ["core", "ui"])
        self.assertIn("lanes core, ui", self.cli("patterns", "--min", "1").stdout)

    def test_invalid_lane_is_refused(self):
        result = self.cli("open", "--delegation", "d1", "--tier", "routine", "--brief", str(self.brief),
                          "--lane", "Core Lane", code=2)
        self.assertIn("invalid lane name", result.stderr)
        self.assertEqual(read_events(self.root), [])

    def test_without_lane_events_are_unchanged(self):
        self.open("d1", "--kind", "port-module", "--new-kind", "Port one module")
        opened = read_events(self.root)[0]
        self.assertNotIn("lane", opened)
        pending = json.loads(self.cli("pending", "--json").stdout)["pending"]
        self.assertEqual(sorted(pending[0]), ["delegation", "opened", "tier", "tree", "writes"])
        self.assertTrue(self.cli("brief", "--delegation", "d1").stdout.find("Delegation id: d1\n") >= 0)
        line = json.loads((Paths(self.root).repo / "patterns.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn("lane", line)
        kinds = json.loads(self.cli("patterns", "--json", "--min", "1").stdout)["kinds"]
        self.assertEqual(sorted(kinds[0]), ["candidate", "count", "days", "description", "kind", "last", "outcomes",
                                            "role", "status", "tiers", "worktrees"])
        self.assertEqual(sorted(json.loads(self.cli("kinds", "--json").stdout)["kinds"][0]), sorted(kinds[0]))


if __name__ == "__main__":
    unittest.main()
