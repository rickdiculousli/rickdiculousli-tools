# Visual Audit Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `visual-audit` plugin whose `audit-report` skill renders agent-written report JSON into one self-contained, show-don't-tell HTML audit page.

**Architecture:** A Python standard-library package inside the skill validates the JSON (`schema`), computes derived state such as failures, contradictions, and attention items (`derive`), renders modules and SVG figures (`modules`, `figures`), and assembles one page from inlined templates (`page`). A thin CLI writes output into a self-ignoring `.audit/` folder. Packaging follows the repository's generator and lifecycle verifier.

**Tech Stack:** Python 3.10+ standard library (`json`, `html`, `string.Template`, `base64`, `argparse`, `unittest`), hand-written CSS and a small optional JS file, Claude Code and Codex CLIs for lifecycle verification.

**Spec:** [docs/superpowers/specs/2026-10-05-visual-audit-design.md](../specs/2026-10-05-visual-audit-design.md)

## Global Constraints

- Plugin `visual-audit`, version `0.1.0`; skill `audit-report`; all files under `plugins/visual-audit/skills/audit-report/`.
- Python 3.10+ standard library only; no network at render or view time; no web fonts; CSS and JS inlined into the HTML.
- Report `version` must be `1`; outcome enum `pass`, `partial`, `blocked`; `blockers` required when outcome is not `pass`.
- `source` defaults to `asserted`; `observed` requires non-empty `evidence`; a `verified` claim must be `observed`.
- Unknown module types and unknown keys are validation errors; validation reports every error as `<json path>: <message>` and nothing is written on failure.
- Truncation limits: evidence 2,000 characters; hunks 40 lines each and 10 per file; run excerpts 60 lines; every marker states how much was hidden.
- Run strip buckets above 120 steps; directories over 12 files start collapsed.
- Agent text is always HTML-escaped; custom SVG is embedded byte-for-byte as `<img src="data:image/svg+xml;base64,…">`, never sanitised or inlined.
- Page must be fully readable with JavaScript disabled; filter buttons exist only when JS runs.
- Default output `.audit/` under cwd, with `.audit/.gitignore` containing `*`; HTML next to JSON with the same stem; `-o PATH` overrides.
- Do not claim model-driven skill use, GUI, or remote checks unless performed.

## Review Focus

- Non-ASCII titles, paths, and commands (CJK, emoji) must render intact and be written as UTF-8 — test in Task 3.
- A report with `"modules": []` and outcome `pass` must render with "not reported" counts and "Nothing needs attention" — test in Task 4.
- Duplicate file paths in `files` modules or duplicate flow node ids must be validation errors, since refs and anchors depend on uniqueness — test in Task 1.
- Diff hunks and excerpts containing `</details>` or `<script>` must appear as text and not break structure — test in Task 5.
- Invalid JSON, a UTF-8 BOM, or a top-level array must exit 1 with a readable message and write nothing — test in Task 3.

## Shared test support

`tests/visual_audit_support.py` (created in Task 1) inserts
`plugins/visual-audit/skills/audit-report/scripts` on `sys.path` and provides:

- `minimal_report(**overrides) -> dict` — `{"version": 1, "title": "T", "goal": "G", "outcome": "pass", "modules": []}` updated with overrides.
- `render_html(report: dict) -> str` — `audit_report.render_report(report, rendered_at="2026-01-01T00:00:00Z")` (available from Task 3).

All test files import it as `from visual_audit_support import minimal_report, render_html`.

---

### Task 1: Plugin skeleton and schema validation

**Files:**
- Create: `plugins/visual-audit/plugin.json`
- Create: `plugins/visual-audit/skills/audit-report/scripts/audit_report/__init__.py`
- Create: `plugins/visual-audit/skills/audit-report/scripts/audit_report/schema.py`
- Create: `tests/visual_audit_support.py`
- Test: `tests/test_visual_audit_schema.py`

**Interfaces:**
- Produces: `schema.ReportError(Exception)` with attribute `errors: list[str]`.
- Produces: `schema.validate(data: object) -> list[str]` — every error, as `"<path>: <message>"`, with path like `modules[2].runs[0].exit`; top-level errors use path `$`.
- Produces: `schema.normalize(data: dict) -> dict` — deep copy with defaults applied (`source: "asserted"`, step `status: "ok"`, missing optional lists as `[]`). Call only on valid data.
- Produces: `schema.load(data: object) -> dict` — `validate` then `normalize`; raises `ReportError` if any errors.

- [ ] **Step 1: Write the portable manifest** `plugins/visual-audit/plugin.json` with `$schema` as in existing plugins, `name` `visual-audit`, `version` `0.1.0`, description "Renders agent-written session reports into a visual HTML audit page.", author Rick Li, keywords `["audit", "report", "visualization"]`.

- [ ] **Step 2: Write the failing tests** in `tests/test_visual_audit_schema.py`, one test method per rule, each asserting the exact path appears in `validate(...)`:

```python
def test_minimal_report_is_valid(self):
    self.assertEqual(schema.validate(minimal_report()), [])

def test_collects_multiple_errors_with_paths(self):
    data = minimal_report(version=2, outcome="done")
    data["modules"] = [{"type": "runs", "runs": [{"command": "x", "exit": "0"}]}]
    errors = schema.validate(data)
    self.assertIn("$.version", " ".join(errors))
    self.assertIn("$.outcome", " ".join(errors))
    self.assertTrue(any(e.startswith("modules[0].runs[0].exit:") for e in errors))
```

Further tests (each: build a report, assert the named path is in the errors):
`test_top_level_must_be_object` (a list → `$`), `test_unknown_top_level_key`,
`test_unknown_module_type` (`modules[0].type`), `test_unknown_item_key`,
`test_blockers_required_unless_pass` (`partial` without blockers → `$.blockers`; with `[]` also error),
`test_observed_requires_evidence` (`modules[0].runs[0].evidence`),
`test_verified_claim_must_be_observed` (`modules[0].claims[0].source`),
`test_refs_must_resolve` (claim ref `{"runs": [3]}` with 1 run → `modules[0].claims[0].refs.runs[0]`; file ref to unknown path errors too),
`test_flow_rejects_unknown_nodes_and_cycles`,
`test_duplicate_file_paths_rejected` (same path in two `files` modules → error naming the second),
`test_duplicate_flow_node_ids_rejected`,
`test_renamed_requires_from`, `test_resolved_only_on_failures` (`resolved` on an `ok` step and on a run with exit 0 without `expect_fail` → errors),
`test_figure_requires_alt_and_matching_data` (`kind: tree` without `tree` → error),
`test_negative_counts_rejected` (`added: -1`),
`test_load_applies_defaults` (asserts `source == "asserted"` and step `status == "ok"` after `load`, and `ReportError.errors` on invalid input).

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_schema -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'audit_report'`.

- [ ] **Step 4: Implement `schema.py`** — a table of allowed keys and types per item kind drives one recursive checker. Ref numbering is 1-based across the whole report in document order (all timeline steps concatenated; likewise runs). Flow cycle detection: depth-first search with an on-stack set. `__init__.py` is empty in this task.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_visual_audit_schema -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add plugins/visual-audit tests/visual_audit_support.py tests/test_visual_audit_schema.py
git commit -m "feat(visual-audit): validate report schema"
```

### Task 2: Derived state

**Files:**
- Create: `plugins/visual-audit/skills/audit-report/scripts/audit_report/derive.py`
- Test: `tests/test_visual_audit_derive.py`

**Interfaces:**
- Consumes: `schema.load`.
- Produces: `derive.derive(report: dict) -> Derived`, which also annotates items in place on the normalized report: every step, run, and claim gets `"n"` (1-based global number) and `"anchor"` (`step-N`, `run-N`, `claim-N`); files get `"anchor"` `file-<slug>`; runs get `"failure"` in `{"unresolved", "resolved", "expected", "ok"}`; steps get `"failure"` in `{"unresolved", "resolved", "ok"}` (`fail`/`warn` count as failure; `retry` does not).
- Produces dataclasses:

```python
@dataclass
class AttentionItem:
    kind: str     # "run", "step", "refuted", "unverified", "deleted", "truncated"
    label: str
    anchor: str

@dataclass
class Derived:
    runs: dict[str, int]          # keys unresolved, resolved, expected (counts)
    steps: dict[str, int]         # keys unresolved, resolved
    asserted: int
    countable: int
    all_asserted: bool            # countable > 0 and asserted == countable
    files: int | None             # None when no files module ("not reported")
    lines_added: int | None
    lines_removed: int | None
    commands: int | None          # None when no runs module
    contradictions: list[AttentionItem]
    attention: list[AttentionItem]
    cited_by: dict[str, list[str]]  # target anchor -> citing claim anchors
    all_steps: list[dict]           # annotated steps in document order
```

- Produces: `derive.slug(text: str) -> str` (lowercase, non-alphanumerics to `-`, collapsed, stripped; used by anchors).

- [ ] **Step 1: Write the failing tests**

```python
def test_run_failure_classes(self):
    report = load(minimal_report(modules=[{"type": "runs", "runs": [
        {"command": "a", "exit": 1},
        {"command": "b", "exit": 1, "expect_fail": True},
        {"command": "c", "exit": 0, "expect_fail": True},
        {"command": "d", "exit": 2, "resolved": True},
        {"command": "e", "exit": 0}]}]))
    d = derive(report)
    self.assertEqual([r["failure"] for r in report["modules"][0]["runs"]],
                     ["unresolved", "expected", "unresolved", "resolved", "ok"])
    self.assertEqual(d.runs, {"unresolved": 2, "resolved": 1, "expected": 1})
```

Further tests: `test_step_failures_and_retry`, `test_contradiction_when_pass_has_unresolved_or_refuted_or_unverified` (three items → three contradictions; none for `partial`), `test_asserted_count_excludes_read_search_think`, `test_all_asserted_flag`, `test_missing_modules_are_none` (`files`, `commands`, `lines_added` are `None` with `modules: []`; an empty `files` list gives `0`), `test_attention_order_and_anchors` (unresolved runs, unresolved steps, refuted, unverified, deleted files, truncated evidence over 2,000 chars — in that order, each with its anchor), `test_cited_by_back_references`, `test_global_numbering_across_modules` (two timeline modules → steps 1..N continuous), `test_slug`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_derive -v`
Expected: ERROR — `cannot import name 'derive'`.

- [ ] **Step 3: Implement `derive.py`** to satisfy the interface above. Countable items for `asserted`: runs, claims, files, and steps of kind `edit`, `run`, or `other`. Duplicate file slugs get `-2`, `-3` suffixes in document order.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_visual_audit_derive -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/visual-audit/skills/audit-report/scripts/audit_report/derive.py tests/test_visual_audit_derive.py
git commit -m "feat(visual-audit): derive failures, contradictions, and attention"
```

### Task 3: Page assembly and CLI

**Files:**
- Create: `plugins/visual-audit/skills/audit-report/scripts/audit_report/page.py`
- Create: `plugins/visual-audit/skills/audit-report/scripts/audit_report/modules.py` (dispatch stub only)
- Create: `plugins/visual-audit/skills/audit-report/scripts/render_report.py`
- Create: `plugins/visual-audit/skills/audit-report/templates/page.html`, `report.css`, `report.js` (minimal placeholders replaced in Tasks 4–8)
- Modify: `plugins/visual-audit/skills/audit-report/scripts/audit_report/__init__.py`
- Test: `tests/test_visual_audit_cli.py`

**Interfaces:**
- Consumes: `schema.load`, `derive.derive`.
- Produces: `audit_report.render_report(data: object, rendered_at: str) -> str` — full HTML; raises `schema.ReportError`.
- Produces: `modules.render_module(module: dict, derived: Derived) -> str` — dispatch on `module["type"]`; this task returns `<section class="module" data-type="…">` with the escaped title only. Later tasks fill each type.
- Produces: `page.render_page(report: dict, derived: Derived, rendered_at: str) -> str` — fills `page.html` (`$title`, `$css`, `$js`, `$band`, `$attention`, `$modules`, `$rendered_at`) via `string.Template.substitute`; CSS and JS are read from `templates/` and inlined. `$band` and `$attention` are empty strings until Task 4.
- Produces: `render_report.main(argv: list[str] | None = None) -> int` — `render_report.py REPORT.json [-o OUT.html]`. Output defaults to `REPORT.json` with `.html` suffix. Creates `.gitignore` containing `*\n` in the HTML's parent directory when that directory is named `.audit` and the file is absent. `rendered_at` is the current UTC time in ISO 8601 seconds.

- [ ] **Step 1: Write the failing tests**

```python
def test_renders_and_writes_gitignore(self):
    audit = self.tmp / ".audit"; audit.mkdir()
    source = audit / "r.json"; source.write_text(json.dumps(minimal_report()))
    self.assertEqual(main([str(source)]), 0)
    self.assertTrue((audit / "r.html").read_text(encoding="utf-8").startswith("<!doctype html>"))
    self.assertEqual((audit / ".gitignore").read_text(), "*\n")
```

Further tests: `test_output_override` (`-o` path written, default not), `test_invalid_report_exits_1_and_writes_nothing` (stderr lists each error path), `test_bad_json_bom_and_array_exit_1` (invalid JSON, BOM-prefixed file, top-level array: exit 1, readable stderr, no HTML), `test_unwritable_output_exits_1`, `test_title_is_escaped` (`<script>alert(1)</script>` title appears as `&lt;script&gt;` and no raw `<script>alert`), `test_unicode_round_trip` (title `"監査 ✅"` present in UTF-8 file), `test_deterministic` (`render_html` twice → identical), `test_self_contained` (no `http://` or `https://` and no `<link` or `src="http` in output; CSS and JS inlined).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_cli -v`
Expected: ERROR — import failure for `render_report`.

- [ ] **Step 3: Implement** `page.py`, `modules.py` stub, `__init__.render_report`, `render_report.py` (it inserts its own directory on `sys.path` so `python3 <skill-dir>/scripts/render_report.py` works from any cwd), and the placeholder templates. Read the JSON with `encoding="utf-8-sig"` so a BOM is accepted. Write output only after rendering succeeds.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_visual_audit_cli -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/visual-audit tests/test_visual_audit_cli.py
git commit -m "feat(visual-audit): render page and write self-ignoring output"
```

### Task 4: Verdict band, attention list, and run strip

**Files:**
- Modify: `plugins/visual-audit/skills/audit-report/scripts/audit_report/page.py`
- Create: `plugins/visual-audit/skills/audit-report/scripts/audit_report/figures.py` (`run_strip` only)
- Test: `tests/test_visual_audit_band.py`

**Interfaces:**
- Consumes: `Derived`, `AttentionItem`.
- Produces: `page.render_band(report: dict, derived: Derived, rendered_at: str) -> str` and `page.render_attention(derived: Derived) -> str`.
- Produces: `figures.run_strip(steps: list[dict]) -> str` — one `<svg class="run-strip">` plus a `<p class="sr-only">` text summary; returns `""` for no steps.
- Produces markup contracts used by CSS and JS (Task 8): status marks are `<span class="mark mark-{ok|fail|warn|expected|asserted}" aria-hidden="true">` followed by a visually hidden text label; counts are `<a class="count" href="#…">`; band root `<header class="band band-{outcome}">`.

- [ ] **Step 1: Write the failing tests**

```python
def test_contradiction_shown_for_contradicted_pass(self):
    html = render_html(minimal_report(modules=[{"type": "claims", "claims": [
        {"claim": "all good", "status": "refuted"}]}]))
    self.assertIn("contradicted by 1 item", html)
```

Further tests: `test_blockers_and_next_steps_rendered_for_partial`, `test_not_reported_counts_with_empty_modules` (`modules: []` → "not reported" for files and commands, and "Nothing needs attention"), `test_failure_counts_split` (text "2 failed runs" and "1 resolved" and "1 expected"), `test_all_asserted_banner`, `test_context_header_and_rendered_at`, `test_attention_links_to_anchors` (each item's `href="#run-1"` etc.), `test_strip_marks_and_summary` (5 steps → 5 marks; summary text "5 steps: 1 failed (step 3)"), `test_strip_buckets_above_120` (300 steps → at most 120 marks, worst status kept), `test_strip_only_failures_focusable` (`<a` only around fail/warn marks; others `aria-hidden="true"`), `test_no_strip_without_timeline`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_band -v`
Expected: FAIL — strings absent.

- [ ] **Step 3: Implement** band, attention list, and strip. Bucketing: `size = ceil(len(steps) / 120)`; worst status order `fail > warn > retry > ok`; a bucket links to its worst step's anchor. Mark minimum width 3px in the SVG viewBox units; the SVG scales to width 100%.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_visual_audit_band -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/visual-audit tests/test_visual_audit_band.py
git commit -m "feat(visual-audit): verdict band, attention list, and run strip"
```

### Task 5: Timeline and files modules

**Files:**
- Modify: `plugins/visual-audit/skills/audit-report/scripts/audit_report/modules.py`
- Test: `tests/test_visual_audit_modules.py`

**Interfaces:**
- Consumes: annotated items from `derive` (`n`, `anchor`, `failure`).
- Produces: `modules.render_timeline(module, derived) -> str`, `modules.render_files(module, derived) -> str`.
- Produces shared helpers used by Task 6: `modules.item_attrs(item: dict, status: str) -> str` (returns `id`, `data-status`, `data-source`, and class `asserted` when `source == "asserted"`), `modules.evidence_block(item: dict, open_: bool) -> str` (labelled "agent-quoted", truncated with "truncated: N of M characters shown"), `modules.cap_lines(text: str, limit: int) -> tuple[str, str | None]` (text and marker like "showing 40 of 312 lines").

- [ ] **Step 1: Write the failing tests**

```python
def test_failed_step_details_open_and_ok_closed(self):
    html = render_html(minimal_report(outcome="partial", blockers=["x"], modules=[
        {"type": "timeline", "steps": [
            {"kind": "run", "label": "tests", "status": "fail", "detail": "boom"},
            {"kind": "run", "label": "tests again", "detail": "fine"}]}]))
    self.assertRegex(html, r'id="step-1"[^>]*>.*?<details open', flags=re.S)
    self.assertNotRegex(html, r'id="step-2"[^>]*>.*?<details open.*?id="', flags=re.S)
```

Further tests: `test_read_runs_collapse_within_phase` (14 consecutive ok reads → "read × 14"; a fail breaks the run), `test_phase_with_failure_open_others_closed`, `test_asserted_items_have_class`, `test_files_grouped_with_directory_totals`, `test_deletions_and_renames_first`, `test_large_directory_collapsed` (13 files → closed `<details>`), `test_log_scaled_bars` (a 4,000-line file's bar width is less than 10× a 40-line file's), `test_generated_and_binary_flags`, `test_hunk_caps_and_markers` (60-line hunk → "showing 40 of 60 lines"; 12 hunks → "2 more hunks not shown"), `test_hunk_markup_is_escaped` (hunk containing `</details><script>` appears escaped), `test_evidence_truncation_marker`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_modules -v`
Expected: FAIL.

- [ ] **Step 3: Implement** both renderers. Bar width: `log1p(n) / log1p(max_n) * 100%`, added and removed drawn as two adjacent spans. Steps with no phase belong to an implicit unnamed phase rendered without a `<details>` wrapper. Named phases get `id="phase-<slug>"` (using `derive.slug`, suffixed `-2`… on collisions) and a summary line of status counts.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_visual_audit_modules -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/visual-audit tests/test_visual_audit_modules.py
git commit -m "feat(visual-audit): timeline and file change modules"
```

### Task 6: Runs and claims modules with cross-links

**Files:**
- Modify: `plugins/visual-audit/skills/audit-report/scripts/audit_report/modules.py`
- Test: `tests/test_visual_audit_modules.py` (add tests)

**Interfaces:**
- Consumes: `item_attrs`, `evidence_block`, `cap_lines` (Task 5); `Derived.cited_by`.
- Produces: `modules.render_runs(module, derived) -> str`, `modules.render_claims(module, derived) -> str`, `modules.backref_chips(anchor: str, derived) -> str` (also called from timeline and files rows so targets show "cited by claim N").

- [ ] **Step 1: Write the failing tests:** `test_run_failure_classes_rendered` (badge text "exit 1 · unresolved", "expected failure", "resolved"), `test_failed_run_excerpt_open`, `test_excerpt_capped_at_60_lines`, `test_suite_bar_counts` ("12 passed · 1 failed · 2 skipped"), `test_claims_sorted_refuted_unverified_verified`, `test_ref_chips_and_back_chips` (claim 1 refs run 2 → `href="#run-2"` in the claim, and `href="#claim-1"` near `id="run-2"`), `test_refuted_claim_open`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_modules -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement** both renderers and back-chips; wire back-chips into timeline and files rows.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_visual_audit_modules -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/visual-audit tests/test_visual_audit_modules.py
git commit -m "feat(visual-audit): runs and claims modules with cross-links"
```

### Task 7: Figure module

**Files:**
- Modify: `plugins/visual-audit/skills/audit-report/scripts/audit_report/figures.py`
- Modify: `plugins/visual-audit/skills/audit-report/scripts/audit_report/modules.py` (dispatch `figure`)
- Test: `tests/test_visual_audit_figures.py`

**Interfaces:**
- Produces: `figures.render_figure(module: dict) -> str` returning `<figure>` with the SVG or `<img>`, a `<figcaption>` from `title`, and (for built-in kinds) a `<div class="sr-only">` list or table of the data.
- Produces: `figures.layer_flow(nodes: list[dict], edges: list[dict]) -> list[list[str]]` — node ids per layer, longest-path layering, input order within a layer.

- [ ] **Step 1: Write the failing tests:** `test_bar_figure_has_bars_and_hidden_table`, `test_tree_figure_renders_nested_labels_with_status_marks`, `test_flow_layering` (`a→b, a→c, b→d, c→d` → `[["a"], ["b", "c"], ["d"]]`; a skip edge `a→d` keeps `d` in layer 2), `test_flow_figure_has_edges_and_labels`, `test_custom_svg_round_trips_as_data_uri` (base64-decoding the `src` returns the exact input bytes, the raw `<svg` is not inlined, and `alt` is set), `test_figure_labels_escaped`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_figures -v`
Expected: FAIL.

- [ ] **Step 3: Implement** the three layouts with fixed geometry constants (row height, layer spacing) so output is deterministic; flow edges are straight lines or simple elbows, no crossing minimisation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_visual_audit_figures -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/visual-audit tests/test_visual_audit_figures.py
git commit -m "feat(visual-audit): bar, tree, flow, and custom figures"
```

### Task 8: Visual design, interaction, and example reports

**Files:**
- Modify: `plugins/visual-audit/skills/audit-report/templates/page.html`, `report.css`, `report.js`
- Create: `plugins/visual-audit/skills/audit-report/reference/example-report.json`
- Create: `tests/visual_audit_fixtures.py` (`large_report() -> dict` with 300 steps in 6 phases, 80 files in 9 directories, 20 runs; `all_pass_report() -> dict`)
- Test: `tests/test_visual_audit_cli.py` (add tests)

**Interfaces:**
- Consumes: markup contracts from Tasks 4–7 (`mark-*` classes, `data-status`, `data-source`, `asserted` class, `<details>`, anchors).

- [ ] **Step 1: Write the failing tests:** `test_example_report_is_valid_and_renders` (loads `reference/example-report.json`; it must contain every module type, every figure kind, a contradiction, a resolved failure, an expected failure, a refuted claim, refs, phases, and a truncated hunk), `test_large_and_all_pass_reports_render`, `test_print_and_dark_styles_present` (`@media print` and `prefers-color-scheme: dark` in output), `test_js_adds_filters_only_at_runtime` (no filter buttons in the static HTML).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_visual_audit_cli -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Write the CSS and JS.** Before editing, invoke the `impeccable:impeccable` skill for Operate-mode work and follow its craft floor. Implement the spec's "Page design" section exactly: status colour roles and shapes, dashed asserted outline, neutral two-layer surface, system sans and monospace, fixed rem scale ~1.2, light and dark, mobile rules below 40rem, print rules, visible focus, WCAG AA contrast. `report.js`: insert filter buttons (all, attention, asserted) that toggle a class on `<main>`; on `hashchange` and load, open every `<details>` ancestor of the target and scroll to it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Visual verification.** Render the example, large, and all-pass reports into `/tmp/visual-audit/`, serve with `python3 -m http.server` from that directory, and inspect each in a browser in light and dark at 1280px and 390px wide, with JS on and off. Run `"<impeccable-dir>/scripts/impeccable" detect --json /tmp/visual-audit/example-report.html` and an Impeccable critique of the example page. Fix every P0/P1 finding in one batch, re-render, check once more, and stop.

- [ ] **Step 6: Commit**

```bash
git add plugins/visual-audit tests/visual_audit_fixtures.py tests/test_visual_audit_cli.py
git commit -m "feat(visual-audit): flight-recorder styling, interaction, and examples"
```

### Task 9: Skill instructions, packaging, and lifecycle verification

**Files:**
- Create: `plugins/visual-audit/skills/audit-report/SKILL.md`
- Create: `plugins/visual-audit/skills/audit-report/reference/schema.md`
- Modify: `catalog.json` (append `"plugins/visual-audit"`)
- Generated: `plugins/visual-audit/.claude-plugin/plugin.json`, `plugins/visual-audit/.codex-plugin/plugin.json`, both marketplaces
- Modify: `scripts/verify_lifecycle.py` (the installed-skill comparison loop)
- Modify: `tests/test_verify_lifecycle.py`
- Modify: `README.md`, `docs/verification.md`

**Interfaces:**
- Produces: `verify_lifecycle.compare_tree(source: Path, installed: Path) -> list[str]` — relative paths that are missing or differ, ignoring generated host directories (`.claude-plugin`, `.codex-plugin`) and `__pycache__`; `verify_host` fails if non-empty and records per-file SHA-256 for every `SKILL.md` as before.

- [ ] **Step 1: Write the failing tests** in `tests/test_verify_lifecycle.py`: `test_compare_tree_detects_missing_and_changed_files` (temp trees: identical → `[]`; a missing script and a changed template are both reported), `test_compare_tree_ignores_host_dirs_and_pycache`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_verify_lifecycle -v`
Expected: ERROR — `cannot import name 'compare_tree'`.

- [ ] **Step 3: Implement `compare_tree`** and use it in `verify_host` in place of the `SKILL.md`-only comparison.

- [ ] **Step 4: Write `SKILL.md`** with frontmatter `name: audit-report` and a description limited to explicit requests ("Use only when the user explicitly asks for an audit report or invokes audit-report…"). Body: the seven-step procedure from the spec's "Skill behaviour" section, the provenance rules, the command `python3 <skill-dir>/scripts/render_report.py <json>`, and a pointer to `reference/schema.md`. Write `reference/schema.md` with every field from the spec's "Report JSON" section and one minimal example per module type. Keep the skill body under 120 lines.

- [ ] **Step 5: Regenerate and verify packaging**

Run:
```sh
python3 scripts/sync_marketplaces.py
python3 scripts/sync_marketplaces.py --check
python3 -m unittest discover -s tests -v
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```
Expected: "Generated metadata is current."; all tests PASS; `codex: PASS` and `claude: PASS`, with all three plugins discovered, installed, and byte-compared.

- [ ] **Step 6: Update docs.** README: add `visual-audit` to the plugin descriptions and install commands, how to invoke it, and where reports go. `docs/verification.md`: record the new run's CLI versions, the three plugins, whole-tree comparison, and skill hashes from the report. State that model-driven use was not tested unless it was.

- [ ] **Step 7: Commit**

```bash
git add catalog.json plugins .claude-plugin .agents scripts tests README.md docs/verification.md
git commit -m "feat(visual-audit): package skill and verify full plugin trees"
```
