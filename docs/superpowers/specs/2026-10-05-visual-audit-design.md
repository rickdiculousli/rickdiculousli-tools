# Visual audit report plugin

## Outcome

Add `visual-audit`, the first real plugin in this marketplace. When explicitly
invoked, its `audit-report` skill has the coding agent describe the work it just
did as structured JSON, then render that JSON into one self-contained HTML page.
The page lets Rick audit harness actions by looking, not by reading a transcript:
show, don't tell.

Success means a reviewer can open the page and within ten seconds know the
outcome, whether anything failed, and how much of the report is only the agent's
word. Detail is one click deeper, never in the way.

## Decisions already made

- **Source of truth:** the agent writes the report (not a transcript parser).
  Because the page shows the agent's own account, provenance is first-class (see
  below).
- **Modules in v1:** run summary (verdict band), action timeline, file changes,
  command and test runs, claims versus evidence, and a figure module for anything
  clearer as a chart, tree, or flow, including custom SVG.
- **Rendering:** agent writes JSON; a Python standard-library renderer bundled in
  the skill produces the page. Agent-supplied text is HTML-escaped. Custom SVG in
  the figure module is inserted verbatim (deliberately not sanitised).
- **Visual direction:** "flight recorder" — calm, dense, Operate-mode UI.
- Comparison and decision/risk modules are out of scope for v1.

## Plugin layout

```text
plugins/visual-audit/
  plugin.json                          # name visual-audit, version 0.1.0
  skills/audit-report/
    SKILL.md                           # when and how to produce a report
    reference/schema.md                # module reference, one example per type
    reference/example-report.json      # every module populated
    scripts/render_report.py           # CLI entry point
    scripts/audit_report/
      __init__.py
      schema.py                        # validation with path-addressed errors
      page.py                          # verdict band, page assembly
      modules.py                       # timeline, files, runs, claims renderers
      figures.py                       # bar, tree, flow SVG layouts
    templates/
      page.html                        # string.Template shell
      report.css                       # all styling, light and dark
      report.js                        # optional filtering; page works without it
```

Everything the skill needs lives inside the plugin, so Claude Code and Codex
install identical bytes. No dependencies, no network access at render or view
time, no build step.

## Skill behaviour

`SKILL.md` frontmatter limits triggering to explicit requests ("make an audit
report", `/visual-audit:audit-report`, or asking Codex to use `audit-report`).
The skill instructs the agent to:

1. Reconstruct the session from its real tool calls and results: commands with
   exit codes, files changed (prefer `git diff --numstat` and `git diff` for
   counts and hunks), test results, and claims it intends to make.
2. Mark an item `observed` only when it is backed by an actual tool result in
   this session, quoting a short excerpt as `evidence`. Everything else is
   `asserted`. Never upgrade a claim to `observed` without evidence.
3. Write `.audit/<YYYYMMDD-HHMMSS>-<slug>.json` in the current working directory,
   then run `python3 <skill-dir>/scripts/render_report.py <json>`.
4. On validation errors, fix the listed paths and re-run.
5. Reply with the HTML path and at most one sentence. The page carries the
   detail.

## Report JSON

```json
{
  "version": 1,
  "title": "Add visual-audit plugin",
  "goal": "One line describing the task",
  "outcome": "pass",
  "started": "2026-10-05T19:02:00-07:00",
  "ended": "2026-10-05T19:40:00-07:00",
  "host": "claude-code 2.1.290",
  "modules": []
}
```

- `version` must be `1`. `title`, `goal`, and `outcome` (`pass`, `partial`,
  `blocked`) are required; times and host are optional strings.
- Every list item in every module accepts `source` (`observed` or `asserted`,
  default `asserted`) and optional `evidence` (string, shown verbatim in
  monospace, truncated to 2,000 characters with a visible marker).
- Each module has `type` and an optional `title`. Unknown types and unknown keys
  are errors.

| Type | Fields |
| --- | --- |
| `timeline` | `steps`: `kind` (`read`, `search`, `edit`, `run`, `think`, `other`), `label`, `status` (`ok`, `fail`, `warn`, `retry`; default `ok`), optional `detail` |
| `files` | `files`: `path`, `change` (`added`, `modified`, `deleted`, `renamed`), `added` and `removed` (non-negative integers), optional `from` for renames, optional `hunks` (list of unified diff strings) |
| `runs` | `runs`: `command`, `exit` (integer), optional `duration_ms`, optional `suites` (`name`, `passed`, `failed`, `skipped` integers), optional `excerpt` |
| `claims` | `claims`: `claim`, `status` (`verified`, `unverified`, `refuted`) |
| `figure` | `kind` (`bar`, `tree`, `flow`, `custom`) plus matching data: `bars` (`label`, `value` ≥ 0, optional `status`), `tree` (recursive `label`, optional `status`, `children`), `flow` (`nodes`: `id`, `label`, optional `status`; `edges`: `from`, `to`, optional `label`), or `svg` (string) |

A `claims` item marked `verified` with `source: asserted` is a validation error:
verification requires observed evidence.

Validation collects every error before failing, each with its JSON path, for
example `modules[2].runs[0].exit: expected integer, got "0"`. The renderer exits
1 and writes nothing on validation failure.

## Page design

Mode: Operate. The tool should disappear into the audit.

**Order on the page**

1. **Verdict band** (always rendered, derived, not a module): title and goal;
   outcome as a large status mark; counts for failures, asserted items, files
   changed (+/− lines), and commands run; and the **run strip** — one thin mark
   per timeline step in order, coloured and shaped by status. Each mark links to
   its step. If there is no timeline, the strip is omitted.
2. Modules in the order the agent listed them.

**Visual grammar** (identical in every module)

| Meaning | Colour role | Shape |
| --- | --- | --- |
| ok / pass / verified | success | filled circle |
| fail / refuted | danger | filled square |
| warn / retry / partial | warning | triangle |
| asserted / unverified | neutral | dashed outline, hollow marker |

Colour never carries meaning alone. Asserted items use a dashed border wherever
they appear, so the proportion of unverified content is visible at a glance.

**Modules**

- **Timeline:** vertical rail of steps, icon by kind, marker by status.
  Consecutive steps with the same kind and `ok` status collapse into one node
  ("read × 14") that expands. Filter chips (all, failed, asserted) via
  `report.js`.
- **Files:** grouped by directory. Each row: change badge, path in monospace,
  and a proportional bar of added versus removed lines. Hunks sit in a collapsed
  `<details>`, each capped at 40 lines with a "truncated" marker.
- **Runs:** one row per command with exit-code badge and duration. Suites render
  as a stacked pass/fail/skip bar with counts. Excerpts collapsed.
- **Claims:** two-column rows, claim then evidence; refuted first, then
  unverified, then verified.
- **Figure:** bar renders horizontal bars sorted as given; tree renders an
  indented elbow tree; flow renders a layered left-to-right graph (longest-path
  layering, nodes ordered by input; cycles are a validation error); custom
  inserts the SVG inside a sized frame.

**Look**

- Neutral surface with a second neutral layer for panels; colour reserved for
  status. No gradients, glass, shadows-as-decoration, or grid of big-number cards.
- System sans for UI, system monospace for paths, commands, and output. No web
  fonts.
- Fixed rem type scale (ratio ~1.2). Dense but scannable; long text wraps,
  monospace scrolls horizontally inside its block.
- `prefers-color-scheme` light and dark; print stylesheet expands all
  `<details>` and drops filter chips.
- Fully readable with JavaScript disabled; `report.js` only adds filtering and
  run-strip highlighting. CSS and JS are inlined so the file is self-contained.
- Accessible: semantic landmarks, visible focus, status conveyed in text for
  screen readers, contrast at WCAG AA in both schemes.

## Output location

Default output is `.audit/` under the current working directory. On first use
the renderer creates `.audit/.gitignore` containing `*`, so reports never enter
version control and no user file is edited. `-o PATH` overrides the HTML path.
The HTML is written next to the JSON with the same stem by default.

## Error handling

- Invalid JSON or schema: exit 1, all errors listed, nothing written.
- Unwritable output: exit 1 with the path and OS error.
- Oversized input is not rejected; truncation rules keep the page usable
  (evidence 2,000 chars, hunks 40 lines, excerpts 60 lines), each marked.

## Testing

Standard-library `unittest` in the repository `tests/` directory, loading the
renderer from the plugin path:

- Validation: each module's required fields, enum values, unknown keys/types,
  the verified-requires-observed rule, flow cycles, and multi-error reporting
  with paths; no output on failure.
- Rendering: example report renders; agent text is escaped (a `<script>` title
  appears as text); custom SVG is inserted verbatim; asserted items carry the
  dashed class; read-run collapsing; truncation markers; derived verdict counts.
- Output: `.audit/.gitignore` creation and `-o` override.
- Determinism: same input renders identical bytes.

Visual verification: render `example-report.json`, inspect it in a browser in
light and dark at desktop and mobile widths, then run Impeccable's detector and
critique on the rendered page and fix material findings.

## Packaging and verification

- Add `plugins/visual-audit` to `catalog.json`, regenerate host metadata, and
  commit generated files.
- Extend `scripts/verify_lifecycle.py` to compare every file in each installed
  plugin with its source (not only `SKILL.md`), since this plugin ships scripts
  and templates. Update its tests.
- Lifecycle verification must pass on both hosts; record results in
  `docs/verification.md`. Document the plugin in the README.
- Model-driven use of the skill in a real session is not claimed unless
  performed.
