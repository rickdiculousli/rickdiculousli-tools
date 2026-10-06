# Visual audit report plugin

## Outcome

Add `visual-audit`, the first real plugin in this marketplace. When explicitly
invoked, its `audit-report` skill has the coding agent describe the work it just
did as structured JSON, then render that JSON into one self-contained HTML page.
The page lets Rick audit harness actions by looking, not by reading a transcript:
show, don't tell.

Success means a reviewer can open the page and within ten seconds know the
outcome, whether it is contradicted by anything, what needs attention, and how
much of the report is only the agent's word. Detail is one click deeper; failures
are already open.

## Decisions already made

- **Source of truth:** the agent writes the report (not a transcript parser).
  Because the page shows the agent's own account, provenance is first-class.
- **Modules in v1:** verdict band, action timeline, file changes, command and
  test runs, claims versus evidence, and a figure module for anything clearer as
  a chart, tree, or flow, including custom SVG.
- **Rendering:** agent writes JSON; a Python standard-library renderer bundled in
  the skill produces the page. Agent-supplied text is HTML-escaped. Custom SVG is
  kept byte-for-byte but embedded as an image so it cannot restyle the page; it
  is not sanitised.
- **Visual direction:** "flight recorder" — calm, dense, Operate-mode UI.
- **Out of scope for v1:** comparison and decision/risk modules, inferring
  resolved failures by matching commands, CSS-only or URL-persisted filters,
  links from truncation markers to the JSON, keyboard shortcuts.

## Plugin layout

```text
plugins/visual-audit/
  plugin.json                          # name visual-audit, version 0.1.0
  skills/audit-report/
    SKILL.md                           # when and how to produce a report
    reference/schema.md                # module reference, one example per type
    reference/example-report.json      # every module and state populated
    scripts/render_report.py           # CLI entry point
    scripts/audit_report/
      __init__.py
      schema.py                        # validation with path-addressed errors
      derive.py                        # counts, contradictions, attention items
      page.py                          # verdict band, attention list, assembly
      modules.py                       # timeline, files, runs, claims renderers
      figures.py                       # bar, tree, flow SVG; custom embedding
    templates/
      page.html                        # string.Template shell
      report.css                       # all styling, light, dark, print
      report.js                        # filters, anchor opening; optional
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
2. Mark an item `observed` only when an actual tool result in this session backs
   it, quoting a short excerpt as `evidence`. Everything else is `asserted`.
3. Mark runs that were meant to fail (for example a TDD red phase) with
   `expect_fail`, and set `resolved: true` only on failures a later action
   demonstrably fixed.
4. Group long sessions into `phase`s and link claims to their proof with `refs`.
5. Write `.audit/<YYYYMMDD-HHMMSS>-<slug>.json` in the current working directory,
   then run `python3 <skill-dir>/scripts/render_report.py <json>`.
6. On validation errors, fix the listed paths and re-run.
7. Reply with the HTML path and at most one sentence.

## Report JSON

```json
{
  "version": 1,
  "title": "Add visual-audit plugin",
  "goal": "One line describing the task",
  "outcome": "partial",
  "blockers": ["Lifecycle check needs the codex CLI, which is missing"],
  "next_steps": ["Install codex and re-run verify_lifecycle.py"],
  "context": {
    "repo": "rickdiculousli-plugin-repository",
    "branch": "visual-audit-plugin",
    "base_commit": "3a95cec",
    "head_commit": "9f1e2aa",
    "session_id": "188c7677",
    "host": "claude-code 2.1.290",
    "started": "2026-10-05T19:02:00-07:00",
    "ended": "2026-10-05T19:40:00-07:00"
  },
  "modules": []
}
```

**Top level:** `version` must be `1`. `title`, `goal`, and `outcome` (`pass`,
`partial`, `blocked`) are required. `blockers` (non-empty list of strings) is
required when outcome is not `pass`. `next_steps` and `context` are optional;
every `context` field is an optional string.

**Shared item fields:** every list item in every module accepts `source`
(`observed` or `asserted`, default `asserted`) and `evidence` (string).
`source: observed` requires non-empty `evidence`. Evidence is shown verbatim in
monospace and labelled "agent-quoted", truncated at 2,000 characters with a
marker giving the original length.

Each module has `type` and an optional `title`. Unknown types and unknown keys
are errors.

| Type | Fields |
| --- | --- |
| `timeline` | `steps`: `kind` (`read`, `search`, `edit`, `run`, `think`, `other`), `label`, `status` (`ok`, `fail`, `warn`, `retry`; default `ok`), optional `phase`, `detail`, `resolved` (boolean, only with `fail`/`warn`) |
| `files` | `files`: `path`, `change` (`added`, `modified`, `deleted`, `renamed`), `added` and `removed` (non-negative integers), optional `from` (required for `renamed`), `hunks` (list of unified diff strings), `generated`, `binary` (booleans) |
| `runs` | `runs`: `command`, `exit` (integer), optional `expect_fail` (boolean), `duration_ms`, `suites` (`name`, `passed`, `failed`, `skipped` integers), `excerpt`, `resolved` |
| `claims` | `claims`: `claim`, `status` (`verified`, `unverified`, `refuted`), optional `refs`: `{"steps": [int], "runs": [int], "files": [path]}` |
| `figure` | `kind` (`bar`, `tree`, `flow`, `custom`), required `alt`, plus matching data: `bars` (`label`, `value` ≥ 0, optional `status`), `tree` (recursive `label`, optional `status`, `children`), `flow` (`nodes`: `id`, `label`, optional `status`; `edges`: `from`, `to`, optional `label`), or `svg` (string) |

**Numbering for refs:** steps and runs are numbered 1-based across the whole
report in document order (all timeline modules concatenated, likewise runs).
Files are referenced by path. Dangling refs are validation errors.

**Further rules:** a `verified` claim must be `observed`; flow edges must name
existing nodes and form no cycle; `resolved` on an `ok` step or a successful run
is an error.

Validation collects every error before failing, each with its JSON path, for
example `modules[2].runs[0].exit: expected integer, got "0"`. The renderer exits
1 and writes nothing on validation failure.

## Derived state

Computed by `derive.py`, never supplied by the agent:

- **Run failure:** exit ≠ 0 without `expect_fail`, or exit = 0 with
  `expect_fail` (an expected failure that passed). Each run is classified as
  unresolved failure, resolved failure, expected failure, or ok.
- **Step failure:** status `fail` (or `warn`) not marked `resolved`.
- **Failure counts:** unresolved, resolved, and expected shown separately. A
  failure is counted once per item; timeline steps and runs are counted
  separately and labelled as such ("2 failed runs · 1 failed step").
- **Contradiction:** outcome `pass` while any unresolved failure, refuted claim,
  or unverified claim exists. Rendered prominently, never a validation error.
- **Asserted count:** asserted items among runs, claims, files, and timeline
  steps of kind `edit`, `run`, or `other`. `read`, `search`, and `think` steps
  are excluded. When every countable item is asserted, a single band-level
  banner says so.
- **Attention items:** unresolved failures (runs and steps), refuted claims,
  unverified claims, deleted files, and evidence truncations, each linking to its
  anchor.
- **Missing modules:** counts for an absent module render "not reported", never
  0. Commands = `runs` items only; files = `files` items only.

## Page design

Mode: Operate. The tool should disappear into the audit.

**Order on the page**

1. **Verdict band:** title, goal, and outcome as a large status mark; the
   contradiction warning ("pass — contradicted by 3 items") when applicable;
   blockers and next steps for non-pass outcomes; counts (failures split as
   above, asserted, files changed with +/− lines, commands), each count linking
   to the relevant attention items or module; the all-asserted banner when
   applicable; the context header in small monospace with a renderer-stamped
   "rendered at"; and the run strip.
2. **Needs attention:** a plain-HTML list of attention items linking to their
   anchors. Explicitly reads "Nothing needs attention" when empty.
3. Modules in the order the agent listed them.

**Run strip:** a single inline SVG of the timeline, one mark per step with a
minimum mark width. Above 120 steps, consecutive steps are bucketed and each
bucket takes its worst status. Only fail/warn marks are focusable links; the
rest are `aria-hidden`. A text alternative summarises it ("312 steps: 3 failed
(steps 41, 88, 203), 2 warnings"). Omitted when there is no timeline.

**Visual grammar** (identical in every module)

| Meaning | Colour role | Shape |
| --- | --- | --- |
| ok / pass / verified / resolved | success | filled circle |
| fail / refuted (unresolved) | danger | filled square |
| warn / retry / partial | warning | triangle |
| expected failure | neutral | circle with slash |
| asserted / unverified | neutral | dashed outline, hollow marker |

Colour never carries meaning alone.

**Disclosure defaults:** item detail, evidence, excerpts, and hunks live in
`<details>`. They start open for unresolved failed runs, failed or warned steps,
and refuted claims; closed otherwise. Phases containing an unresolved failure
start open; others start closed with a status summary.

**Anchors:** the renderer emits `#step-N`, `#run-N`, `#claim-N`, `#file-<slug>`,
and `#phase-<slug>`, plus `#module-N` and `#attention`. With JS, following any
anchor opens every enclosing `<details>` and scrolls to the item. Without JS,
disclosure defaults keep every attention target and failing run-strip target
visible (failures, refuted claims, and directories containing deletions or cited
files start open); ref chips into other closed groups rely on the browser's own
behaviour. Claim `refs` render as link chips to their targets, and targets show a
back-chip to the claims that cite them.

**Modules**

- **Timeline:** grouped by `phase` when present. Vertical rail of steps, icon by
  kind, marker by status. Inside a phase, consecutive `ok` steps of the same kind
  collapse into one expandable node ("read × 14").
- **Files:** grouped by directory with a directory total row; directories over
  12 files start collapsed. Within a directory, deletions and renames sort
  first. Each row: change badge, path in monospace, and a log-scaled bar of
  added versus removed lines. `generated` files are greyed and collapsed;
  `binary` files show no bar. Hunks are capped at 40 lines each and 10 per file,
  with markers like "showing 40 of 312 lines" and "3 more hunks not shown".
- **Runs:** one row per command with exit-code badge, failure class, and
  duration. Suites render as a stacked pass/fail/skip bar with counts. Excerpts
  capped at 60 lines with a marker.
- **Claims:** claim then evidence then ref chips; refuted first, then
  unverified, then verified.
- **Figure:** bar renders horizontal bars in the given order; tree renders an
  indented elbow tree; flow renders a layered left-to-right graph (longest-path
  layering, nodes ordered by input). Custom SVG is embedded as
  `<img src="data:image/svg+xml;base64,…" alt="…">`. Every figure has its `alt`
  and, for built-in kinds, a visually hidden list or table of its data.

**Filtering:** `report.js` inserts filter buttons (all, attention, asserted) at
the top of the page; they apply to every module via `data-status` and
`data-source` attributes. Without JS the buttons do not exist.

**Look**

- Neutral surface with a second neutral layer for panels; colour reserved for
  status. No gradients, glass, decorative shadows, or grid of big-number cards.
- System sans for UI, system monospace for paths, commands, and output. No web
  fonts.
- Fixed rem type scale (ratio ~1.2). Dense but scannable; prose wraps, monospace
  scrolls horizontally inside its block.
- `prefers-color-scheme` light and dark.
- **Mobile (below 40rem):** claim and evidence stack; figures sit in a
  horizontally scrolling frame; band counts wrap into a two-column text grid.
- **Print:** attention items and failed or refuted content print expanded;
  other `<details>` stay closed; hunks print as a file list with +/− counts;
  filter buttons are hidden.
- Fully readable with JavaScript disabled. CSS and JS are inlined so the file is
  self-contained.
- Accessible: semantic landmarks, visible focus, status conveyed in text for
  screen readers, contrast at WCAG AA in both schemes.

## Output location

Default output is `.audit/` under the current working directory. On first use
the renderer creates `.audit/.gitignore` containing `*`, so reports never enter
version control and no user file is edited. The HTML is written next to the JSON
with the same stem; `-o PATH` overrides it.

## Error handling

- Invalid JSON or schema: exit 1, all errors listed, nothing written.
- Unwritable output: exit 1 with the path and OS error.
- Oversized input is not rejected; truncation rules keep the page usable, and
  every truncation says how much was hidden.

## Testing

Standard-library `unittest` in the repository `tests/` directory, loading the
renderer from the plugin path:

- **Validation:** required fields, enums, unknown keys and types, observed
  requires evidence, verified requires observed, blockers required for non-pass,
  refs must resolve, flow cycles, misuse of `resolved`, and multi-error reporting
  with paths; no output on failure.
- **Derivation:** run failure classes including `expect_fail` both ways,
  resolved steps, contradiction detection, asserted count exclusions,
  all-asserted banner, attention items, "not reported" for missing modules.
- **Rendering:** the example report renders; agent text is escaped (a `<script>`
  title appears as text); custom SVG bytes round-trip through the data URI;
  disclosure defaults open failures only; anchors and ref chips exist both ways;
  run-strip bucketing above 120 steps; read-run collapsing; truncation markers
  with sizes; empty attention list message.
- **Output:** `.audit/.gitignore` creation and `-o` override.
- **Determinism:** same input renders identical bytes apart from the "rendered
  at" stamp, which tests can fix.

Visual verification: render `example-report.json` plus a large generated report
(300 steps, 80 files) and an all-pass report, inspect them in a browser in light
and dark at desktop and mobile widths, then run Impeccable's detector and
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
