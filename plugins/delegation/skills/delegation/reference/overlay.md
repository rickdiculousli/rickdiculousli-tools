# Overlay format (`.agents/delegation.md`)

The overlay lives in the repository it describes. It is Markdown with fixed `##`
headings. Every heading is optional; a missing one falls back to the base
default. `check.py lint` reports problems as `line <n>: <problem>` and exits 1.

| Heading | Content | Default |
|---|---|---|
| `## Bulk work` | What counts as bulk in this repo | Base rule 1 only |
| `## Oracle` | What verifies work mechanically | None |
| `## Validators` | `name: command` lines | None; all claims are `cited` or `asserted` |
| `## Extra inputs` | Ignored paths folded into the tree hash | None |
| `## Single writer` | Resources only the judge writes | None |
| `## Findings` | The findings sink and its schema | The execution log |
| `## Return fields` | Repo-specific fields for returns | None |
| `## Tier hints` | Known task types per tier | None |
| `## Parallel limit` | Max parallel readers | 3 |
| `## Return cap` | Max return length, in words | 400 |

## Parsing rules

- **Headings.** `## <name>` matches case-insensitively, with surrounding spaces
  ignored. An unknown heading or a repeated one is a lint problem. Text before the
  first `##` heading, and under an unknown heading, is ignored. Any other line
  starting with `#` (a `#` title, `###` subheadings) is skipped.
- **Lines.** CRLF and LF both work. Blank lines are skipped. A leading `- ` list
  marker is stripped, so sections may be written as lists.
- **`## Validators`.** One `name: command` per line, split at the first colon.
  Names match `[a-z0-9][a-z0-9_-]*` and must be unique. `check.py run <name>`
  runs the command through the shell from the worktree root, stdin closed,
  stdout and stderr merged; the ledger keeps the exit code, duration, a SHA-256
  of the output and its last 40 lines (at most 4000 characters).
- **`validator:<name>` references.** Anywhere in the file, `validator:<name>`
  must name a registered validator, or lint reports `unregistered validator`.
  Use it in `## Oracle` or `## Tier hints` to tie prose to a check.
- **`## Extra inputs`.** One path per line, relative to the worktree root;
  surrounding backticks are stripped. Absolute paths and paths containing `..`
  are rejected. A file contributes its content hash, a directory the hashes of
  every file under it, and a missing path the marker `missing`. With extra
  inputs, the tree hash is a SHA-256 over the git tree id plus each input's hash,
  so changing a golden trace makes earlier checks stale.
- **`## Parallel limit` and `## Return cap`.** The leading integer of the first
  line, at least 1. Trailing text is allowed, for example
  `3 (ghidra-mcp concurrency unverified)`.
- All other sections are free text for the judge; `check.py` doesn't interpret
  them.

## Worked example: `game-decomp`

```markdown
# Delegation overlay: game-decomp
## Bulk work
Decompiling and naming functions per module file; porting simulation code to Rust against golden traces.
## Oracle
Golden-trace diff (per-tick thing state); the unit test suites.
## Validators
unit: uv run -m unittest discover -s tests -v
probes: uv run -m unittest discover -s research/probes/tests -v
refs: uv run --no-project python -I research/modules/check_refs.py
## Single writer
The Ghidra project (through ghidra-mcp); research/modules/functions.csv, then apply_annotations.py.
## Findings
research/findings.jsonl (existing schema, with status `refuted` added).
## Return fields
thing offsets touched (read/write); globals read/written; callers/callees.
## Tier hints
execute: naming one module file; one Rust plan task against traces.
routine: probe batches (--jobs 6 max); first-divergence triage; export_functions.py --check.
## Parallel limit
3 (ghidra-mcp concurrency unverified)
```

`trace-diff` is registered once the Rust plan's Task 1 produces golden traces, and
the trace manifest then goes under `## Extra inputs`.
