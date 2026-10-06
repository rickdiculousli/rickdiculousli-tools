import re
import unittest

from visual_audit_support import details_open, minimal_report, render_html
from audit_report.modules import cap_lines


def partial(*modules):
    return render_html(minimal_report(outcome="partial", blockers=["b"], modules=list(modules)))


def step(kind="read", status="ok", **extra):
    return {"kind": kind, "label": f"{kind} thing", "status": status, **extra}


def file(path, change="modified", added=1, removed=1, **extra):
    return {"path": path, "change": change, "added": added, "removed": removed, **extra}


def element(html, element_id):
    """Return the opening tag of the element with this id."""
    return re.search(rf'<[^>]*id="{element_id}"[^>]*>', html).group(0)


def bar_width(html, element_id):
    row = re.search(rf'id="{element_id}".*?class="bar" style="width:([\d.]+)%', html, flags=re.S)
    return float(row.group(1))


class TimelineTests(unittest.TestCase):
    def test_failed_step_details_open_and_ok_closed(self):
        html = partial({"type": "timeline", "steps": [
            {"kind": "run", "label": "tests", "status": "fail", "detail": "boom"},
            {"kind": "run", "label": "tests again", "detail": "fine"}]})
        self.assertTrue(details_open(html, "step-1"))
        self.assertFalse(details_open(html, "step-2"))

    def test_step_status_attributes(self):
        html = partial({"type": "timeline", "steps": [
            step("run", "fail"), step("run", "fail", resolved=True), step("run", "retry"), step()]})
        self.assertIn('data-status="fail"', element(html, "step-1"))
        self.assertIn('data-status="resolved"', element(html, "step-2"))
        self.assertIn('data-status="retry"', element(html, "step-3"))
        self.assertIn('data-attention', element(html, "step-1"))
        self.assertNotIn('data-attention', element(html, "step-2"))

    def test_read_runs_collapse_within_phase(self):
        reads = [step(phase="Explore") for _ in range(14)]
        html = partial({"type": "timeline", "steps": reads + [step("run", "fail", phase="Explore")]})
        self.assertIn("read × 14", html)
        for n in range(1, 16):
            self.assertIn(f'id="step-{n}"', html)

    def test_short_runs_not_collapsed_and_failures_break_runs(self):
        html = partial({"type": "timeline", "steps": [
            step(), step(), step("edit"), step(), step("read", "fail"), step(), step()]})
        self.assertNotIn("×", html)

    def test_collapse_applies_without_phase(self):
        html = partial({"type": "timeline", "steps": [step("search") for _ in range(3)]})
        self.assertIn("search × 3", html)

    def test_phase_with_failure_open_others_closed(self):
        html = partial({"type": "timeline", "steps": [
            step(phase="Explore"), step("run", "fail", phase="Verify")]})
        self.assertFalse(details_open(html, "phase-explore"))
        self.assertTrue(details_open(html, "phase-verify"))
        self.assertIn("1 failed", html)

    def test_asserted_items_have_class(self):
        html = partial({"type": "timeline", "steps": [
            step("edit"), step("edit", source="observed", evidence="diff applied")]})
        self.assertIn("asserted", element(html, "step-1"))
        self.assertNotIn("asserted", element(html, "step-2"))
        self.assertIn('data-source="observed"', element(html, "step-2"))

    def test_evidence_truncation_marker(self):
        html = partial({"type": "timeline", "steps": [step("run", "fail", evidence="x" * 8412)]})
        self.assertIn("agent-quoted", html)
        self.assertIn("truncated: 2,000 of 8,412 characters shown", html)
        self.assertNotIn("x" * 2001, html)


class FilesTests(unittest.TestCase):
    def test_files_grouped_with_directory_totals(self):
        html = partial({"type": "files", "files": [
            file("src/a.py", added=3, removed=1), file("src/b.py", added=2, removed=0), file("README.md")]})
        self.assertIn("src/", html)
        self.assertIn("2 files · +5 −1", html)

    def test_deletions_and_renames_first(self):
        html = partial({"type": "files", "files": [
            file("src/a.py"), file("src/c.py", "renamed", **{"from": "src/old.py"}), file("src/b.py", "deleted")]})
        order = [html.index(f'id="file-src-{name}-py"') for name in ("b", "c", "a")]
        self.assertEqual(order, sorted(order))
        self.assertIn("src/old.py", html)

    def test_large_directory_collapsed(self):
        files = [file(f"pkg/f{i}.py") for i in range(13)]
        self.assertFalse(details_open(partial({"type": "files", "files": files}), "dir-pkg"))
        self.assertTrue(details_open(partial({"type": "files", "files": files[:12]}), "dir-pkg"))

    def test_directory_with_deletion_starts_open(self):
        files = [file(f"pkg/f{i}.py") for i in range(12)] + [file("pkg/gone.py", "deleted")]
        self.assertTrue(details_open(partial({"type": "files", "files": files}), "dir-pkg"))

    def test_log_scaled_bars(self):
        html = partial({"type": "files", "files": [
            file("big.lock", added=4000, removed=0), file("small.py", added=40, removed=0)]})
        big, small = bar_width(html, "file-big-lock"), bar_width(html, "file-small-py")
        self.assertEqual(big, 100.0)
        self.assertLess(big, 10 * small)

    def test_generated_and_binary_flags(self):
        html = partial({"type": "files", "files": [
            file("dist/app.js", generated=True), file("logo.png", "added", 0, 0, binary=True)]})
        self.assertIn("generated", element(html, "file-dist-app-js"))
        self.assertIn("binary", html)
        row = re.search(r'<li id="file-logo-png".*?</li>', html, flags=re.S).group(0)
        self.assertNotIn('class="bar"', row)

    def test_hunk_caps_and_markers(self):
        long_hunk = "\n".join(f"+line {i}" for i in range(60))
        html = partial({"type": "files", "files": [file("a.py", hunks=[long_hunk] + ["@@ x"] * 11)]})
        self.assertIn("showing 40 of 60 lines", html)
        self.assertIn("2 more hunks not shown", html)
        self.assertNotIn("+line 40", html)

    def test_hunk_markup_is_escaped(self):
        html = partial({"type": "files", "files": [file("a.py", hunks=["+</details><script>x()</script>"])]})
        self.assertIn("&lt;/details&gt;&lt;script&gt;", html)
        self.assertNotIn("<script>x()", html)

    def test_cap_lines(self):
        self.assertEqual(cap_lines("a\nb", 5), ("a\nb", None))
        self.assertEqual(cap_lines("a\nb\nc", 2), ("a\nb", "showing 2 of 3 lines"))


class RunsTests(unittest.TestCase):
    def test_run_failure_classes_rendered(self):
        html = partial({"type": "runs", "runs": [
            {"command": "a", "exit": 1}, {"command": "b", "exit": 1, "expect_fail": True},
            {"command": "c", "exit": 2, "resolved": True}, {"command": "d", "exit": 0}]})
        self.assertIn("exit 1 · unresolved", html)
        self.assertIn("exit 1 · expected failure", html)
        self.assertIn("exit 2 · resolved", html)
        self.assertIn('data-status="fail"', element(html, "run-1"))
        self.assertIn('data-status="expected"', element(html, "run-2"))
        self.assertIn('data-status="ok"', element(html, "run-4"))

    def test_failed_run_excerpt_open(self):
        html = partial({"type": "runs", "runs": [
            {"command": "a", "exit": 1, "excerpt": "boom"}, {"command": "b", "exit": 0, "excerpt": "fine"}]})
        self.assertTrue(details_open(html, "run-1"))
        self.assertFalse(details_open(html, "run-2"))

    def test_excerpt_capped_at_60_lines(self):
        excerpt = "\n".join(f"out {i}" for i in range(75))
        html = partial({"type": "runs", "runs": [{"command": "a", "exit": 0, "excerpt": excerpt}]})
        self.assertIn("showing 60 of 75 lines", html)
        self.assertNotIn("out 60", html)

    def test_suite_bar_counts_and_duration(self):
        html = partial({"type": "runs", "runs": [{"command": "a", "exit": 1, "duration_ms": 1530, "suites": [
            {"name": "unit", "passed": 12, "failed": 1, "skipped": 2}]}]})
        self.assertIn("12 passed · 1 failed · 2 skipped", html)
        self.assertIn("1.5 s", html)
        self.assertIn('class="suite-bar"', html)


class ClaimsTests(unittest.TestCase):
    def claims(self):
        return [{"claim": "verified one", "status": "verified", "source": "observed", "evidence": "ok"},
                {"claim": "unverified one", "status": "unverified"},
                {"claim": "refuted one", "status": "refuted", "evidence": "nope"}]

    def test_claims_sorted_refuted_unverified_verified(self):
        html = partial({"type": "claims", "claims": self.claims()})
        order = [html.index(f'id="claim-{n}"') for n in (3, 2, 1)]
        self.assertEqual(order, sorted(order))

    def test_refuted_claim_open(self):
        html = partial({"type": "claims", "claims": self.claims()})
        self.assertTrue(details_open(html, "claim-3"))
        self.assertFalse(details_open(html, "claim-1"))

    def test_ref_chips_and_back_chips(self):
        html = partial(
            {"type": "timeline", "steps": [step("run")]},
            {"type": "runs", "runs": [{"command": "a", "exit": 0}, {"command": "b", "exit": 0}]},
            {"type": "files", "files": [file("a.py")]},
            {"type": "claims", "claims": [{"claim": "c", "status": "unverified",
                                           "refs": {"runs": [2], "steps": [1], "files": ["a.py"]}}]})
        claim = re.search(r'<li id="claim-1".*?</li>', html, flags=re.S).group(0)
        for target in ("run-2", "step-1", "file-a-py"):
            self.assertIn(f'href="#{target}"', claim)
            row = re.search(rf'<li id="{target}".*?</li>', html, flags=re.S).group(0)
            self.assertIn('href="#claim-1"', row)


if __name__ == "__main__":
    unittest.main()
