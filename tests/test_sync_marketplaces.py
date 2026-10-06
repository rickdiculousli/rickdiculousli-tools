import json
from pathlib import Path
import tempfile
import unittest

from scripts.sync_marketplaces import load_catalog, sync


class MarketplaceGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = {
            "name": "test-personal", "owner": {"name": "Tester"},
            "plugins": ["plugins/example"],
        }
        plugin = self.root / "plugins/example"
        (plugin / "skills/hello").mkdir(parents=True)
        (plugin / "plugin.json").write_text(json.dumps({
            "name": "example", "version": "0.1.0", "description": "Example skill",
        }))
        (plugin / "skills/hello/SKILL.md").write_text(
            "---\nname: hello\ndescription: Say hello when asked.\n---\nSay hello.\n"
        )
        self.save_catalog()

    def save_catalog(self):
        (self.root / "catalog.json").write_text(json.dumps(self.catalog))

    def assert_invalid_without_writes(self):
        with self.assertRaises(ValueError):
            sync(self.root)
        self.assertFalse((self.root / ".claude-plugin").exists())
        self.assertFalse((self.root / ".agents").exists())

    def test_duplicate_plugin_rejected_before_writes(self):
        self.catalog["plugins"].append("plugins/example")
        self.save_catalog()
        self.assert_invalid_without_writes()

    def test_escaping_path_rejected_before_writes(self):
        for path in ("../example", "/tmp/example", "plugins/../../example"):
            with self.subTest(path=path):
                self.catalog["plugins"] = [path]
                self.save_catalog()
                self.assert_invalid_without_writes()

    def test_manifest_identity_must_match_directory(self):
        manifest = self.root / "plugins/example/plugin.json"
        data = json.loads(manifest.read_text())
        data["name"] = "different"
        manifest.write_text(json.dumps(data))
        self.assert_invalid_without_writes()

    def test_missing_plugin_rejected_before_writes(self):
        self.catalog["plugins"] = ["plugins/missing"]
        self.save_catalog()
        self.assert_invalid_without_writes()

    def test_generates_native_sources_pointing_to_same_content(self):
        self.assertTrue(sync(self.root))
        claude = json.loads((self.root / ".claude-plugin/marketplace.json").read_text())
        codex = json.loads((self.root / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(claude["plugins"][0]["source"], "./plugins/example")
        self.assertEqual(codex["plugins"][0]["source"], {
            "source": "local", "path": "./plugins/example",
        })
        for adapter in (".claude-plugin", ".codex-plugin"):
            manifest = json.loads((self.root / "plugins/example" / adapter / "plugin.json").read_text())
            self.assertEqual(manifest["name"], "example")
            self.assertNotIn("$schema", manifest)

    def test_check_detects_drift_without_mutating_and_sync_repairs(self):
        self.assertFalse(sync(self.root, check=True))
        self.assertFalse((self.root / ".claude-plugin").exists())
        sync(self.root)
        self.assertTrue(sync(self.root, check=True))
        output = self.root / ".agents/plugins/marketplace.json"
        output.write_text("stale\n")
        self.assertFalse(sync(self.root, check=True))
        self.assertEqual(output.read_text(), "stale\n")
        self.assertTrue(sync(self.root))
        self.assertTrue(sync(self.root, check=True))


if __name__ == "__main__":
    unittest.main()
