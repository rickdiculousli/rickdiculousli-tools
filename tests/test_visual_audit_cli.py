import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from visual_audit_support import minimal_report, render_html
from render_report import main


class CliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.audit = self.tmp / ".audit"
        self.audit.mkdir()

    def run_main(self, *args):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = main([str(arg) for arg in args])
        return code, stderr.getvalue()

    def write(self, name, content):
        path = self.audit / name
        if isinstance(content, (dict, list)):
            content = json.dumps(content)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    def test_renders_and_writes_gitignore(self):
        source = self.write("r.json", minimal_report())
        self.assertEqual(self.run_main(source)[0], 0)
        self.assertTrue((self.audit / "r.html").read_text(encoding="utf-8").startswith("<!doctype html>"))
        self.assertEqual((self.audit / ".gitignore").read_text(), "*\n")

    def test_existing_gitignore_left_alone(self):
        (self.audit / ".gitignore").write_text("custom\n")
        self.run_main(self.write("r.json", minimal_report()))
        self.assertEqual((self.audit / ".gitignore").read_text(), "custom\n")

    def test_output_override(self):
        source = self.write("r.json", minimal_report())
        out = self.tmp / "elsewhere" / "out.html"
        self.assertEqual(self.run_main(source, "-o", out)[0], 0)
        self.assertTrue(out.is_file())
        self.assertFalse((self.audit / "r.html").exists())

    def test_invalid_report_exits_1_and_writes_nothing(self):
        source = self.write("r.json", minimal_report(version=2, outcome="nope"))
        code, stderr = self.run_main(source)
        self.assertEqual(code, 1)
        self.assertIn("version:", stderr)
        self.assertIn("outcome:", stderr)
        self.assertFalse((self.audit / "r.html").exists())
        self.assertEqual((self.audit / ".gitignore").read_text(), "*\n")

    def test_bad_json_bom_and_array_exit_1(self):
        for name, content in (("bad.json", "{nope"), ("array.json", [])):
            with self.subTest(name=name):
                code, stderr = self.run_main(self.write(name, content))
                self.assertEqual(code, 1)
                self.assertTrue(stderr.strip())
                self.assertFalse((self.audit / name).with_suffix(".html").exists())
        bom = self.write("bom.json", b"\xef\xbb\xbf" + json.dumps(minimal_report()).encode())
        self.assertEqual(self.run_main(bom)[0], 0)

    def test_missing_input_exits_1(self):
        code, stderr = self.run_main(self.audit / "missing.json")
        self.assertEqual(code, 1)
        self.assertIn("missing.json", stderr)

    def test_unwritable_output_exits_1(self):
        source = self.write("r.json", minimal_report())
        blocker = self.tmp / "file"
        blocker.write_text("x")
        code, stderr = self.run_main(source, "-o", blocker / "out.html")
        self.assertEqual(code, 1)
        self.assertIn("out.html", stderr)

    def test_title_is_escaped(self):
        html = render_html(minimal_report(title="<script>alert(1)</script>"))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)

    def test_unicode_round_trip(self):
        source = self.write("r.json", minimal_report(title="監査 ✅ résumé"))
        self.run_main(source)
        html = (self.audit / "r.html").read_text(encoding="utf-8")
        self.assertIn("監査 ✅", html)
        self.assertIn("résumé", html)

    def test_deterministic(self):
        report = minimal_report(modules=[{"type": "runs", "runs": [{"command": "x", "exit": 0}]}])
        self.assertEqual(render_html(report), render_html(report))

    def test_module_sections_have_anchors(self):
        html = render_html(minimal_report(modules=[{"type": "runs", "title": "Checks", "runs": []}]))
        self.assertIn('id="module-1"', html)
        self.assertIn("Checks", html)

    def test_self_contained(self):
        html = render_html(minimal_report(goal="curl https://example.com"))
        self.assertNotIn("<link", html)
        self.assertNotIn("@import", html)
        self.assertIsNone(re.search(r"""(?:src|href)\s*=\s*["']?https?:|url\(\s*["']?https?:""", html))
        self.assertIn("<style>", html)
        self.assertIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
