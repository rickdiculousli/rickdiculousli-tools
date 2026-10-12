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
| `## Roles` | Named tier/runbook pairs with reuse caps | None |
| `## Rote scripts` | `name: command; what it replaces` proposals or approved helpers | None |
| `## Host side effects` | Prohibited host changes outside the worktree, one per line | None |
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
  `state-relative logs/<delegation>/<n>.log`; the ledger keeps that path, the exit
  code, duration, a SHA-256 of the output and its last 40 lines (at most 4000
  characters).
- **Validator attributes.** Optional, in brackets after the name, separated by
  commas: `test [timeout=1800, lock=cargo]: cargo test --workspace`.
  - `cheap`: fast enough to run while working. Briefs tell subagents to run
    cheap validators first and fix what they report before anything slower.
  - `needs-human`: requires user notification by the judge before work begins
    and early while the user is present. Stop for required human action;
    do not retry indefinitely. This is a bare attribute, without a value.
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
    which exits with its status (124 on timeout). With `--delegation`, it
    records command evidence with `validator=null`; that evidence cannot support
    `checked` acceptance by a registered validator. Cite command observations or
    mark them `asserted`. Both `--lock` and `--timeout` are required.
  - Locks also cover physical resources. For example, `games: slots=6,
    wait=3600` permits six foreground game processes. `exec` holds its slot for
    the complete foreground process lifetime: no detached launches. One command
    owns one slot; a command spawning several jobs must acquire a slot per child
    or serialize them, otherwise it oversubscribes the resource.
  - Slot counts suit one machine; the environment variable
    `DELEGATION_LOCK_<NAME>` (upper case, `-` as `_`) overrides one for a machine
    or session, for example `DELEGATION_LOCK_CARGO=2`. Set it the same way for
    every session on the machine: each session uses only the slots it knows of.
  - `check.py locks` lists each lock's slots and who holds them.
  - How it works: native `flock` (POSIX) or `msvcrt.locking` (Windows)
    holds each slot in the XDG repository resource-lock directory returned by
    `check.py paths --json`. Both platforms use JSON holder/waiter sidecars with
    PID and process-start identity. The fixed root `state.lock` coordinates
    acquisition, waiter registration and cleanup; no slot wait or validator runs
    while holding it. All coordinating processes must use the same XDG root.
    Metadata alone never breaks native contention. Unknown owners protect state.
- **`validator:<name>` references.** Anywhere in the file, `validator:<name>`
  must name a registered validator, or lint reports `unregistered validator`.
  Use it in `## Oracle` or `## Tier hints` to tie prose to a check.
- **`## Extra inputs`.** One path per line, relative to the worktree root, or a logical
  `state:context/<relative-path>` input;
  surrounding backticks are stripped. Absolute paths and paths containing `..`
  are rejected. A file contributes its content hash, a directory the hashes of
  every file under it, and a missing path the marker `missing`. With extra
  inputs, the tree hash is a SHA-256 over the git tree id plus each input's hash,
  so changing a golden trace makes earlier checks stale.
- **`## Parallel limit` and `## Return cap`.** The leading integer of the first
  line, at least 1. Trailing text is allowed, for example
  `3 (ghidra-mcp concurrency unverified)`.
- **`## Roles`.** One named role per line, for example:

  ```text
  capture: tier=execute, runbook=state:context/capture.md, max-uses=8, max-context-bytes=100000
  ```

  `tier` is `execute` or `routine`; `runbook` names a context file inside the
  worktree. At least one positive cap is required. Prefer `max-uses`: it counts
  the first brief and every continuation, including all ancestor branches.
  `max-context-bytes` accumulates the sizes of the brief and context files loaded
  on every use, including repeated reads across uses. Outputs are excluded; this
  measures supplied file bytes, not the model's actual context consumption.
  `open --tier execute --role capture` loads the runbook and validates that
  the required `--tier` matches the role. Reuse through
  `open --tier execute --continue <prior-id>` requires a new id and brief, a closed prior
  delegation, the same tier, and no open brief in the same role session. Each
  use records fresh brief/runbook hashes. Optional roles leave legacy overlays
  valid.
- **`## Rote scripts`.** One `name: body` per line; the parser validates
  this structure. Use `name: command; what it replaces` for proposals. Record deterministic multi-step rote sequences worth replacing with
  repository scripts. A proposal does not authorize writing a script: obtain
  explicit approval before creating or changing repository helpers.
- **`## Host side effects`.** Free text, one prohibited host change outside the
  worktree per line (for example, user-wide plugin configuration or live game
  saves). When the section is nonempty, briefs append these as never-write
  restrictions with the isolation instruction. These are agent instructions,
  not filesystem enforcement; worktree write permissions do not authorize host
  changes.
- **`## Tier hints`.** Free text may mark human dependencies, for example
  `execute [needs-human]: native launches require human approval`. The judge
  notifies the user before such work and early while the user is present;
  stop for human action rather than retrying indefinitely.
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
