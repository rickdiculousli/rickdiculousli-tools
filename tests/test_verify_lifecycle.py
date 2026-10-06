import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.sync_marketplaces import load_catalog
from scripts.verify_lifecycle import compare_tree, verify_host


ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = "rickdiculousli-plugins"
PLUGIN_ID = "hello-world@rickdiculousli-plugins"


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name)
        self.registered = False
        self.installed = []

    def fake_command(self, args, env, cwd):
        """Boundary fixture modeled on Codex 0.160.1's actual JSON output."""
        flags = args[1:]
        output = {}
        if flags == ["--version"]:
            output = "codex-cli 0.160.1"
        elif flags[:3] == ["plugin", "marketplace", "add"]:
            self.registered = True
            (self.profile / "config.toml").write_text('[marketplaces.rickdiculousli-plugins]\nsource_type = "local"\n')
            output = {"marketplaceName": MARKETPLACE, "installedRoot": str(ROOT), "alreadyAdded": False}
        elif flags[:3] == ["plugin", "marketplace", "list"]:
            output = {"marketplaces": [{"name": MARKETPLACE, "root": str(ROOT)}] if self.registered else []}
        elif flags[:2] == ["plugin", "list"]:
            output = {"installed": self.installed, "available": [
                {"pluginId": f"{manifest['name']}@{MARKETPLACE}", "name": manifest["name"],
                 "installed": False, "enabled": False}
                for _, manifest in load_catalog(ROOT)[1]]}
        elif flags[:2] == ["plugin", "add"]:
            output = {"pluginId": flags[2], "installedPath": str(self.profile / "plugins/cache" / flags[2])}
        elif flags[:3] == ["plugin", "marketplace", "remove"]:
            self.registered = False
        return subprocess.CompletedProcess(args, 0, output if isinstance(output, str) else json.dumps(output), "")

    def test_successful_add_without_installed_state_fails(self):
        with patch("scripts.verify_lifecycle.shutil.which", return_value="/test/codex"), patch(
            "scripts.verify_lifecycle.run_command", side_effect=self.fake_command
        ):
            result = verify_host("codex", ROOT, self.profile)
        self.assertFalse(result["passed"])
        self.assertIn(PLUGIN_ID, result["error"])
        self.assertFalse(self.registered)

    def test_successful_registration_without_marketplace_state_fails(self):
        def omit_marketplace(args, env, cwd):
            response = self.fake_command(args, env, cwd)
            if args[1:4] == ["plugin", "marketplace", "list"]:
                response.stdout = '{"marketplaces": []}'
            return response

        with patch("scripts.verify_lifecycle.shutil.which", return_value="/test/codex"), patch(
            "scripts.verify_lifecycle.run_command", side_effect=omit_marketplace
        ):
            result = verify_host("codex", ROOT, self.profile)
        self.assertFalse(result["passed"])
        self.assertIn(MARKETPLACE, result["error"])

    def test_original_failure_survives_cleanup_failure(self):
        def fail_install_and_cleanup(args, env, cwd):
            if args[1:3] == ["plugin", "add"]:
                raise RuntimeError("install failed")
            if args[1:4] == ["plugin", "marketplace", "remove"]:
                raise RuntimeError("cleanup failed")
            return self.fake_command(args, env, cwd)

        with patch("scripts.verify_lifecycle.shutil.which", return_value="/test/codex"), patch(
            "scripts.verify_lifecycle.run_command", side_effect=fail_install_and_cleanup
        ):
            result = verify_host("codex", ROOT, self.profile)
        self.assertFalse(result["passed"])
        self.assertEqual(result["error"], "install failed")
        self.assertTrue(any("cleanup failed" in error for error in result["cleanup_errors"]))

    def test_missing_executable_fails_instead_of_skipping(self):
        with patch("scripts.verify_lifecycle.shutil.which", return_value=None):
            result = verify_host("codex", ROOT, self.profile)
        self.assertFalse(result["passed"])
        self.assertIn("codex", result["error"])

    def test_unknown_host_fails_instead_of_skipping(self):
        result = verify_host("unknown", ROOT, self.profile)
        self.assertFalse(result["passed"])
        self.assertIn("unknown", result["error"])

    def test_existing_profile_refused_without_invoking_cli(self):
        (self.profile / "settings.json").write_text("{}")
        with patch("scripts.verify_lifecycle.run_command") as command:
            result = verify_host("claude", ROOT, self.profile)
        self.assertFalse(result["passed"])
        self.assertIn("empty", result["error"])
        command.assert_not_called()



class CompareTreeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.source = Path(temp.name) / "source"
        self.installed = Path(temp.name) / "installed"
        for root in (self.source, self.installed):
            for relative, content in (("plugin.json", "{}"), ("skills/a/SKILL.md", "skill"),
                                      ("skills/a/scripts/run.py", "print()"), ("skills/a/templates/t.css", "a{}")):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
        self.expected = ["plugin.json", "skills/a/SKILL.md", "skills/a/scripts/run.py", "skills/a/templates/t.css"]

    def test_identical_trees(self):
        self.assertEqual(compare_tree(self.expected, self.source, self.installed), [])

    def test_compare_tree_reports_missing_changed_and_extra(self):
        (self.installed / "skills/a/scripts/run.py").unlink()
        (self.installed / "skills/a/templates/t.css").write_text("changed")
        (self.installed / "skills/a/stray.txt").write_text("x")
        self.assertEqual(compare_tree(self.expected, self.source, self.installed), [
            "changed: skills/a/templates/t.css", "extra: skills/a/stray.txt", "missing: skills/a/scripts/run.py"])

    def test_compare_tree_ignores_host_dirs_pycache_and_ds_store(self):
        for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
                         "skills/a/scripts/__pycache__/run.cpython-314.pyc", ".DS_Store"):
            path = self.installed / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x")
        self.assertEqual(compare_tree(self.expected, self.source, self.installed), [])


if __name__ == "__main__":
    unittest.main()
