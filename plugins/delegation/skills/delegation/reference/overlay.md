# Overlay format (`.agents/delegation.md`)

The overlay lives in the repository it describes. It is Markdown with fixed `##`
headings. Every heading is optional; a missing one falls back to the base
default. `check.py lint` reports problems as `line <n>: <problem>` and exits 1.

| Heading | Content | Default |
|---|---|---|
| `## Bulk work` | What counts as bulk in this repo | Base rule 1 only |
| `## Oracle` | What verifies work mechanically | None |
| `## Validators` | `name [attributes]: command` lines | None; all claims are `cited` or `asserted` |
| `## Extra inputs` | Ignored paths folded into the tree hash | None |
| `## Locks` | `name: slots=<n>, wait=<seconds>` lines | None |
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
  stdout and stderr merged. The full output goes to
  `.delegation/logs/<delegation>/<n>.log`; the ledger keeps that path, the exit
  code, duration, a SHA-256 of the output and its last 40 lines (at most 4000
  characters).
- **Validator attributes.** Optional, in brackets after the name, separated by
  commas: `test [timeout=1800, lock=cargo]: cargo test --workspace`.
  - `cheap`: fast enough to run while working. Briefs tell subagents to run
    cheap validators first and fix what they report before anything slower.
  - `timeout=<seconds>`: the default for `run`; `--timeout` overrides it.
  - `lock=<name>`: `run` waits for a free slot of this lock and holds it while
    the command runs. The lock must be declared under `## Locks`, and the
    validator needs a `timeout`, so nothing holds a lock indefinitely. The
    ledger records the lock, the slot and the wait.
  - `requires=<platform>`: the validator runs only where Python's
    `sys.platform` matches (`darwin`, `linux`, `win32`); list several as
    `requires=darwin|linux`. Elsewhere `run` refuses (exit 2, no ledger entry),
    and briefs written on that host name it as not runnable there, so a check
    that can't run on a host never shows up as a FAIL. Every result records
    the host it ran on (`host`: platform, machine, node).
  An unknown or malformed attribute is a lint problem.
- **`## Locks`.** One `name: slots=<n>, wait=<seconds>` per line; both
  attributes are optional (`name:` alone is one slot, waiting indefinitely).
  A lock limits how many commands that need it run at once across **every
  worktree of the repo**: give memory-hungry builds the same lock and at most
  `slots` of them run at a time, even from parallel worktrees and sandboxed
  hosts. A process that waits longer than `wait` is refused (exit 2, no ledger
  entry); while it waits it prints who holds each slot.
  - Validators take a lock with `lock=<name>`; any other command takes one with
    `check.py exec --lock <name> --timeout <seconds> [--delegation <id>] -- <command>`,
    which runs it without a ledger entry and exits with its status (124 on
    timeout).
  - Slot counts suit one machine; the environment variable
    `DELEGATION_LOCK_<NAME>` (upper case, `-` as `_`) overrides one for a machine
    or session, for example `DELEGATION_LOCK_CARGO=2`. Set it the same way for
    every session on the machine: each session uses only the slots it knows of.
  - `check.py locks` lists each lock's slots and who holds them.
  - How it works: each slot is a file under `/tmp/delegation-locks-<hash of
    git's common directory>/`, held with `flock`. The kernel releases a slot
    when its holder exits, even on a crash, so there is no server to start and
    no stale lock to clear. Sandboxes that keep `.git` read-only still allow
    `/tmp`. Windows has no `flock`; there, locks hold nothing.
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

## Fixture-backed validators

A validator can carry the oracle itself, so oracle-backed acceptance is `checked`
rather than only `cited`. Set the fixture's environment in the command, or call
the repo's fixture runner:

```markdown
## Validators
trace-diff: GOLDEN_TRACES=research/traces/golden uv run -m unittest tests.test_trace_diff -v
fixtures: uv run python -I scripts/run_fixtures.py --require-all
## Extra inputs
research/traces/golden
```

A missing fixture must fail the validator, not skip: a suite that skips exits 0,
which the ledger records as PASS. Make the command require the fixture (for
example `test -d research/traces/golden && ...`, or a runner flag that turns
skips into failures). If the fixtures are git-ignored, list them under
`## Extra inputs` so changing them makes earlier results stale.

## Worked example: `game-decomp`

```markdown
# Delegation overlay: game-decomp
## Bulk work
Decompiling and naming functions per module file; porting simulation code to Rust against golden traces.
## Oracle
Golden-trace diff (per-tick thing state); the unit test suites.
## Validators
unit [timeout=900]: uv run -m unittest discover -s tests -v
probes: uv run -m unittest discover -s research/probes/tests -v
refs [cheap]: uv run --no-project python -I research/modules/check_refs.py
port [timeout=1800, lock=cargo]: cargo test --workspace
## Locks
cargo: slots=1, wait=3600
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
