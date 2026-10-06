import base64
import re
import unittest

from visual_audit_support import minimal_report, render_html
from audit_report.figures import layer_flow

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><style>body{display:none}</style></svg>'


def figure(kind, **data):
    return render_html(minimal_report(modules=[{"type": "figure", "kind": kind, "alt": "the alt", **data}]))


def nodes(*ids):
    return [{"id": i, "label": i.upper()} for i in ids]


def edges(*pairs):
    return [{"from": a, "to": b} for a, b in pairs]


class FigureTests(unittest.TestCase):
    def test_bar_figure_has_bars_and_hidden_table(self):
        html = figure("bar", bars=[{"label": "parse", "value": 3}, {"label": "render", "value": 9, "status": "fail"}])
        self.assertEqual(html.count('class="fig-bar'), 2)
        self.assertIn("fig-bar status-fail", html)
        hidden = re.search(r'<div class="sr-only">.*?</div>', html, flags=re.S).group(0)
        self.assertIn("<table>", hidden)
        self.assertIn("render", hidden)
        self.assertIn('aria-label="the alt"', html)

    def test_tree_figure_renders_nested_labels_with_status_marks(self):
        tree = {"label": "root", "children": [{"label": "child", "status": "fail",
                                               "children": [{"label": "leaf"}]}]}
        html = figure("tree", tree=tree)
        for label in ("root", "child", "leaf"):
            self.assertIn(f">{label}</text>", html)
        self.assertIn("tree-node status-fail", html)
        self.assertIn("<ul>", re.search(r'<div class="sr-only">.*?</div>', html, flags=re.S).group(0))

    def test_flow_layering(self):
        flow_edges = edges(("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"))
        self.assertEqual(layer_flow(nodes("a", "b", "c", "d"), flow_edges), [["a"], ["b", "c"], ["d"]])
        self.assertEqual(layer_flow(nodes("a", "b", "c", "d"), flow_edges + edges(("a", "d"))),
                         [["a"], ["b", "c"], ["d"]])
        self.assertEqual(layer_flow(nodes("x", "y"), []), [["x", "y"]])

    def test_flow_figure_has_edges_and_labels(self):
        html = figure("flow", flow={"nodes": nodes("a", "b"),
                                    "edges": [{"from": "a", "to": "b", "label": "calls"}]})
        self.assertEqual(html.count('class="flow-edge"'), 1)
        self.assertIn(">calls</text>", html)
        self.assertIn(">A</text>", html)
        self.assertIn("A → B", html)

    def test_custom_svg_round_trips_as_data_uri(self):
        html = figure("custom", svg=SVG)
        source = re.search(r'src="data:image/svg\+xml;base64,([^"]+)"', html).group(1)
        self.assertEqual(base64.b64decode(source).decode("utf-8"), SVG)
        self.assertNotIn("<style>body", html)
        self.assertIn('alt="the alt"', html)

    def test_figure_labels_escaped(self):
        html = figure("bar", bars=[{"label": "<b>x</b>", "value": 1}])
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("<b>x</b>", html)

    def test_figure_section_title(self):
        html = render_html(minimal_report(modules=[{"type": "figure", "kind": "bar", "alt": "a", "title": "Timing",
                                                    "bars": [{"label": "x", "value": 1}]}]))
        self.assertIn("<h2>Timing</h2>", html)


if __name__ == "__main__":
    unittest.main()
