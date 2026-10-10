# Delegation: pods of judge, execute and routine agents (2026-10-09)

What a design session on 2026-10-09 (run from `coordinator`) settled. A thread writing the plan or building any part of this hasn't seen that session; this file is its context.

## Why

In long sessions the top model does too much itself. In `game-decomp`'s decompilation work, an Opus session reads dozens of decompiled function bodies, probe logs and test output. Most of that context is **bulk**: worth something for one turn, then dead weight that makes every later turn costlier and forces an earlier compaction. The part worth keeping, the **gold** (working hypotheses, dead ends, which callers were checked and why a name was rejected), is a few thousand tokens.

Delegating bulk work to cheaper or lower-effort subagents protects the gold rather than competing with it. The session holding the hypotheses stays long-lived because its context stays mostly gold. Discoveries are written to a findings file as they happen, so a compaction only ever loses bulk.

This plugin packages that as a reusable **base** plus a per-repo **overlay**, so a second repo needs only an overlay file. A **pod** is one judge (the main thread) plus the subagents it delegates to.

## Decisions Rick made (don't relitigate)

- **Abstract tiers, mapped per host.** The base speaks only of `judge`, `execute` and `routine`. One `tiers.json` maps them to models and effort:

  | Tier | Claude Code | Codex |
  |---|---|---|
  | `judge`: plan, rule, review, diagnose | Opus 5.5, medium effort | Sol 6.1, medium effort |
  | `execute`: bulk reading, work pinned by a spec or oracle | Sonnet 5.5 | Sol 6.1, low effort |
  | `routine`: run, triage, summarise, mechanical edits | Haiku 4.5 | Luna 6 |

  Codex has only two usable models, so effort is a tier lever as well as the model. Same-model delegation (Sol to Sol) is still worth it for bulk work: it keeps the judge's context small, gives each task a clean context and allows parallel readers. It costs somewhat more total tokens and is not worth it for short tasks.
- **Overlays live in the repo they describe**, at `.agents/delegation.md`. Not in `AGENTS.md`, not centrally.
- **Activation is a one-line pointer in each repo's `AGENTS.md`** plus the skill. No hooks, no reliance on description triggering.
- **Agent definitions are generated from `tiers.json`** by `scripts/sync_marketplaces.py`, committed and never hand-edited, like the host manifests. Effort is only settable through definitions, so instruction-only routing was rejected. Headless `claude -p` / `codex exec` delegation was rejected as too heavy.
- **There is no `judge` definition.** The judge is the main session; Rick starts it at medium effort in T3. The skill states the expected judge setting but can't set it.
- **Evidence is deterministic where it can be:** registered validators, run through `check.py`, recorded in a ledger keyed by delegation id and git tree hash. Not keyed by time.
- **At most one writer per worktree.** Readers may run in parallel; writers run one at a time. Parallel writers (separate worktrees, commit-sha evidence) are out of v1.
- **Pods never depend on the relay.** The relay (`coordinator`, on hold) consumes a small interface defined here.

## Components

### In this repo: `plugins/delegation/`

| Piece | What it is |
|---|---|
| `plugin.json` | Portable manifest, version `0.1.0`, listed in `catalog.json`. |
| `tiers.json` | The only place host models and effort live. Per host, per tier: model id, effort (or absent for the host default). |
| `skills/delegation/SKILL.md` | The base rules (below). Names tiers, never host models. Tells the agent how to find and read the overlay and which agent definition each tier maps to on this host. |
| `skills/delegation/reference/overlay.md` | The overlay format and a worked example (game-decomp's). |
| `skills/delegation/reference/return-format.md` | The return format and the brief template, so briefs can quote it verbatim. |
| `skills/delegation/scripts/check.py` | Stdlib Python 3.10+. The ledger, tree hash, validators and overlay lint (below). |
| Generated agent definitions | `execute` and `routine`, one per host where the host supports them, written by `sync_marketplaces.py` from `tiers.json`. Each carries its model and effort, and a short body pointing at `return-format.md`. |

### In each consuming repo

| Piece | What it is |
|---|---|
| Pointer in `AGENTS.md` | `Delegation: follow the delegation skill; this repo's overlay is .agents/delegation.md.` |
| `.agents/delegation.md` | The overlay. |
| Ledger | `.agents/delegation-ledger.jsonl`, git-ignored by the repo. |

### Data flow

1. The session reads `AGENTS.md`, sees the pointer, and loads the skill when real work starts.
2. The skill reads the overlay (falling back to base defaults for missing sections).
3. To delegate, the judge runs `check.py open`, then starts the generated `execute` or `routine` agent with a brief built from the template plus the overlay's return fields.
4. The subagent works, runs validators through `check.py run`, and returns a structured report. It never writes to single-writer resources.
5. The judge reads the ledger for that delegation at the current tree, merges proposed changes, applies them to single-writer resources, writes findings, and runs `check.py close`.

## Base rules (`SKILL.md`)

1. **When to delegate.** When the work's tokens far exceed the brief plus the review: bulk reading (many files or functions), work a mechanical oracle verifies, or independent items that can run in parallel. Keep it in the judge when it's short, depends on the judge's accumulated hypotheses, or is a ruling.
2. **Choosing a tier.** `execute` for work that needs reasoning but is pinned by a spec or oracle. `routine` for work with an obvious right answer. Neither guesses: `execute` stops and reports when stuck, with its evidence; `routine` reports oddities without interpreting them.
3. **Brief.** Goal; inputs (paths); the files it may write; resources it must not write; the done condition or validators to run; the delegation id; the return format.
4. **Return format.** See below.
5. **Batching and concurrency.**
   - Group similar routine items into one call.
   - Readers (they write nothing and return data) may run in parallel up to the overlay's parallel limit, default 3.
   - **At most one writer per worktree.** A writer runs alone.
6. **Single writer.** For resources the overlay reserves, subagents return proposed changes. Only the judge applies them.
7. **Findings as they happen.** Write each discovery or ruled-out approach to the overlay's findings sink as soon as it's established, not at handoff. Minimum fields: id, date, claim, status (including `refuted`), evidence. Without an overlay sink, use the execution log.
8. **The judge checks; it doesn't redo.** It reviews ledger entries and the diff, and reads raw material only to dig into a specific doubt.
9. **Quota zones** (when a relay or a soft limit is in play): at `last-task`, open no new delegations; at `wrap`, close every open delegation before handing off. See "Pods and relay".

## Return format

```
Result: one paragraph.
Claims:
  - <claim> [checked: <ledger id>] | [cited: <refs>] | [asserted]
Fields: <the overlay's return fields>
Surprises: <anything unexpected>
Ruled out: <approaches tried and rejected, and why>
```

Length is capped (the overlay may set it; default about 400 words).

| Evidence kind | Backed by | Judge treats it as |
|---|---|---|
| **checked** | A ledger id from a registered validator, at the current tree | Accepted |
| **cited** | References (paths, lines, addresses, symbols) that a validator confirms *exist* | References accepted; reasoning judged |
| **asserted** | Prose only | A hypothesis; may drill in |

A claim that something passed must be `checked`. A validator that fails, or a ledger entry at a different tree, downgrades the claim to `asserted`. This is the same claims-with-proof vocabulary as `visual-audit`, whose report could later read the ledger directly.

## `check.py`

```
check.py run <validator> --delegation <id>    run a registered validator, append its result
check.py query --delegation <id> [--tree current] [--json]
check.py open  --delegation <id> --tier execute|routine --brief <path>
check.py close --delegation <id> --outcome done|stuck|abandoned
check.py pending [--json]                      open delegations with no close
check.py tree                                  print the current tree hash
check.py lint                                  check the overlay
```

**Ledger entry** (one JSON object per line): `schema`, `event` (`result` / `open` / `close`), `delegation`, `timestamp`, and for results: `validator`, `command`, `exit`, `duration_s`, `tree`, `output_sha256`, `output_tail`.

**Tree hash.** The hash of the working tree exactly as it is, including uncommitted changes and untracked files that aren't ignored, computed without touching the real index or committing:

```sh
GIT_INDEX_FILE=<tmp> git add -A && git write-tree
```

Extra inputs that git ignores (golden traces, built binaries) are folded in when the overlay lists them under `## Extra inputs`: the tree hash becomes a hash of the git tree plus each listed path's content hash. A query with `--tree current` recomputes it, so any change since a check makes that check stale.

**Not tamper-proof, by design.** It guards against sloppiness (a filtered test run, a pass before the last edit, an invented address), not an adversary. For cheap validators the judge can simply rerun them. The ledger matters most for expensive ones (probe batches, trace replays) the judge shouldn't repeat.

## Overlay format (`.agents/delegation.md`)

Markdown with fixed `##` headings. Every heading is optional; missing ones fall back to base defaults. `check.py lint` flags unknown headings and validators referenced but not registered.

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
| `## Return cap` | Max return length | ~400 words |

### Worked example: `game-decomp`

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

`trace-diff` is registered once the Rust plan's Task 1 produces golden traces, and the trace manifest then goes under `## Extra inputs`.

## Pods and relay

The relay (a coordinator repo, on hold) relays a pod's **head**, the judge thread, between providers. The split:

- **The pod owns routing:** tiers, what to delegate, briefs, evidence.
- **The relay owns** the baton, provider choice, quota zones and handoffs. It never sees tiers.

On a handoff the incoming head reads the same overlay and resolves the same tiers to its own host's models through `tiers.json`. Findings, the ledger (keyed by tree, so a Codex head can trust checks a Claude executor recorded at the same tree) and the execution log carry the gold across.

**The interface the relay consumes:**

- `check.py pending --json`: open delegations. Subagents belong to the provider session that started them and can't survive a provider switch, so the relay's release checks require this to be empty.
- The quota-zone rules in base rule 9.
- Open delegations are a field the relay may show in `relay.py status`.

The relay's side of this is recorded in an addendum to its spec.

## Verification

**Step 0, before building the Codex side.** Find out what a Codex plugin can ship besides skills, and whether a Codex subagent can be given a model and effort. Record the result and versions in `docs/verification.md`. If yes, the generator writes Codex definitions. If no, the Codex skill states the tier in the brief and uses a same-model subagent at the default effort. Either way nothing is assumed.

Also confirm on Claude Code that a plugin's agent definitions are picked up and that their `model` and effort frontmatter takes effect.

**Tests** (stdlib `unittest`, alongside the existing suite):

- **Generator:** `tiers.json` produces the expected definitions; `sync_marketplaces.py --check` fails on a hand-edited generated file.
- **`check.py`:**
  - The tree hash is stable when nothing changes, and changes on an edit, a new untracked file, and a change to a declared extra input.
  - It never modifies the real index.
  - `run` appends a result; `query` filters by delegation and by tree; a check at an older tree is excluded under `--tree current`.
  - `open`/`close`/`pending` track lifecycle; an unclosed delegation shows in `pending`.
  - `lint` reports unknown headings and unregistered validators.
- **Lifecycle:** `verify_lifecycle.py` installs into a disposable profile and confirms the skill and generated definitions appear on each host.
- **Not tested, and not claimed:** whether models route well. That's the pilot's job.

**Error handling:**

- No overlay: base defaults apply; the skill says so once.
- A validator fails: the ledger records it; the claim is `asserted`, not `checked`.
- An executor is stuck: it stops and reports its evidence; the judge closes the delegation as `stuck`.
- A host lacks the generated definitions: the same fallback as the Codex case in step 0.

## Rollout

1. **Plugin:** `delegation` 0.1.0 in this repo, verified and installed on both hosts.
2. **game-decomp pilot** (its own change in `game-decomp`):
   - the overlay and the `AGENTS.md` pointer
   - `refuted` added to the findings statuses
   - the `unit`, `probes` and `refs` validators, writing `research/modules/check_refs.py` (every claimed address is a function in `functions.csv`; every cited Windows match is in the match table)
   - `.agents/delegation-ledger.jsonl` git-ignored
   - run the Rust plan's **Task 2** (naming across module files) as the pilot, as parallel readers
   - judge it roughly: quota points per task from a coordinator repo, and how much of the judge's context is free at the end
3. **coordinator** (its own change): `projects.md` rows for `game-decomp` and this repo, and a note of which repos have an overlay.
4. **A second repo** later, with only an overlay. If it needs more, the base is missing something.

## Out of scope / later

- **Parallel writers.** Separate worktrees per writer, each committing on its own branch, evidence keyed by commit sha, the judge merging and re-validating. Blocked first by a conflict: Claude Code's built-in worktree isolation creates worktrees inside the repo, and Rick's global rule puts worktrees only under `a separate worktree`.
- A `visual-audit` report reading the ledger.
- Overlays overriding tier models. Tiers are global until a repo needs otherwise.
- Tamper-proof evidence.
