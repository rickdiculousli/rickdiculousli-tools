import copy
import unittest

from visual_audit_support import minimal_report
from audit_report import schema

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>'


def paths(errors):
    return [error.split(":", 1)[0] for error in errors]


class SchemaTests(unittest.TestCase):
    def assertErrorAt(self, data, path):
        errors = schema.validate(data)
        self.assertIn(path, paths(errors), errors)

    def test_minimal_report_is_valid(self):
        self.assertEqual(schema.validate(minimal_report()), [])

    def test_collects_multiple_errors_with_paths(self):
        data = minimal_report(version=2, outcome="done")
        data["modules"] = [{"type": "runs", "runs": [{"command": "x", "exit": "0"}]}]
        errors = schema.validate(data)
        self.assertTrue(any(e.startswith("version:") for e in errors))
        self.assertTrue(any(e.startswith("outcome:") for e in errors))
        self.assertTrue(any(e.startswith("modules[0].runs[0].exit:") for e in errors))

    def test_top_level_must_be_object(self):
        self.assertEqual(paths(schema.validate([])), ["$"])

    def test_required_top_level_fields(self):
        for key in ("version", "title", "goal", "outcome", "modules"):
            with self.subTest(key=key):
                data = minimal_report()
                del data[key]
                self.assertErrorAt(data, key)

    def test_unknown_top_level_key(self):
        self.assertErrorAt(minimal_report(extra=1), "extra")

    def test_unknown_module_type(self):
        self.assertErrorAt(minimal_report(modules=[{"type": "chart"}]), "modules[0].type")

    def test_unknown_item_key(self):
        data = minimal_report(modules=[{"type": "runs", "runs": [{"command": "x", "exit": 0, "colour": "red"}]}])
        self.assertErrorAt(data, "modules[0].runs[0].colour")

    def test_unknown_context_key(self):
        self.assertErrorAt(minimal_report(context={"repo": "r", "weather": "sunny"}), "context.weather")

    def test_blockers_required_unless_pass(self):
        self.assertErrorAt(minimal_report(outcome="partial"), "blockers")
        self.assertErrorAt(minimal_report(outcome="blocked", blockers=[]), "blockers")
        self.assertEqual(schema.validate(minimal_report(outcome="blocked", blockers=["no network"])), [])

    def test_observed_requires_evidence(self):
        data = minimal_report(modules=[{"type": "runs", "runs": [{"command": "x", "exit": 0, "source": "observed"}]}])
        self.assertErrorAt(data, "modules[0].runs[0].evidence")
        data["modules"][0]["runs"][0]["evidence"] = "   "
        self.assertErrorAt(data, "modules[0].runs[0].evidence")

    def test_verified_claim_must_be_observed(self):
        data = minimal_report(modules=[{"type": "claims", "claims": [{"claim": "ok", "status": "verified"}]}])
        self.assertErrorAt(data, "modules[0].claims[0].source")

    def test_refs_must_resolve(self):
        data = minimal_report(modules=[
            {"type": "runs", "runs": [{"command": "x", "exit": 0}]},
            {"type": "claims", "claims": [{"claim": "c", "status": "unverified",
                                           "refs": {"runs": [3], "steps": [1], "files": ["nope.py"]}}]},
        ])
        errors = paths(schema.validate(data))
        self.assertIn("modules[1].claims[0].refs.runs[0]", errors)
        self.assertIn("modules[1].claims[0].refs.steps[0]", errors)
        self.assertIn("modules[1].claims[0].refs.files[0]", errors)

    def test_refs_resolve_across_modules(self):
        data = minimal_report(modules=[
            {"type": "timeline", "steps": [{"kind": "read", "label": "a"}]},
            {"type": "timeline", "steps": [{"kind": "read", "label": "b"}]},
            {"type": "runs", "runs": [{"command": "x", "exit": 0}]},
            {"type": "files", "files": [{"path": "a.py", "change": "added", "added": 1, "removed": 0}]},
            {"type": "claims", "claims": [{"claim": "c", "status": "unverified",
                                           "refs": {"runs": [1], "steps": [2], "files": ["a.py"]}}]},
        ])
        self.assertEqual(schema.validate(data), [])

    def test_flow_rejects_unknown_nodes_and_cycles(self):
        flow = {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}, {"from": "a", "to": "z"}]}
        data = minimal_report(modules=[{"type": "figure", "kind": "flow", "alt": "x", "flow": flow}])
        errors = schema.validate(data)
        self.assertTrue(any("cycle" in e for e in errors), errors)
        self.assertIn("modules[0].flow.edges[2].to", paths(errors))

    def test_duplicate_file_paths_rejected(self):
        item = {"path": "a.py", "change": "modified", "added": 1, "removed": 1}
        data = minimal_report(modules=[{"type": "files", "files": [item]}, {"type": "files", "files": [dict(item)]}])
        self.assertErrorAt(data, "modules[1].files[0].path")

    def test_duplicate_flow_node_ids_rejected(self):
        flow = {"nodes": [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}], "edges": []}
        data = minimal_report(modules=[{"type": "figure", "kind": "flow", "alt": "x", "flow": flow}])
        self.assertErrorAt(data, "modules[0].flow.nodes[1].id")

    def test_renamed_requires_from(self):
        data = minimal_report(modules=[{"type": "files", "files": [
            {"path": "b.py", "change": "renamed", "added": 0, "removed": 0}]}])
        self.assertErrorAt(data, "modules[0].files[0].from")

    def test_resolved_only_on_failures(self):
        data = minimal_report(modules=[
            {"type": "timeline", "steps": [{"kind": "run", "label": "a", "resolved": True}]},
            {"type": "runs", "runs": [{"command": "x", "exit": 0, "resolved": True}]},
        ])
        errors = paths(schema.validate(data))
        self.assertIn("modules[0].steps[0].resolved", errors)
        self.assertIn("modules[1].runs[0].resolved", errors)

    def test_resolved_on_expected_failure_rejected(self):
        data = minimal_report(modules=[{"type": "runs", "runs": [
            {"command": "x", "exit": 1, "expect_fail": True, "resolved": True}]}])
        self.assertErrorAt(data, "modules[0].runs[0].resolved")

    def test_resolved_allowed_on_failures(self):
        data = minimal_report(modules=[
            {"type": "timeline", "steps": [{"kind": "run", "label": "a", "status": "fail", "resolved": True}]},
            {"type": "runs", "runs": [{"command": "x", "exit": 1, "resolved": True},
                                      {"command": "y", "exit": 0, "expect_fail": True, "resolved": True}]},
        ])
        self.assertEqual(schema.validate(data), [])

    def test_figure_requires_alt_and_matching_data(self):
        self.assertErrorAt(minimal_report(modules=[{"type": "figure", "kind": "tree", "alt": "x"}]), "modules[0].tree")
        self.assertErrorAt(minimal_report(modules=[{"type": "figure", "kind": "bar",
                                                    "bars": [{"label": "a", "value": 1}]}]), "modules[0].alt")
        self.assertErrorAt(minimal_report(modules=[{"type": "figure", "kind": "bar", "alt": "x",
                                                    "bars": [{"label": "a", "value": 1}],
                                                    "tree": {"label": "t"}}]), "modules[0].tree")

    def test_custom_svg_requires_xmlns(self):
        self.assertErrorAt(minimal_report(modules=[{"type": "figure", "kind": "custom", "alt": "x",
                                                    "svg": "<svg></svg>"}]), "modules[0].svg")
        self.assertEqual(schema.validate(minimal_report(modules=[
            {"type": "figure", "kind": "custom", "alt": "x", "svg": SVG}])), [])

    def test_tree_is_validated_recursively(self):
        tree = {"label": "root", "children": [{"label": "a", "status": "bogus"}]}
        data = minimal_report(modules=[{"type": "figure", "kind": "tree", "alt": "x", "tree": tree}])
        self.assertErrorAt(data, "modules[0].tree.children[0].status")

    def test_negative_counts_rejected(self):
        data = minimal_report(modules=[{"type": "files", "files": [
            {"path": "a", "change": "added", "added": -1, "removed": 0}]}])
        self.assertErrorAt(data, "modules[0].files[0].added")

    def test_non_finite_numbers_rejected(self):
        for value in (float("nan"), float("inf")):
            data = minimal_report(modules=[{"type": "figure", "kind": "bar", "alt": "x",
                                            "bars": [{"label": "a", "value": value}]}])
            self.assertErrorAt(data, "modules[0].bars[0].value")

    def test_booleans_are_not_integers(self):
        data = minimal_report(modules=[{"type": "runs", "runs": [{"command": "x", "exit": True}]}])
        self.assertErrorAt(data, "modules[0].runs[0].exit")

    def test_load_applies_defaults_without_mutating_input(self):
        data = minimal_report(modules=[
            {"type": "timeline", "steps": [{"kind": "read", "label": "a"}]},
            {"type": "runs", "runs": [{"command": "x", "exit": 0}]},
        ])
        original = copy.deepcopy(data)
        report = schema.load(data)
        self.assertEqual(data, original)
        self.assertEqual(report["modules"][0]["steps"][0]["status"], "ok")
        self.assertEqual(report["modules"][0]["steps"][0]["source"], "asserted")
        self.assertEqual(report["modules"][1]["runs"][0]["source"], "asserted")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["context"], {})

    def test_load_raises_with_all_errors(self):
        with self.assertRaises(schema.ReportError) as caught:
            schema.load(minimal_report(version=2, outcome="x"))
        self.assertEqual(len(caught.exception.errors), 2)


if __name__ == "__main__":
    unittest.main()
