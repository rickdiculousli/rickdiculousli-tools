import re
import unittest

from visual_audit_support import minimal_report, render_html


def timeline(*statuses, **extra):
    steps = []
    for index, status in enumerate(statuses):
        step = {"kind": "run", "label": f"step {index + 1}", "status": status}
        if status.endswith("+resolved"):
            step.update(status=status.split("+")[0], resolved=True)
        steps.append(step)
    return {"type": "timeline", "steps": steps, **extra}


def strip(html):
    match = re.search(r'<svg class="run-strip".*?</svg>', html, flags=re.S)
    return match.group(0) if match else ""


class BandTests(unittest.TestCase):
    def test_contradiction_shown_for_contradicted_pass(self):
        html = render_html(minimal_report(modules=[{"type": "claims", "claims": [
            {"claim": "all good", "status": "refuted"}]}]))
        self.assertIn("contradicted by 1 item", html)

    def test_no_contradiction_for_clean_pass(self):
        self.assertNotIn("contradicted", render_html(minimal_report()))

    def test_title_goal_and_outcome(self):
        html = render_html(minimal_report(title="Ship it", goal="Add the thing"))
        self.assertIn('<header class="band band-pass"', html)
        self.assertIn("Ship it", html)
        self.assertIn("Add the thing", html)

    def test_blockers_and_next_steps_rendered_for_partial(self):
        html = render_html(minimal_report(outcome="partial", blockers=["codex missing"],
                                          next_steps=["install codex"]))
        self.assertIn('band-partial', html)
        self.assertIn("codex missing", html)
        self.assertIn("install codex", html)

    def test_not_reported_counts_with_empty_modules(self):
        html = render_html(minimal_report())
        self.assertEqual(html.count("not reported"), 3)
        self.assertIn("Nothing needs attention", html)

    def test_failure_counts_split(self):
        html = render_html(minimal_report(outcome="partial", blockers=["b"], modules=[
            {"type": "files", "files": [{"path": "a", "change": "added", "added": 3, "removed": 0}]},
            {"type": "runs", "runs": [
                {"command": "a", "exit": 1}, {"command": "b", "exit": 1},
                {"command": "c", "exit": 1, "resolved": True},
                {"command": "d", "exit": 1, "expect_fail": True}]},
            timeline("fail"),
        ]))
        self.assertIn("2 failed runs", html)
        self.assertIn("1 resolved", html)
        self.assertIn("1 expected", html)
        self.assertIn("1 failed step", html)
        self.assertRegex(html, r'<a class="count" href="#attention">2 failed runs')
        self.assertRegex(html, r'<a class="count" href="#module-1">1 file')
        self.assertRegex(html, r'<a class="count" href="#module-2">4 commands')

    def test_asserted_count(self):
        html = render_html(minimal_report(modules=[{"type": "runs", "runs": [
            {"command": "a", "exit": 0}, {"command": "b", "exit": 0, "source": "observed", "evidence": "ok"}]}]))
        self.assertIn("1 of 2 asserted", html)

    def test_all_asserted_banner(self):
        html = render_html(minimal_report(modules=[{"type": "runs", "runs": [{"command": "a", "exit": 0}]}]))
        self.assertIn('class="banner-asserted"', html)
        observed = minimal_report(modules=[{"type": "runs", "runs": [
            {"command": "a", "exit": 0, "source": "observed", "evidence": "ok"}]}])
        self.assertNotIn('class="banner-asserted"', render_html(observed))

    def test_context_header_and_rendered_at(self):
        html = render_html(minimal_report(context={"branch": "feature/x", "head_commit": "abc1234"}))
        self.assertIn("feature/x", html)
        self.assertIn("abc1234", html)
        self.assertIn("2026-01-01T00:00:00Z", html)

    def test_attention_links_to_anchors(self):
        html = render_html(minimal_report(outcome="partial", blockers=["b"], modules=[
            {"type": "runs", "runs": [{"command": "pytest", "exit": 1}]},
            {"type": "claims", "claims": [{"claim": "works", "status": "unverified"}]}]))
        attention = re.search(r'<section id="attention".*?</section>', html, flags=re.S).group(0)
        self.assertIn('href="#run-1"', attention)
        self.assertIn('href="#claim-1"', attention)
        self.assertNotIn("Nothing needs attention", attention)

    def test_strip_marks_and_summary(self):
        html = render_html(minimal_report(outcome="partial", blockers=["b"],
                                          modules=[timeline("ok", "ok", "fail", "retry", "ok")]))
        self.assertEqual(strip(html).count('class="strip-mark'), 5)
        self.assertIn("5 steps: 1 failed (step 3)", html)

    def test_strip_buckets_above_120(self):
        statuses = ["ok"] * 300
        statuses[150] = "fail"
        html = render_html(minimal_report(outcome="partial", blockers=["b"], modules=[timeline(*statuses)]))
        marks = strip(html)
        self.assertLessEqual(marks.count('class="strip-mark'), 120)
        self.assertEqual(marks.count("mark-fail"), 1)
        self.assertIn('href="#step-151"', marks)

    def test_strip_only_failures_focusable(self):
        html = render_html(minimal_report(outcome="partial", blockers=["b"],
                                          modules=[timeline("ok", "warn", "fail", "retry")]))
        marks = strip(html)
        self.assertEqual(marks.count("<a "), 2)
        self.assertIn('href="#step-2"', marks)
        self.assertIn('href="#step-3"', marks)
        self.assertEqual(marks.count('aria-hidden="true"'), 2)

    def test_resolved_fail_step_is_not_a_failure_mark(self):
        html = render_html(minimal_report(modules=[timeline("fail+resolved")]))
        marks = strip(html)
        self.assertIn("mark-ok", marks)
        self.assertNotIn("<a ", marks)
        self.assertIn("1 step: 0 failed", html)

    def test_strip_links_are_named_and_reachable(self):
        html = render_html(minimal_report(outcome="partial", blockers=["b"], modules=[timeline("ok", "fail")]))
        marks = strip(html)
        self.assertNotIn('role="img"', marks)
        self.assertIn('role="group"', marks)
        self.assertIn('aria-label="Step 2: failed"', marks)
        self.assertIn('class="strip-hit"', marks)

    def test_legend_explains_marks(self):
        html = render_html(minimal_report())
        legend = re.search(r'<details class="legend">.*?</details>', html, flags=re.S).group(0)
        for text in ("failed", "warning", "expected failure", "agent-asserted"):
            self.assertIn(text, legend)

    def test_all_asserted_flag_on_main(self):
        html = render_html(minimal_report(modules=[{"type": "runs", "runs": [{"command": "a", "exit": 0}]}]))
        self.assertIn('<main id="report" data-all-asserted>', html)
        self.assertIn('<main id="report">', render_html(minimal_report()))

    def test_filters_only_hide_item_rows(self):
        css = render_html(minimal_report())
        self.assertNotIn(".module li:not(", css)

    def test_no_strip_without_timeline(self):
        self.assertNotIn("<svg class=\"run-strip\"", render_html(minimal_report()))


if __name__ == "__main__":
    unittest.main()
