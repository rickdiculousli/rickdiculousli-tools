---
name: audit-report
description: Use only when the user explicitly asks for an audit report, a visual report of what the agent did in this session, or invokes audit-report. Renders the session's actions as a self-contained HTML page for visual review.
---

# Audit report

Turn what you did in this session into a visual HTML page the user can audit at a
glance: outcome, contradictions, what needs attention, and how much of the report is
only your word. You write structured JSON; a bundled renderer draws the page.

`<skill-dir>` below means the directory containing this SKILL.md.

## Procedure

1. **Reconstruct the session from real tool results**, not memory of intent:
   commands with their exit codes, files changed (prefer `git diff --numstat` for
   counts and `git diff` for hunks), test results, and the claims you intend to make.
2. **Mark provenance honestly.** Set `"source": "observed"` only when an actual tool
   result from this session backs the item, and quote a short excerpt of it as
   `evidence`. Everything else stays `asserted` (the default). A claim may be
   `verified` only if it is observed. Never upgrade an item without evidence.
3. **Classify failures.** Mark runs that were meant to fail (for example a TDD red
   phase) with `"expect_fail": true`. Set `"resolved": true` only on a failed step or
   run that a later action demonstrably fixed.
4. **Structure long sessions.** Group timeline steps into `phase`s (Explore, Build,
   Verify, …) and link each claim to its proof with `refs` (step and run numbers are
   1-based across the whole report; files by path).
5. **Write the JSON** to `.audit/<YYYYMMDD-HHMMSS>-<slug>.json` under the current
   working directory, then render it:

   ```sh
   python3 <skill-dir>/scripts/render_report.py .audit/<name>.json
   ```

   The HTML is written next to the JSON. The renderer adds `.audit/.gitignore` so
   reports never enter version control. Use `-o PATH` for another location.
6. **On validation errors**, the renderer lists every problem with its JSON path
   (for example `modules[2].runs[0].exit: expected integer`). Fix them and re-run.
7. **Reply with the HTML path and at most one sentence.** The page carries the detail.

## Choosing modules

Include only modules you have real content for; a missing module shows as
"not reported", never as zero.

| Module | Use for |
| --- | --- |
| `timeline` | Every meaningful action, in order (reads, searches, edits, runs) |
| `files` | Every file changed, with line counts and hunks |
| `runs` | Commands and test runs with exit codes, suites, and output excerpts |
| `claims` | Statements you make about the result, each verified, unverified, or refuted |
| `figure` | Anything clearer as a chart: `bar`, `tree`, `flow`, or `custom` SVG |

Set `outcome` to `pass`, `partial`, or `blocked`. Anything other than `pass` requires
`blockers`; add `next_steps` when the user must act. The page flags a `pass` that is
contradicted by unresolved failures or refuted or unverified claims, so do not soften
the outcome.

The full field reference with one example per module is in
[reference/schema.md](reference/schema.md). A complete example covering every module
is [reference/example-report.json](reference/example-report.json).
