# Overlay format (`.agents/delegation.md`)

The overlay lives in the repository it describes. It is Markdown with fixed `##`
headings. Every heading is optional; a missing one falls back to the base
default. `check.py lint` reports problems as `line <n>: <problem>` and exits 1.
It also reports layout drift (`missing`, `unexpected` or `outdated` paths) and
compares `## Version` with the installed plugin; `--json` prints all of it. See
the `migrate` skill.

| Heading | Content | Default |
|---|---|---|
| `## Bulk work` | What counts as bulk in this repo | Base rule 1 only |
| `## Oracle` | What verifies work mechanically | None |
| `## Validators` | `name [attributes]: command` lines | None; all claims are `cited` or `asserted` |
| `## Extra inputs` | Ignored paths folded into the tree hash | None |
| `## Locks` | `name: slots=<n>, wait=<seconds>` lines | None; native locks |
| Parallel runs | Sections used only by parallel or cross-machine runs; see [Parallel runs](#parallel-runs) | None |
| `## Roles` | Named tier/runbook pairs with reuse caps | None |
| `## Rote scripts` | `name: command; what it replaces` proposals or approved helpers | None |
| `## Host side effects` | Prohibited host changes outside the worktree, one per line | None |
| `## Authoring` | Whether the judge adds roles or rote scripts on its own or asks first: `roles: ask\|allowed`, `scripts: ask\|allowed` | Both `allowed` |
| `## Single writer` | Resources only the judge writes | None |
| `## Findings` | The findings sink and its schema | The execution log |
| `## Return fields` | Repo-specific fields for returns | None |
| `## Tier hints` | Known task types per tier | None |
| `## Parallel limit` | Max parallel readers | 3 |
| `## Return cap` | Max return length, in words | 400 |
| `## Version` | Plugin version the overlay was last linted clean against, like `0.11.0` | None; lint warns `version-mismatch` |

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
  - `paths=<glob>|<glob>`: the repository-relative paths whose changes call for
    this validator, for `check.py suggest`. `**` crosses directories, `*` and `?`
    stay within one, and a trailing `/` means everything below it:
    `ghidra-sync [paths=ghidra/**|exports/*.json]: ...`. It is a hint only; `run`
    never refuses on it. Absolute paths and `..` are lint problems.
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
- **`## Version`.** One line, `<major>.<minor>.<patch>`. Setup and migrate write
  it after a clean lint. Lint warns `version-mismatch` when it is missing or its
  major.minor is older than the installed plugin, and `version-newer` when it is
  newer; patch differences are ignored. Neither warning fails lint.
- **`## Parallel limit` and `## Return cap`.** The leading integer of the first
  line, at least 1. Trailing text is allowed, for example
  `3 (ghidra-mcp concurrency unverified)`.
- **`## Roles`.** One named role per line, for example:

  ```text
  capture: tier=execute, runbook=.agents/delegation/runbooks/capture.md, max-uses=8, max-context-bytes=100000
  ```

  `tier` is `execute` or `routine`; `runbook` names a tracked repository-relative
  source, normally `.agents/delegation/runbooks/<role>.md`; a `state:` runbook is an
  outdated lint problem. At least one positive cap is required. Prefer `max-uses`: it counts
  the first brief and every continuation, including all ancestor branches.
  `max-context-bytes` accumulates the sizes of the brief and context files loaded
  on every use, including repeated reads across uses. Outputs are excluded; this
  measures supplied file bytes, not the model's actual context consumption.
  `open --tier execute --role capture` loads the runbook and validates that
  the required `--tier` matches the role. Reuse through
  `open --tier execute --continue <prior-id>` requires a new id and brief, a closed prior
  delegation, the same tier, and no open brief in the same role session. Each
  use records fresh brief/runbook hashes.
- **`## Rote scripts`.** One `name: body` per line; the parser validates
  this structure. Use `name: command; what it replaces` for proposals. Record deterministic multi-step rote sequences worth replacing with
  repository scripts. Whether the judge may then write one without asking
  follows `## Authoring` (default `allowed`).
- **`## Host side effects`.** Free text, one prohibited host change outside the
  worktree per line (for example, user-wide plugin configuration or live game
  saves). When the section is nonempty, briefs append these as never-write
  restrictions with the isolation instruction. These are agent instructions,
  not filesystem enforcement; worktree write permissions do not authorize host
  changes.
- **`## Authoring`.** Up to two lines, `roles: ask|allowed` and
  `scripts: ask|allowed` (case-insensitive). `allowed`, the default when the
  section or a line is missing, lets the judge add that kind of material under
  `.agents/delegation/` when it sees repeated work; it reports each addition,
  keeps a single writer, and lints and proves what it adds. `ask` means each
  addition needs the user's approval first. An unknown key or value, or a repeated key, is a lint
  problem. Neither value allows editing tiers or agent definitions.
- **`## Tier hints`.** Free text may mark human dependencies, for example
  `execute [needs-human]: native launches require human approval`. The judge
  notifies the user before such work and early while the user is present;
  stop for human action rather than retrying indefinitely.
- All other sections are free text for the judge; `check.py` doesn't interpret
  them.

## Parallel runs

Everything in this section is optional and off unless the overlay names it. A
repository without these sections sees no change in any command or output.

- **Setup survey.** Offer these only when the user asks for runs spanning
  machines or parallel lanes, or the overlay already has them:
  - `## Locks` `provider: "<command>"`: only when an external lease service
    coordinates slots across machines (contract below).
  - `## Deps`: only for repositories with several units (crates, packages) where
    a change in one must also run its dependents' validators: `<unit>:
    <dependent>, ...` lines or a `command:` that prints the map as JSON. Pair it
    with `paths=` on the units' validators.
  - `## Rules`: project rules every subagent must obey (what test output may
    never contain, where scratch goes, append-only caches). `check.py brief`
    injects them into every brief, so don't repeat them in the brief body.
- **Lane tags.** When this session works one lane of a parallel run, pass
  `check.py open ... --lane <name>` (`[a-z0-9][a-z0-9_-]*`): the open event,
  `pending --json`, the brief header and the pattern log carry it, and
  `patterns` lists the lanes each kind was used from.
- **Dependents.** `check.py suggest --with-dependents` also adds the validators
  scoped to units that depend on a changed unit, from the `## Deps` map or
  command (a changed shared crate then pulls in its dependents' suites; `--json`
  marks each as `via: changed|dependents`).
- **Leases.** With a `provider:` line under `## Locks` the slots are leases from
  an external command; `run` and `exec` take and renew a lease instead of a
  native slot, and the ledger records it under `lease`. A lock line may then
  also carry `ttl=<seconds>` (default 120), the lease length. The contract
  follows.

Parsing rules for these sections:

- **`provider: "<command>"`** (one line in `## Locks`, quotes optional) replaces
  the native files with leases from an external command, for slots shared
  across machines. See [Lock provider contract](#lock-provider-contract). With
  a provider, `slots=` and `DELEGATION_LOCK_<NAME>` are not consulted (the
  provider owns the slot count), `wait` still bounds how long `run` and `exec`
  poll, and `ttl` is the lease length passed to the provider. An empty or
  unquotable command, or a second `provider:` line, is a lint problem, and so
  is a lock named `provider` (`provider: slots=2`): the name is reserved.
  Without the line, locking is unchanged.
- **`## Deps`.** The dependency map for `check.py suggest --with-dependents`
  (requirement: a change in one unit must also run the validators of the units
  that depend on it). Units are repository-relative directories (a crate, a
  package), written with or without a trailing slash. One
  `<unit>: <dependent>, <dependent>` per line means the listed units depend on
  `<unit>`; closure is transitive, a unit listing itself is ignored, and a
  repeated unit, an absolute path or `..` is a lint problem. Alternatively (or
  additionally; the command wins) one `command: <cmd>` line names a command run
  from the worktree root that prints a JSON object `{"<unit>": ["<dependent>", ...]}`
  on stdout, for example a wrapper over `cargo metadata`. A failing, hanging
  (120 s) or malformed command makes `suggest --with-dependents` exit 2. A
  changed path belongs to the longest declared unit that contains it; a
  dependent's validators are those whose `paths=` match a file Git tracks under
  that unit (an untracked-only dependent contributes nothing). The repository
  root (`.`) is not a unit.
- **`## Rules`.** Free-text lines (bullets). `check.py brief` appends them to
  every brief, after the safety instructions and before the scratch directory,
  as `Rules (overlay ## Rules); these apply to everything you do here:`. Put
  project rules every subagent must obey here (what test output may never
  contain, where scratch goes, cache keys being append-only). One rule per
  line; a line starting with `#` is skipped like any heading, so don't start a
  rule with it. They are agent instructions, not enforcement.

## Lock provider contract

With `provider: "<command>"` under `## Locks`, `check.py run` (for a validator
with `lock=<name>`) and `check.py exec --lock <name>` hold a lease from the
provider for the lifetime of the foreground command instead of a native slot.
`<command>` is split with POSIX shell rules and run from the worktree root with
stdin closed, stdout and stderr captured, inheriting the environment plus the
holder's identity in `DELEGATION_LEASE_DELEGATION` (the delegation id, empty
for an unattributed `exec`), `DELEGATION_LEASE_COMMAND` (the validator name or
command line), `DELEGATION_LEASE_WORKTREE` (absolute path) and
`DELEGATION_LEASE_PID`, for the provider's own records. `acquire` and `release`
get 60 seconds each, `renew` one renewal period (below), after which a call
counts as an error. The provider must implement three subcommands, appended to
`<command>`:

| Call | Must do | stdout | Exit |
|---|---|---|---|
| `acquire <name> --ttl <seconds>` | Try once, without blocking, to take one free slot of lock `<name>` for `<seconds>` (an integer) | On success, the lease key on the first non-empty line (for example `cargo.0`); it is passed back as one argument, so it may contain spaces but not a newline; later lines are ignored | `0` acquired; `3` every slot is taken (busy); anything else is a provider error |
| `renew <key> --ttl <seconds>` | Extend the lease `<key>` by `<seconds>` from now | ignored | `0` renewed; anything else means the lease is gone |
| `release <key>` | End the lease `<key>` (a missing lease is fine) | ignored | `0`; anything else is reported, not fatal |

How check.py uses them:

- `acquire` is polled once a second while it exits `3` (so a `wait` under a
  second still allows one full poll); without `wait` it polls indefinitely,
  as native locks do. The lock's `wait` bounds the polling (exit 2, nothing
  recorded, same as native locks), and the last line of the provider's stderr
  is shown as the reason while waiting. An exit other than `0` or `3`, a
  missing or unrunnable executable, a timeout, or exit `0` without a key,
  refuse the run with exit 2 and record nothing. The lease is taken before the
  tree is hashed, so it covers the hashing as well as the command.
- `--ttl` is the lock's `ttl` rounded up to a whole second (default 120).
  `renew` runs in the background every `ttl/3` seconds while the command runs,
  concurrently with it but never concurrently with another `renew` or with
  `release`. A renewal that fails is printed to stderr and sets `lease.lost`
  in the ledger result; the command is not interrupted, so the result stays
  usable evidence but the provider may have handed the slot to someone else.
- `release` always runs when the command ends, including after a timeout or a
  forwarded signal; it waits for an in-flight `renew` first, at most one
  renewal period. If it fails the lease expires at its TTL.
- The ledger result records `lock`, `lock_wait_s` and a `lease` object
  (`provider`, `key`, `ttl_s`, `renewals`, `lost`); `lock_slot` is `null` under a
  provider. `check.py locks` prints the provider and each lock's ttl and wait;
  holders are the provider's to show.

The provider decides how many slots a lock has and may share them across
machines; `tests/fake_lease_provider.py` in the plugin repository is a reference
implementation backed by a directory.

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


## Repository material

Delegation material defaults to tracked `.agents/delegation/runbooks/` role
sources and `.agents/delegation/scripts/` approved rote scripts. The overlay stays
at `.agents/delegation.md`. These sections and directories are optional; general
repository tools stay in their own location and may be referenced intentionally.
Whether the judge creates or changes them without asking follows
`## Authoring` (default `allowed`).

A role's `runbook` is a repository-relative tracked source. `open` validates
tracking and containment (including symlinks), then copies it under external
`state:context/<source-path>` while holding the ledger lock. Every open delegation
that names that context pins its bytes, including delegations without a role.
Equivalent paths and in-state symlink references share the same pin; the
materialized destination itself must be a regular file, not a symlink.
Unchanged sources may share the pin; changed sources refuse to open until all
pins close. Refresh the tracked source on final use, preserving the current
external context; the next open after all pins close rematerializes it.
Lint warnings for material outside `.agents/delegation/` are nonfatal
and separate from unsafe-path errors. They allow intentional general tool refs.
Rote command inspection recognizes direct scripts, common interpreters and
`uv run --script`; complex shell wrappers receive best-effort inspection.
Review and stage approved source files before the first role open; the checker
does not stage repository material.

Lint lists files under `.agents/delegation/` that the overlay never names, and
anything there other than `runbooks/` and `scripts/`, as `unexpected`.

## Public lock interface

The public lock interface is
`python3 "$DELEGATION_CHECKER" --root "$PROJECT" exec --lock games --timeout 300 -- <command>`.
Configure `DELEGATION_CHECKER` as an installed skill's `scripts/check.py` or any
checkout's `plugins/delegation/skills/delegation/scripts/check.py`; quote paths
containing spaces. Use one foreground `exec` for each native process, with no
detached children. On POSIX, `exec` and `run` forward SIGTERM, SIGINT and SIGHUP
to the command's process group, kill the group if it is still alive one second
later, then exit with 128 + signal and release the lock; an orchestrator can
therefore cancel or time out a wrapped native process by signalling `check.py`.
Allow at least that grace before escalating to SIGKILL, which cannot be
forwarded. A declared `slots=N` permits N foreground processes across
worktrees of one repository. All coordinating processes must share the same
XDG state root. Optional outer orchestration wraps commands through this public
CLI; validators and general tools remain usable standalone without importing
checker internals.

The CLI is the supported compatibility surface; internal `delegation_check`
imports are not a supported API.
