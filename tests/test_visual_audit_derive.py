import unittest

from visual_audit_support import minimal_report
from audit_report.derive import derive, slug
from audit_report.schema import load


def build(**overrides):
    report = load(minimal_report(**overrides))
    return report, derive(report)


def steps(*specs):
    return {"type": "timeline", "steps": [dict(kind=kind, label=f"{kind} {i}", **extra)
                                          for i, (kind, extra) in enumerate(specs)]}


class DeriveTests(unittest.TestCase):
    def test_run_failure_classes(self):
        report, d = build(modules=[{"type": "runs", "runs": [
            {"command": "a", "exit": 1},
            {"command": "b", "exit": 1, "expect_fail": True},
            {"command": "c", "exit": 0, "expect_fail": True},
            {"command": "d", "exit": 2, "resolved": True},
            {"command": "e", "exit": 0}]}])
        self.assertEqual([r["failure"] for r in report["modules"][0]["runs"]],
                         ["unresolved", "expected", "unresolved", "resolved", "ok"])
        self.assertEqual(d.runs, {"unresolved": 2, "resolved": 1, "expected": 1})

    def test_step_failures_and_retry(self):
        report, d = build(modules=[steps(
            ("run", {"status": "fail"}), ("run", {"status": "warn", "resolved": True}),
            ("run", {"status": "retry"}), ("read", {}))])
        self.assertEqual([s["failure"] for s in report["modules"][0]["steps"]],
                         ["unresolved", "resolved", "ok", "ok"])
        self.assertEqual(d.steps, {"unresolved": 1, "resolved": 1})

    def test_contradictions_for_pass(self):
        modules = [
            {"type": "runs", "runs": [{"command": "a", "exit": 1}]},
            {"type": "claims", "claims": [{"claim": "x", "status": "refuted"},
                                          {"claim": "y", "status": "unverified"}]},
        ]
        _, d = build(modules=modules)
        self.assertEqual([c.anchor for c in d.contradictions], ["run-1", "claim-1", "claim-2"])
        _, d = build(outcome="partial", blockers=["b"], modules=modules)
        self.assertEqual(d.contradictions, [])

    def test_asserted_count_excludes_read_search_think(self):
        _, d = build(modules=[
            steps(("read", {}), ("search", {}), ("think", {}), ("edit", {}), ("run", {}), ("other", {})),
            {"type": "runs", "runs": [{"command": "a", "exit": 0, "source": "observed", "evidence": "ok"}]},
        ])
        self.assertEqual((d.asserted, d.countable), (3, 4))
        self.assertFalse(d.all_asserted)

    def test_all_asserted_flag(self):
        _, d = build(modules=[steps(("edit", {}))])
        self.assertTrue(d.all_asserted)
        _, d = build(modules=[steps(("read", {}))])
        self.assertFalse(d.all_asserted)

    def test_missing_modules_are_none(self):
        _, d = build()
        self.assertIsNone(d.files)
        self.assertIsNone(d.lines_added)
        self.assertIsNone(d.lines_removed)
        self.assertIsNone(d.commands)
        _, d = build(modules=[{"type": "files", "files": []}, {"type": "runs", "runs": []}])
        self.assertEqual((d.files, d.lines_added, d.lines_removed, d.commands), (0, 0, 0, 0))

    def test_file_totals(self):
        _, d = build(modules=[{"type": "files", "files": [
            {"path": "a", "change": "added", "added": 5, "removed": 0},
            {"path": "b", "change": "modified", "added": 2, "removed": 3}]}])
        self.assertEqual((d.files, d.lines_added, d.lines_removed), (2, 7, 3))

    def test_attention_order_and_anchors(self):
        _, d = build(outcome="partial", blockers=["b"], modules=[
            {"type": "files", "files": [{"path": "src/Old File.py", "change": "deleted", "added": 0, "removed": 9}]},
            {"type": "claims", "claims": [{"claim": "u", "status": "unverified", "evidence": "x" * 2001},
                                          {"claim": "r", "status": "refuted"}]},
            steps(("run", {"status": "fail"})),
            {"type": "runs", "runs": [{"command": "a", "exit": 1}]},
        ])
        self.assertEqual([(a.kind, a.anchor) for a in d.attention], [
            ("run", "run-1"), ("step", "step-1"), ("refuted", "claim-2"), ("unverified", "claim-1"),
            ("deleted", "file-src-old-file-py"), ("truncated", "claim-1")])

    def test_cited_by_back_references(self):
        _, d = build(modules=[
            {"type": "runs", "runs": [{"command": "a", "exit": 0}]},
            {"type": "files", "files": [{"path": "a.py", "change": "added", "added": 1, "removed": 0}]},
            {"type": "claims", "claims": [
                {"claim": "c1", "status": "unverified", "refs": {"runs": [1], "files": ["a.py"]}},
                {"claim": "c2", "status": "unverified", "refs": {"runs": [1]}}]},
        ])
        self.assertEqual(d.cited_by["run-1"], ["claim-1", "claim-2"])
        self.assertEqual(d.cited_by["file-a-py"], ["claim-1"])

    def test_global_numbering_across_modules(self):
        report, d = build(modules=[steps(("read", {}), ("read", {})), steps(("edit", {}))])
        self.assertEqual([s["n"] for s in d.all_steps], [1, 2, 3])
        self.assertEqual(report["modules"][1]["steps"][0]["anchor"], "step-3")

    def test_phase_and_module_anchors(self):
        report, _ = build(modules=[steps(("read", {"phase": "Build"})), steps(("read", {"phase": "Build"}))])
        self.assertEqual(report["modules"][0]["steps"][0]["phase_anchor"], "phase-build")
        self.assertEqual(report["modules"][1]["steps"][0]["phase_anchor"], "phase-build-2")
        self.assertEqual([m["anchor"] for m in report["modules"]], ["module-1", "module-2"])

    def test_same_phase_in_one_module_shares_anchor(self):
        report, _ = build(modules=[steps(("read", {"phase": "A"}), ("read", {"phase": "A"}))])
        self.assertEqual({s["phase_anchor"] for s in report["modules"][0]["steps"]}, {"phase-a"})

    def test_duplicate_file_slugs_suffixed(self):
        report, _ = build(modules=[{"type": "files", "files": [
            {"path": "a.py", "change": "added", "added": 1, "removed": 0},
            {"path": "a-py", "change": "added", "added": 1, "removed": 0}]}])
        self.assertEqual([f["anchor"] for f in report["modules"][0]["files"]], ["file-a-py", "file-a-py-2"])

    def test_slug(self):
        self.assertEqual(slug("  Hello, World!  "), "hello-world")
        self.assertEqual(slug("監査 ✅"), "監査")
        self.assertEqual(slug("!!!"), "item")


if __name__ == "__main__":
    unittest.main()
