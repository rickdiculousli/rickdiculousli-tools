# Long-horizon: reliable progress across sessions (2026-10-11)

Status: proposed specification, based on Rick's approval to generalize the
game-decomp workflow. Revised after written-spec review to add deterministic
checks, an interview-led setup flow, default session closure, the goal
lifecycle and friction controls. Implementation planning is linked below.
This document does not add an installed plugin or change any consuming repository.

The [implementation plan](../plans/2026-10-11-long-horizon.md) resolves the
implementation contracts. The
[XDG state and locks addendum](2026-10-11-xdg-state-and-locks-addendum.md)
defines the runtime XDG state paths and specifies separately
reviewable delegation migration work and the shared weekly cleanup convention.

## Purpose and success

Package the practices that let an agent advance a large project over many
sessions, worktrees, hosts and model changes without drifting into later work,
forgetting evidence or mistaking a successful batch for a completed goal.

The plugin is named `long-horizon`. It works with a solo agent and optionally
composes with `delegation`: long-horizon selects and preserves work across
sessions; delegation assigns workers and records execution evidence within a
session. Both hosts consume the same skills, templates and script.

Success means a fresh session can identify the current milestone, select the
next eligible task, determine whether its host has the necessary inputs, recover
relevant decisions and evidence, and finish a bounded batch with an accurate
handoff. It must never infer acceptance from missing, skipped or stale checks.
A user with only a vague aim can reach that state through setup, and a
completed goal ends with a signed-off record and a harness that stops loading
itself into every session. Users should rarely feel the rules: only a few are
hard, and the rest yield to a sentence from the user.

Rules that are pure functions of tracked files and Git state are enforced by a
script, not by prose: selection, goal consistency, handoff staleness, evidence
freshness, the milestone close gate and closure verification. Skills keep the
judgment: interviewing, planning, interpreting blockers and deciding scope.

## Lessons from game-decomp

These are observations from `game-decomp` at revision
`ea0fd97a6d0f5e3f7abddf83867070a131d26e57`, not claims that this plugin has been
implemented or evaluated. Source paths below are relative to that repository.

| Observed practice or failure | General requirement | Source |
| --- | --- | --- |
| Isolated later-stage ports were accepted before golden traces existed; their real calling context still needs acceptance. | Preserve bounded acceptance, enforce milestone order, and require integration evidence before closing an integrating milestone. | `docs/goals.md`, Existing partial work |
| Goals contain ordered tasks, host tags such as `(Mac)`, `(linux)`, `(any)`, and an explicit “Done when” condition. | Separate task completion, batch completion and milestone acceptance; tasks declare capability needs in a parseable form. | `docs/goals.md` |
| Early milestones built oracles and golden traces before porting. | Planning puts evidence-building and de-risking milestones first. | `docs/goals.md` |
| Startup prepares context and reports host capabilities without running tests or installing tools. | Resume is preparation, with named readiness levels and actionable missing inputs. | `tools/resume.py` |
| The startup helper finds delegation by globbing a versioned plugin cache under the home directory. | Repositories locate plugin scripts through a declared path or environment variable and fail closed. | `tools/resume.py` |
| Fixture bytes persist outside Git; the live ledger belongs to a worktree and is disposable. | Durable evidence must survive independently of scratch state; referenced bytes need an explicit recovery route. | `docs/delegation/README.md` |
| A fixture skip cannot establish acceptance; cheap checks and scoped gates avoid repeated full-suite runs. | Validation scope and accepted exceptions are repository policy; evidence freshness is scoped so documentation edits do not invalidate it. | `.agents/delegation.md`, Oracle |
| Ghidra changes invalidate a check even when the source tree stays unchanged. | Acceptance includes external input digests, not just a Git tree hash. | `.agents/delegation.md`, `ghidra-sync` |
| Descriptive static names, runtime observations and unproved causes have different statuses. | Findings retain their evidence class, domain and uncertainty. | `research/findings.jsonl`, `docs/handoff.md` |
| The handoff grew to 131 lines and absorbed standing policy from `AGENTS.md`. | The handoff has a template and a size budget; policy lives in the overlay or `AGENTS.md`. | `docs/handoff.md` |
| Host-specific merge, push and sync rules have standing authorization and exceptional stop conditions. | Follow explicit local integration policy and record each step's outcome separately. | `AGENTS.md`, Workflow |
| Every batch ends verified, merged to `main` and pushed, so the next session starts fresh from `main`. | Default closure is validation, merge to the default branch and push; users may choose otherwise. | `AGENTS.md`, Workflow |

These practices motivate the design; one project is insufficient evidence that
the plugin improves cost, speed or correctness in every repository.

## Boundaries and alternatives

A separate plugin with optional delegation integration is preferred. Adding
these rules to delegation would make multi-session progress depend on worker
routing. A larger autonomous scheduler would introduce budgets, orchestration
and state recovery before the simpler workflow has been tested.

| Owner | Responsibility |
| --- | --- |
| Long-horizon | Goal interview and planning, milestone selection, startup context, readiness interpretation, durable continuation, evidence freshness and batch closure |
| Delegation | Tiers, briefs, agents, concurrency, locks, validators, live ledger, tree hash and pending-worker checks |
| Repository | Goal content, acceptance authority, domain bootstrap, evidence stores, validation budget and integration authorization |
| Host or user | Session launch, worktree creation, tool permissions, model selection, subscription budget and exceptional approvals |

Long-horizon does not spawn agents, maintain a second validator ledger, define a
second worktree tree hash, run validators, supply fixture storage, create
worktrees, switch providers or authorize remote actions. No hooks, background
loop, automatic quota polling, network access or database are required in v1.
It does not replace brainstorming or implementation plans: a roadmap orders
work; a plan explains how to perform an approved piece of work.

## Rules and friction

Rigid rules that block users get bypassed or uninstalled. Long-horizon keeps a
short list of hard rules and treats everything else as a default that one
sentence from the user can override.

Hard rules, which the agent never bypasses:

- Never report PASS, or close a milestone or goal, without evidence or an
  exception the user explicitly accepted.
- Never mark a goal done without sign-off when the overlay requires it.
- Never merge, push or sync outside the recorded closure policy.
- Never destroy user work or history.

Everything else, including task selection, milestone order within a session,
batch size and checkpoint detail, yields to an explicit user instruction. The
agent complies without arguing and logs one line in the handoff (`Override:`
what, why, what remains). The original work is preserved unless the user
cancels it.

Friction rules:

- **A failed gate offers options instead of a dead end.** It names exactly what
  is missing and offers: run the check; mark the task done and leave the
  milestone open; or, only on the user's explicit word, record an accepted
  exception (`Accepted-Exception: check=<name> reason=<text> by=<user>` trailer).
  `gate` accepts a milestone whose missing evidence is covered by accepted
  exceptions, and the completion record lists them.
- **When everything is blocked, offer choices instead of halting.** Propose
  working to unblock the first task, researching the blocker, a specific user
  decision, or clearly labeled off-milestone work if the user agrees.
- **Off-goal requests are done, not refused.** A quick unrelated fix mid-goal is
  done and noted in the handoff as off-goal; it does not count toward the
  milestone and earns no lecture.
- **Lint has two levels.** Only errors that would make selection or acceptance
  wrong block (two current markers, a done milestone with open tasks, a
  malformed overlay); an unparseable goals file degrades to manual selection.
  Handoff size, missing task IDs and template gaps are warnings.
  `lh.py lint --fix` shows mechanical repairs as a diff and applies them on
  approval.
- **Ceremony scales with the batch.** A small batch gets a one-line handoff
  update and the normal closure. Refinement proposals, parked-item triage and
  completion records happen only at milestone or goal boundaries.
- **Questions are batched.** Collect them for one message at a natural break;
  ask mid-batch only when work cannot continue without the answer.
- **Errors carry their fix.** Every `lh.py` finding prints the command or the
  sentence to say that resolves it.

## Composition with delegation and quota

Documented in both plugins' guidance:

| Situation | Use |
| --- | --- |
| A goal spanning sessions | long-horizon |
| ...whose batches include bulk mechanical work, validators worth a ledger, or parallel reading | long-horizon + delegation |
| A large task finished in one session | delegation alone |

- **One survey, two setups.** When long-horizon setup's survey finds validators
  or bulk work and delegation is not set up, it suggests running delegation setup
  next and passes its survey notes along, so the user is not asked twice. It
  suggests; it never installs or configures delegation itself.
- **Checks are named once.** A `Done when` names delegation validators as
  `validator:<name>`; their ledger results become evidence trailers with the
  ledger id. Long-horizon never restates validator commands.
- **Quota sizes the batch, opt-in.** If the overlay enables it and the `quota`
  plugin is installed, resume makes one quota call at session start to size the
  batch ("20% left: one small task") and to suggest which provider to use for the
  next session. This is a single call, not polling, and never blocks work.
- **A combined session:** resume picks the task, delegation runs the bulk work
  and validators, checkpoint reuses their ledger results as evidence and then
  merges and pushes.

## Plugin contents

Proposed layout follows this repository's portable packaging convention:

```text
plugins/long-horizon/
  plugin.json
  skills/
    setup/SKILL.md
    setup/reference/interview.md
    setup/reference/goals-template.md
    setup/reference/handoff-template.md
    setup/reference/cheatsheet.md
    resume/SKILL.md
    resume/scripts/lh.py
    resume/reference/overlay.md
    resume/reference/goals-format.md
    resume/reference/readiness.md
    checkpoint/SKILL.md
    checkpoint/reference/evidence.md
```

Authored identity belongs in `plugin.json` and `catalog.json`; host manifests
and marketplaces are generated with `scripts/sync_marketplaces.py`. Initial
released version is `0.1.0`. `lh.py` is Python 3.10+ standard library, run as
`python3 <resume-dir>/scripts/lh.py`; setup and checkpoint reach it through the
sibling path `<skill-dir>/../resume/scripts/lh.py`. No consumer build step or
added runtime dependency is needed. Existing domain helpers remain in their
repositories. The README's long-horizon section carries the cheat sheet, the
composition table and a sample session walkthrough.

## Deterministic checks (`lh.py`)

`lh.py` reads tracked files, ignored long-horizon state and Git; it never runs
validators, installs anything or touches the network. When delegation is
active it calls delegation's `check.py` (path from the overlay) for the tree
hash, lint and pending state rather than reimplementing them. Exit codes: 0 OK,
1 findings, 2 usage or environment error. Every command accepts `--json`; the
default text output is compact enough to paste into a session.

| Command | Checks and output |
| --- | --- |
| `lint [--overlay PATH] [--fix]` | Errors: overlay headings and syntax; referenced paths exist; activation pointer reachable from `AGENTS.md` and from `CLAUDE.md` (directly or via `@AGENTS.md`); goals consistency; no live agent IDs or credential-shaped strings in the handoff; delegation `check.py lint` when active. Warnings: missing task IDs, missing handoff template sections, handoff over its size budget. Exit 1 only for errors. `--fix` prints a diff of mechanical repairs (status markers, task IDs, template headings) and applies it only with `--apply`. |
| `status` | Checkout identity (main or linked worktree, branch, default branch, dirty paths); current goal, current milestone and its `Done when`; next eligible task for this host and tasks skipped for capability; open blockers; handoff staleness; unfinished closure steps; readiness levels from the startup report; delegation pending state. Prints only the current milestone's section and context links, not the whole roadmap. With no active goal or a dormant overlay it prints one line saying so. `--brief` is the user-facing view: goal and milestone progress (`Goal: port · milestone 3/9 · task 3.2`), the next task, and a **Needs you** list of sign-offs, pending decisions, human-only steps and missing inputs. |
| `evidence record` / `evidence find <check>` | Writes or reads commit trailers (below) and reports whether each item is fresh for the current checkout. |
| `gate [--base REV]` | Compares goals with the base revision. Every newly checked milestone needs, for each check its `Done when` names, a fresh passing evidence reference or an accepted exception; every newly checked task needs a cited evidence ID or commit; a newly completed goal additionally needs all its milestones done, its own `Done when` evidence and a `Signed-off:` line when the overlay reserves goal completion for the user. Edits to order, scope or criteria are flagged for the ownership policy. On failure it lists the options from Rules and friction. |
| `closure verify` | Verifies the Git-checkable closure claims in `the resolved XDG worktree payload’s closure.json`: committed, merged into the target branch, and pushed as of the last fetch (no fetch is performed). Host sync remains a recorded claim. |

Goal consistency, enforced by `lint` and `status`: goals and milestones are
each ordered; at most one goal and one milestone in it are marked current, and
they are the first incomplete ones; anything marked done has no open children;
nothing is done while an earlier sibling is open; task IDs are unique. An unparseable goals file is reported, and the skills fall back to
manual selection with that limitation stated.

Selection is a pure function: the first goal that is neither done, shelved nor
dropped, its first incomplete milestone; within it, the
first unchecked task that has no open blocker and whose capability tags are
satisfied by the readiness report. Capability-ineligible tasks are listed, not
hidden. If no task is eligible, `status` reports the blockers and missing
inputs and selects nothing; it never advances to a later milestone.

Handoff staleness uses Git, not a self-referential hash: the last commit that
touched the handoff, the commits since then outside the overlay's non-code
paths, whether goals changed since then, and whether the handoff is dirty.

Pilot scenarios that depend only on files and Git are unit tests over
disposable repositories in this repository's `tests/`, so most of the
acceptance table runs on every change without model calls.

## Consuming repository contract

Activation is an explicit pointer in `AGENTS.md`, also reachable from
`CLAUDE.md`:

```text
Long horizon: follow the long-horizon resume and checkpoint skills; this repo's overlay is .agents/long-horizon.md.
```

Setup proposes this pointer and a tracked overlay. Defaults are
`docs/goals.md` and `docs/handoff.md`, but existing paths are adopted rather
than replaced. The overlay format, parsing rules and schema version are in
`resume/reference/overlay.md`. Headings:

- **State:** `active` or `dormant` (after wind-down).
- **Goals and ownership:** goals path; who may change milestone order, scope and
  `Done when`; who may refine tasks within the current milestone; who may mark
  tasks, milestones and goals complete; goal sign-off `user` or `agent`.
  Defaults: agents may add, split, reword or reorder tasks within the current
  milestone, logging each change in the handoff, and record supported task and
  milestone completion; the user owns milestone order, scope and `Done when`,
  and signs off goals.
- **Goals format:** optional overrides of the default markers below.
- **Continuation:** handoff path, handoff size budget, durable findings and
  acceptance paths, and non-code paths whose edits never invalidate evidence
  (handoff, goals, findings by default).
- **Startup:** optional repository bootstrap command, its permitted effects,
  generated context path and readiness report path.
- **Capabilities:** each task tag mapped to the readiness levels it requires;
  `any` or no tag requires none.
- **Evidence:** delegation `check.py` path or environment variable when used,
  validator policy reference, per-check scope pathspecs, external input digest
  commands (each must be cheap and read-only), and allowed skips with their
  precise scope.
- **Batch:** what bounds a session batch (default: one task or one blocker
  resolution, then checkpoint), and whether resume consults `quota` once to size
  it (default off).
- **Integration:** target branch; authorized commit/merge/push/sync steps, their
  order and exceptions; ownership of shared documents. Default, offered in
  setup and recorded only when the user accepts it: validation, then commit,
  merge to the default branch and push at the end of every batch, as standing
  authorization. Rationale shown to the user: the next session starts from a
  clean, current default branch with a small context instead of inheriting this
  session's accumulated transcript, which costs more and degrades judgment as it
  grows. Alternatives the user may pick instead: commit only, merge without
  push, open a pull request, or ask each time.

Default goals format, documented in `resume/reference/goals-format.md`:

```markdown
# Goal: Faithful native port — current
Done when: validator:full-match-replay passes on the scenarios-v1 corpus.

## 3. Simulation spec — current
Done when: validator:sim-headers passes and every thing field is confirmed against traces.
Context: research/modules/simulation.md
- [x] [3.1] Every function in the simulation modules named in Ghidra. (any)
- [ ] [3.2] `thing.h` complete, each field confirmed against trace bytes. (Mac)

## Parked
- Widescreen mode (2026-10-11)
```

A goal is a level-1 `# Goal:` heading with its own `Done when` over ordered
milestones; a file without goal headings is one implicit goal whose `Done when`
is its last milestone's. Status markers are `— done`, `— current` or none; goals
may also be `— shelved` or `— dropped` with a `Reason:` line. A completed goal
carries `Signed-off: <who>, <date>` when sign-off is required. A `## Parked`
section holds ideas captured mid-work; selection ignores it. Task IDs in
brackets are
optional; without one, a task is identified by milestone number plus a short
digest of its text, and `lint` warns that edits will change it. A trailing
parenthesized tag list names capabilities. `Context:` lines are the minimal
links resume loads for that milestone.

The startup readiness report, documented in `resume/reference/readiness.md`,
is JSON:

```json
{"version": 1,
 "levels": {"fixtures": {"ready": true, "strength": "sha256", "detail": "12 files"},
            "native": {"ready": false, "strength": "exists", "detail": "app missing"}},
 "missing": [{"input": "reference app", "needed_for": ["native"], "recover": "tools/CAPTURE.md#app"}]}
```

`strength` records how hard the check was (exists, size, sha256, probed); no
level means tests passed. Helpers in the repository find plugin scripts only
through the overlay or an environment variable and fail closed when missing;
no author-specific clone, cache version or machine name belongs in the base.
The overlay references delegation's validators and locks rather than restating
them. It is configuration to inspect, never automatic authorization to execute
an unapproved command.

No overlay means resume reports that setup is missing and works from explicit
session instructions and existing goals/handoff if unambiguous. It invents no
integration policy. A conflicting or malformed overlay is reported and dependent
actions stop; independent read-only context gathering may continue.

## Setup skill

Use when asked to enable, configure or update long-horizon, or to start or
re-plan a long-running goal in a repository. Setup works from any checkout of
the repository and from any starting point, from a vague aim to an existing
roadmap. Write nothing until the user approves the draft.

Setup offers two depths. The **quick path** sets up one goal with all defaults
in at most about five questions, any of which the user may answer with "you
decide"; the overlay can then be little more than the goals path. The **full
path** runs the whole interview below. Start quick unless the project is large,
the user asks for depth or the survey finds existing policy to adopt; *update*
mode can deepen a quick setup later.

Assume the user may be new to the workflow. Explain the concepts once, in plain
words, using their project as the example: goal, milestone, task, done-when,
handoff, batch. Avoid terms such as oracle, ledger or evidence trailer unless the
user uses them first.

### 1. Locate the checkout and mode

Run `lh.py status` (it works without an overlay) and record:

- **Checkout:** main checkout or linked worktree (`--git-dir` versus
  `--git-common-dir`), current branch, default branch, dirty paths. Setup writes
  only into the current checkout. It never creates, removes or switches
  worktrees or branches; T3 Code or the user does that.
- **Existing setup elsewhere:** whether the default branch already has an overlay
  (`git show <default>:.agents/long-horizon.md`) or another branch or worktree
  has an unmerged one (`git log --all -- .agents/long-horizon.md`). If so, start
  from that version and say so, rather than drafting a divergent copy.
- **Mode:** *new goal* (no roadmap), *adopt* (existing goals, plans or
  handoff), *update* (overlay exists; run `lh.py lint` first and propose edits,
  not a rewrite), *add a goal* to an active or dormant setup (reactivating a
  dormant one), or *wind down* (see Goal lifecycle).
- **Delegation:** whether its overlay and pointer exist, and `check.py lint`.

Entry from a worktree is normal: the setup lands on that branch and becomes
active for other worktrees only after the repository's integration policy
merges it. Entry from the default branch with unrelated dirty changes is also
allowed; setup touches only its own files and stages nothing else.

### 2. Interview

Always interview, in every mode; even an existing roadmap may no longer match
what the user wants. Follow `setup/reference/interview.md`: conversational,
a few questions at a time, reflecting answers back in short summaries. Vague
answers are acceptable; offer concrete options and examples rather than
demanding precision. Cover:

- **Outcome:** what they are trying to accomplish and why; who it is for.
- **Done:** how they would recognize success; what would be good enough.
- **Current state:** what exists, what was tried, what is known to be wrong.
- **Proof:** what can tell right from wrong (reference behavior, golden data,
  tests, a human judgment) and whether it exists yet.
- **Constraints:** hosts and inputs, licensing or data that must not leave a
  machine, budget, deadlines, things that must not change.
- **Autonomy:** which decisions agents may make alone, which need the user, and
  how often the user wants to be consulted.
- **Session closure:** offer the default as a recommendation with its reason:
  every batch ends with validation, merge to the default branch and push, so
  each session can end and a fresh one continues from `main` without this
  session's context. Record what the user actually chooses, including host sync
  steps and cases that must stop and ask.
- **Unknowns:** risks and open questions the user already suspects.
- **Batch sizing:** whether to consult `quota` once per session (only offered
  when the quota plugin is installed).

Survey the repository in parallel (read-only): instructions, existing goals,
plans, handoff, findings, startup helpers, delegation policy, validators,
bulk-work patterns, external inputs, hardcoded plugin-cache paths, and churning
untracked files. Use the survey to ask better questions and to avoid asking what
the repository already answers. If it finds validators or bulk work and
delegation is not set up, note the suggestion for step 4.

### 3. Plan together

Turn the interview into ordered milestones, helping the user shape a vague aim:

- Put evidence first: early milestones build the oracle or proof the later work
  will be judged by, and retire the riskiest unknowns.
- Each milestone states an outcome and a `Done when` that names checkable
  evidence; where the proof does not exist yet, building it is a task.
- Detail the first one or two milestones with tasks and capability tags; keep
  later ones coarse, to be refined when they become current under the ownership
  policy.
- Turn unknowns into explicit research tasks or recorded open questions rather
  than guessed scope.
- When adopting, preserve existing order, checkboxes, evidence and handoff
  contents; propose only the annotations needed to parse (status markers,
  capability tags, optional IDs), never reorderings or rewordings.

Present the plan, iterate, and get the user's agreement. Setup does not decide
the project's scope.

### 4. Draft, dry-run and ask

Show in chat:

1. The goals draft or annotations, and an initial handoff naming the first
   concrete action.
2. The overlay draft, leaving out headings with nothing real; the default
   ownership from the overlay contract applies unless existing policy or the
   user says otherwise.
3. The output of `lh.py status --overlay <draft>` against the drafts: current
   milestone, next eligible task for this host and any consistency errors. The
   user confirms this selection is what they expect.
4. A sample of the next session in plain words, for example: "Open a new
   session and say *continue*. I'll do 3.1, run the tests, merge, push, and tell
   you to start fresh."
5. The pointer line and where it goes (`AGENTS.md`, plus `CLAUDE.md` if it does
   not import `AGENTS.md`), XDG state/retention instructions, and ignore
   suggestions for churning files.
6. The delegation suggestion, when the survey produced one, with what it would
   add for this project.
7. Remaining open questions only for what the interview and survey could not
   establish, batched in one message.

Wait for approval or edits.

### 5. Write and prove

Write the approved files; commit only if asked or if standing integration
authorization covers setup. Then:

1. `lh.py lint` reports OK.
2. `lh.py status` reproduces the selection confirmed in step 4.
3. If the user authorizes it, run the startup helper once and confirm its
   readiness report parses.
4. `lh.py evidence find` resolves existing evidence at the current checkout or
   reports none.
5. With delegation active, `check.py pending` reports no open delegations.

Report one table of these checks and results, what was written, where it is
active (this branch only until integrated, or the default branch), and what
remains missing. End with the cheat sheet from `setup/reference/cheatsheet.md`:

| You want to… | Say… |
| --- | --- |
| Keep going | "continue" |
| See progress | "where are we?" |
| Save an idea | "park: …" |
| Change the plan | "reprioritize …" (within your ownership settings) |
| Stop now | "pause" (checkpoints without starting anything new) |
| Finish or shelve a goal | "sign off" / "shelve this goal" |

If the user accepted the delegation suggestion, offer to run delegation setup
next with the survey notes. Setup does not install tooling, capture inputs, run expensive
acceptance gates, create repository helper scripts or change unrelated plugin
configuration; such actions need their own task authorization.

## Resume skill

Trigger only when the activation pointer is present, at session start or when
the user says "continue", "keep going" or asks where things stand. "Where are
we?" alone prints `lh.py status --brief` and starts nothing.

1. Run `lh.py status`. It reads the overlay, the current milestone's section and
   context links, the handoff and Git state. Do not load the whole roadmap or
   archive unless the task needs it. If it reports no active goal (all complete,
   or a goal awaiting sign-off), say so, surface any pending sign-off or
   wind-down offer, and do no goal work.
2. Preserve unrelated uncommitted work. If the handoff is stale or disagrees
   with goals or the tree, reconcile: goals define scope; a newer handoff cannot
   silently reorder them.
3. Run only the authorized startup helper and re-run `lh.py status` to pick up
   its readiness report. Startup may prepare declared external runtime cache, but does
   not perform acceptance, installs, downloads, captures or cache regeneration by
   default. If a helper fails, preserve the diagnostic and continue only work
   whose inputs and safety do not depend on the failed preparation.
4. Take the task `status` selected. If it is blocked in a way `status` cannot
   know, record the blocker in the handoff's `## Blockers` section (task ID,
   reason, needed input or decision) and re-run `status`. Never advance to a later
   milestone because its work is easier or this host lacks a capability. If
   nothing is eligible, offer the choices from Rules and friction and wait.
5. If the overlay enables it, make one `quota` call and size the batch.
6. Give the user a three-line brief: where we are, what this batch will do, and
   anything needed from them. Then start without asking for confirmation, unless
   a decision is pending. Keep observed facts, hypotheses, bounded prior
   acceptance and open integration gaps distinct, and resume normal
   implementation/research workflows.

During work: "park: …" appends to `## Parked` without reordering anything; an
off-goal request is done and noted; an authorized detour must unblock the
current task, with its reason and return condition recorded. Changes to
milestone scope or order follow the overlay's ownership policy. An explicit user
request overrides selection and is logged as an `Override:`.

## Checkpoint skill

Use when finishing a batch, handing over to another session or host, when
context is running low, or in response to an explicit pause. It also guides
recording findings during work: discoveries and rejected approaches belong in
the durable sink when established, not only in a final transcript. If
delegation already governs that sink, follow its single-writer and open-check
rules instead of creating another findings stream.

1. Review final changes and evidence. Close or explicitly hand back workers using
   delegation when active; inspect pending state through its checker. Never reset
   a ledger, close someone else's work blindly or treat a dead worker as resumed.
2. Run `lh.py evidence find` for each required check. Reuse fresh evidence; run
   only checks without it, proportional to the changed component and integrated
   batch. Failed, skipped, unstable or out-of-domain results remain limitations,
   not PASS.
3. Record acceptance with `lh.py evidence record` (commit trailers) or in the
   overlay's findings or component notes. A disposable log path alone is
   insufficient.
4. Update the handoff and permitted task statuses, scaled to the batch (a small
   batch needs one line), then run `lh.py gate` and `lh.py lint`. Mark a
   milestone complete only when `gate` passes and the agent has authority to
   mark it; if `gate` fails, present its options rather than stopping. Passing isolated functions cannot close a
   whole-call integration milestone. A finished batch may leave every milestone
   checkbox unchanged. When a milestone or goal completes, follow Goal lifecycle.
5. Perform the overlay's closure sequence (by default validation, commit, merge
   to the default branch, push), recording each step in
   `the resolved XDG worktree payload’s closure.json`, then run `lh.py closure verify`. Committed,
   merged, pushed and host-synced are separate claims. On failure, preserve
   completed steps and state the exact remaining operation; do not force a merge,
   rewrite history or restart successful steps unnecessarily. With no recorded
   closure policy, ask before merging or pushing.
6. Return a concise result with the handoff link, commit when made, validation
   scope, verified closure state, limitations, next concrete task and the
   **Needs you** list from `status --brief`, with any questions batched. When
   closure fully succeeded, recommend ending the session and continuing in a
   fresh one rather than starting the next task here.

A pre-commit handoff records the batch's verified state and intended closure
steps; it must never claim that a future push or sync already succeeded. Later
outcomes are reported in the final response and kept in ignored closure state;
`status` shows unfinished closure to the next session in the same worktree.

An explicit pause overrides normal persistence. Preserve a useful checkpoint
and report unfinished checks or integration; do not start more implementation
or invoke unauthorized closure actions merely to satisfy the template.

## Goal lifecycle

**Milestone complete.** After `gate` passes and the milestone is marked done,
the next milestone becomes current. If it is still coarse, the checkpoint
writes its tasks and capability tags under the default ownership (agents refine
the current milestone) and logs them in the handoff; when the overlay reserves
refinement for the user, it records a proposal as a pending decision instead.
Its `Done when` and lessons that change later milestones are proposed, never
applied silently. Parked items are triaged here: each is proposed for a
milestone, kept parked or dropped, in one batched question.

**Goal complete.** When the last milestone closes, the agent checks the goal's
own `Done when` with fresh evidence. It then writes a completion record to
`docs/goals-archive/<date>-<goal-slug>.md` (path configurable): outcome, the
evidence trailers per milestone, accepted limitations and exceptions, refuted
approaches worth remembering, and follow-ups not done (remaining parked items
included). With sign-off `agent` the goal is marked done once `gate` passes.
With the default `user` sign-off the goal stays `current` with an `Awaiting sign-off` handoff entry until the
user approves; the agent then adds `Signed-off:`, marks the goal done and
replaces its milestones in the goals file with a one-line link to the record, so
later sessions do not load finished work. `gate` refuses the done marker
without the record and, when required, the sign-off line. If the user declines
sign-off, their objections become tasks in a new or reopened milestone.
The next goal, if any, becomes current.

**Shelve or drop.** Not every goal finishes. On the user's word the goal is
marked `— shelved` or `— dropped` with a `Reason:` line and a short record of
where it stopped, written the same way as a completion record. Selection skips
it; a shelved goal resumes by removing the marker. Wind-down treats shelved and
dropped goals like completed ones.

**All goals complete: wind down.** When no active goal remains, `status` reports it,
and the checkpoint (or the next resume) offers a partial teardown. It runs as
setup's *wind down* mode, with a draft shown and approved like any setup:

- Remove the activation pointer from `AGENTS.md`/`CLAUDE.md`, so sessions stop
  loading long-horizon instructions and resume never triggers.
- Set the overlay to `dormant` and keep it, so a future goal reactivates with
  setup's *add a goal* mode instead of a fresh survey.
- Replace the handoff with a short closing note linking the completion records,
  or remove it if the user prefers.
- Clear only the approved resolved XDG long-horizon worktree payload under the fixed root lock.
- Keep everything durable: goals file and archive, findings, evidence trailers,
  startup helpers and readiness reports.
- Leave delegation untouched; mention that its own setup can remove or keep it.

Wind-down never deletes history, findings or repository helpers, and lands
through the same closure policy as any batch.

## Durable handoff and evidence

The handoff describes current state, not a transcript, and stays within the
overlay's size budget; standing policy belongs in the overlay or `AGENTS.md`.
Its template contains:

- A shared section: current milestone/task, the batch's actual result, the next
  concrete action, remaining milestone work and any pending user decision.
- `## Blockers`: task ID, reason, needed input or decision, date.
- Accepted scope, evidence identifiers, exceptions and remaining integration gaps.
- Decisions/hypotheses/refuted approaches with links to durable findings.
- Required host capabilities and missing-input recovery steps.
- Startup command and context links; read-only defaults are explicit.
- Pending user decisions, including milestone refinements and goal sign-off.
- This batch's `Override:` lines, task refinements and off-goal work.
- On a merge conflict in the shared section (two worktrees closing batches),
  regenerate it from `lh.py status` on the merged tree rather than hand-merging
  prose.
- No credentials or live agent IDs. Ephemeral agent mappings stay in ignored
  worktree state.

Durable evidence is a commit trailer, readable with
`git log --format=%(trailers)`:

```text
Accepted-Check: name=rust-fixtures outcome=PASS scope=<digest> inputs=ghidra:<digest> domain=scenarios-v1 ledger=<id or none> log=<recovery route>
```

`scope` is a digest over the paths and blob IDs matching the check's scope
pathspec (default: everything except non-code paths), including uncommitted and
untracked non-ignored files. Evidence is fresh when the current scope digest and
every declared external input digest match. This keeps a checkpoint's own
handoff and goals edits from invalidating the checks it just ran, and it needs no
historical tree objects. An input whose digest command fails or is not declared
makes the evidence unverifiable, not fresh.

Acceptance survives a lost live ledger as historical evidence with its original
provenance. It is not forged into a new ledger PASS. Delegation remains the
authority for current checked claims: stable registered-validator results at the
required tree. Command observations and prose assertions are labeled
accordingly. With no delegation, `ledger=none` and the observed command, outcome
and scope are preserved directly; never imitate a checked ledger id.

Persistent external inputs belong to the repository's storage design, not the
plugin. Document how to acquire or regenerate missing bytes; a digest cannot
restore them. Never overwrite active hashed context during bootstrap, copy a
live ledger between worktrees, or archive scratch state as the continuation plan.
When required context is pinned by active work, defer refresh until it closes.

## Acceptance for the plugin

Implementation should verify packaging with the repository's generated-metadata
check, unit suite and disposable-profile lifecycle verifier. Record actual host
versions and observed results in `docs/verification.md`. Do not modify normal
user plugin settings or claim model-behavior checks from manifest or unit tests.

Unit tests drive `lh.py` over disposable Git repositories, main checkouts and
linked worktrees. They cover goals parsing and consistency, selection with
blockers and capability tags, handoff staleness, evidence freshness (scope,
non-code edits, changed and undeclared inputs), the close gate including goal
records and sign-off, accepted exceptions, shelved/dropped goals and the
parked section, no-active-goal and dormant states, `status --brief` and its
Needs-you list, closure verification, lint error versus warning levels and
`--fix` diffs, pointer reachability and handoff hygiene, and
delegation present or absent via a stub `check.py`.

Behavioral pilots run on both supported hosts, with written outputs and
actions inspected. They confirm the skills call `lh.py` and act on its output;
they must not depend on copyrighted game files. Required cases:

| Scenario | Expected behavior |
| --- | --- |
| Setup with a vague aim, from a linked worktree | Interviews, proposes evidence-first milestones, shows the dry-run selection, waits for approval, reports the setup is active only on this branch until integrated |
| Setup adopting an existing roadmap, from the main checkout with unrelated dirty files | Interviews anyway, preserves order and contents, proposes only parse annotations, touches only its own files |
| Setup when another branch already has an overlay | Starts from that version instead of drafting a divergent copy |
| Fresh checkout with goals and handoff | Identifies the active milestone and next eligible task without loading the full history |
| Isolated later-stage work already accepted | Preserves bounded acceptance and selects current-milestone work |
| Missing native inputs but available fixtures | Reports distinct capability levels and chooses only eligible work |
| First task blocked; all tasks blocked | Records a blocker, selects the next within the milestone, or stops dependent work |
| Existing or stale handoff and dirty worktree | Reconciles with goals/tree and preserves unrelated changes |
| Failed, skipped, stale or externally invalidated acceptance | `gate` refuses milestone completion and the exact gap is recorded |
| Fresh evidence after a docs-only edit | Reuses it without repeating an expensive gate |
| Delegation absent; delegation active | Works solo; with delegation, uses its pending/evidence interfaces and maintains no duplicate ledger |
| Fresh worktree or provider handover | Reconstructs from tracked context and durable evidence, without reusing live agent identities |
| Push or sync failure after commit | Reports verified partial closure and a precise retry step without claiming full completion |
| Explicit pause or user scope override | Preserves unfinished work and follows current authorization |
| Setup closure question | Recommends validation + merge + push with its reason, and records a different user choice faithfully |
| Batch closes successfully under the default | Merges and pushes, then recommends a fresh session instead of continuing |
| Milestone completes; next one is coarse | Proposes its tasks and asks, or refines directly only when the overlay allows |
| Last milestone completes | Writes the completion record, waits for sign-off, then archives the goal |
| All goals complete | Offers wind-down; after approval removes the pointer, sets the overlay dormant and keeps durable records |
| New goal after wind-down | Reactivates through *add a goal* without re-surveying from scratch |
| Quick setup with an unfamiliar user answering "you decide" | Explains concepts plainly, uses defaults, shows a sample session, ends with the cheat sheet |
| Survey finds validators and bulk work, delegation absent | Suggests delegation setup and hands over the survey; installs nothing |
| Quota enabled; quota disabled or plugin absent | One quota call sizes the batch; otherwise no quota call and no error |
| Gate fails for missing evidence | Offers run, task-only, or a user-granted accepted exception; never closes on its own |
| Every task blocked | Offers concrete choices and waits instead of silently stopping |
| Off-goal quick fix and "park: …" mid-batch | Does the fix and notes it; parks the idea without reordering |
| User overrides selection | Complies, logs one `Override:` line, preserves the original work |
| Shelve a goal | Marks it with a reason and record; selection moves on |
| Lint warnings only | Work proceeds; warnings are reported with fixes |

V1 is acceptable when packaging checks and unit tests pass and observed pilots
demonstrate setup, selection, honest acceptance and useful continuation. Report
untested hosts or scenarios plainly. Claims of reduced token cost require later
measurement; they are not prerequisites for shipping.

## Deferred

- **Task claims and multi-host coordination.** Most users run one machine; v1
  relies on milestone order and the merge-conflict rule above. Same-machine
  claims keyed by the Git common directory, cross-host claims and per-host
  handoff sections wait for a pilot that needs them.
- **Generic token-cost measurement** and any automated scheduling.

## Adoption and next step

After written-spec review, create the implementation plan for packaging, `lh.py`
with its tests, skills/templates and pilots. game-decomp is the first consuming
repository candidate: run setup in adopt mode, keep its documents, bootstrap,
milestone ownership and host policies, add the readiness report to
`tools/resume.py`, replace its plugin-cache glob with a declared checker path,
and move standing policy out of the handoff. Those changes need a separately
authorized adoption change. This spec alone changes neither game-decomp nor the
delegation plugin.

## Consolidated planning clarifications (2026-10-11)

The following resolved contracts supersede earlier conflicting examples. They
are design requirements, not claims of executed checks.


These decisions complete the specification. Fold these clarifications into its
relevant sections during Task 1 so implementation has one consistent contract.

### 1. Layout, versions and compatibility

Use the spec's plugin layout, plus a small `long_horizon` package next to
`resume/scripts/lh.py`. The entry point only imports `long_horizon.cli.main`.
Modules are `model`, `overlay`, `goals`, `git`, `state`, `readiness`, `handoff`,
`scope`, `delegation`, `evidence`, `gate`, `closure`, `lint` and `cli`; combine
small modules if doing so keeps responsibilities clear. Everything ships inside
`plugins/long-horizon/`. Setup/checkpoint locate the entry point relative to
their installed skill directory (`../resume/scripts/lh.py`), quoting paths.
Consumers may declare `LONG_HORIZON_SCRIPT` or a script path; never search a
versioned cache or assume this checkout. Names are plugin-qualified in guidance
so `long-horizon:setup` cannot be confused with `delegation:setup`.

Append `plugins/long-horizon` to `catalog.json`, preserving existing order.
Initial version is `0.1.0`. Generate both manifests and marketplaces through the
existing generator; it needs no new host adapter. Change delegation's composition
guidance only, with its current version bumped from `0.6.2` to `0.6.3` if still
current at implementation time. Re-read that version before editing. Quota
content remains unchanged. Both hosts receive the same files.

### 2. Runtime state follows the repository's XDG rule

The spec's worktree-local `.long-horizon/closure.json` conflicts with contributor
guidance requiring plugin state under XDG. Use:

```text
${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/long-horizon/
  state.lock
  gc.json
  <sha256(canonical-git-common-dir)>/worktrees/<sha256(canonical-worktree-root)>/
    identity.json
    closure.json
    evidence/<content-id>.json
    snapshots/<content-id>.json
    trailers.txt
```

Those files belong to one worktree and contain no live agent mappings. No cache
is needed initially. `status --json` exposes the resolved state directory and
`closure verify` accepts `--state PATH` for importing a specifically chosen
closure record. Do not discover/import another worktree's state automatically.
Replace `.long-horizon/` instructions in the spec/templates with this contract;
do not add a repository ignore rule for a directory we do not create. Legacy
`.long-horizon/` state may be reported with a migration instruction, but never
silently moved or deleted. Wind-down clears only this plugin's resolved worktree
state after showing its path; durable files and delegation state survive.

**Daily worktree churn is normal; automatic cleanup runs weekly.** On the first
state mutation or setup/resume/checkpoint at least seven days (168 hours) after
the previous sweep, run best-effort local garbage collection. Resume
invokes `state gc --apply --if-due` explicitly; `status`, `lint`, `find`, `gate`
and `closure verify` remain read-only. A manual `state gc` previews removals;
`state gc --apply` runs them immediately. No daemon, hook or network call.

Each worktree's `identity.json` records version, canonical worktree/common-dir/
git-dir paths, directory file identities (device/inode and stable birth time
where available), containing-volume identity, creation time, last mutation and
first confirmed missing time. A volume mismatch is unknown, not deletion.
Compare those identities with local Git registration, without pruning Git's
worktree records. Treat a worktree as deleted only when its directory and its
Git registration are both absent. If the common directory is itself gone,
require its recorded worktree and git directory also to be absent. An unavailable
mount, permission error, still-registered missing worktree or identity mismatch
is unknown and retained with a diagnostic. A newly recreated worktree at the
same path must match the recorded directory file identities to reuse state;
new directories must not inherit old state. If those identities cannot be
established reliably, retain the old payload as unknown rather than reuse it;
quarantine the old payload under a unique retired-generation name for the same
retention window.

Delete confirmed-deleted worktree state seven days after its first confirmed
missing observation, including scratch snapshots, pending records and closure
bookkeeping. The grace period permits explicit recovery/import, and status/gc
lists any pending evidence or unfinished closure scheduled for removal. Deleting
the worktree abandons its disposable bookkeeping; committed evidence, goals,
archives and user files are never touched. Do not infer closure success from
cleanup. Still-existing/registered worktrees keep pending evidence, its referenced
snapshots and unfinished closure regardless of age. Within them, delete
unreferenced snapshots and setup drafts after 30 days without use; remove
committed pending copies and their unreferenced snapshots immediately once
durable evidence is verified. Record last use of an attempt on state mutations.
Expired entries are removed on the next weekly sweep, so expiration does not
promise immediate deletion. The seven-day deleted-worktree recovery window
starts at its first confirmed missing observation, independently of sweep cadence.
Successful wind-down clears the current worktree payload immediately. Remove
empty repository directories afterward. When the plugin is never used again,
automatic cleanup cannot run; the manual command can sweep all its XDG state.

**One permanent lock, no lock per abandoned worktree.** All short state
transactions and garbage collection acquire the same root `state.lock`. Never
hold it during validators, input probes, startup or integration operations.
Never unlink or replace this lock file: doing so could let two processes lock
different inodes. Holding it while collecting prevents a writer from recreating
or changing a payload being removed. The root's tiny lock and GC timestamp are
the only permanent housekeeping files; per-worktree locks cannot accumulate.
Collection rechecks eligibility under the lock, skips symlinks/unknown files,
confines removal to recognized plugin-owned payloads and tolerates partial
deletion. A second run is a no-op. Cleanup errors are warnings and must not
block authorized work or silently remove protected state.

Readers never create state. Writers use an exclusive lock, atomic replacement
in the same directory and restrictive file modes where supported. Use the same
stdlib locking pattern as delegation's `file_lock.py`: `fcntl.flock` on POSIX
and `msvcrt.locking` on Windows, locking one fixed byte at offset zero with a
nonblocking attempt and a bounded retry loop. Always unlock and close the same
handle, including on exceptions; distinguish contention from other I/O errors.
Bundle the small lock helper inside long-horizon rather than importing an
installed delegation package. POSIX and Windows support state writes; report
an unsupported-lock diagnostic only when neither backend is available. Failed
writes leave the old record valid.
No consumer state is written beside installed scripts.

### 3. Overlay grammar and defaults

Keep a human-readable Markdown overlay; no YAML parser. An optional
`## Schema` contains `1`. Under the spec's named headings, each nonblank line is
`key: <JSON value>` with an optional leading `- `. Paths and commands are JSON
strings, maps/arrays are JSON values, booleans are JSON booleans. Normalize
heading case, CRLF and surrounding whitespace, preserve value case, reject
duplicate headings/keys and wrong value types. A title and blank lines are
allowed; comments are full lines starting `<!--` and ending `-->`. Unknown keys
or headings are errors with a suggested spelling. Missing optional sections use
defaults, so the quick setup can be this small:

```markdown
# Long-horizon
## Goals and ownership
path: "docs/goals.md"
## Integration
steps: ["validate", "commit", "merge", "push"]
target: "main"
remote: "origin"
authorization: "User approved standing batch closure on 2026-10-11."
```

That integration example is written only after approval. With no recorded
integration section, commit/merge/push/sync remain unauthorized. Omitted state
means `active`; omitted sign-off means `user`. Other defaults: handoff
`docs/handoff.md`, archive `docs/goals-archive`, handoff budget 80 lines, one task
or one blocker resolution per batch, quota off, readiness absent, no capability
requirements for `any`, agent task refinement/completion and milestone completion,
user milestone order/scope/criteria and goal sign-off. Non-code defaults are the
actual configured goals, handoff, findings and archive paths, not every Markdown
file. Evidence policy, overlays and activation instructions are not implicitly
excluded from acceptance-policy freshness.

Reference documentation defines every key and type. Ownership keys separate
`milestone-policy`, `task-refinement`, `task-completion`, `milestone-completion`
and `goal-signoff`. Integration defines `steps`, `target`, `remote`, optional
`sync`, `stop-conditions` and an authorization description. Evidence defines
`checks`, each with `scope`, `inputs`, `domain`, `allowed-skips` and optional
`validator`; input definitions contain an authorized cheap read-only command,
a timeout and recovery route. Delegation and quota script paths may be literal
or named environment variables; an explicitly configured missing value is a
finding, never a reason to guess a cache path. Startup's command and permitted
effects are descriptive authorization for the skill, not a command `status`
executes. Allow external context/recovery links, but managed goals/handoff/archive
paths must stay inside the current checkout, including through symlinks.

### 4. Goals grammar, manual fallback and ownership

Parse only headings and task lines outside fenced code. Support the spec's
explicit `# Goal:` headings and a single implicit goal for legacy roadmaps.
Milestones are numbered level-2 headings; `## Parked` is never a milestone.
Retain original text/line locations for diagnostics and surgical edits. Marker
customization is an explicit mapping in `Goals format`; regex injection is not
supported. Terminal siblings are done, shelved or dropped; a later goal can
therefore be current after shelving an earlier one. Milestones only use
current/done/open. IDs are unique across the goals file; missing task IDs use
`<milestone-number>-<first-12-sha256-of-normalized-task-text>` with a warning and
collision detection. Capability tags are comma-separated trailing parentheses;
all listed tags and all mapped levels must be satisfied. Unknown tags are
ineligible with a fix, never treated as `any`.

Add parseable `Checks: ["validator:unit", "observation:review"]` after `Done when`
when prose contains requirements not already expressed as named check tokens.
All named tokens in `Done when` are also required; `Checks` cannot weaken them.
Free-text acceptance without a named check is displayed but cannot auto-pass a
gate. Setup asks for check annotations without rewording adopted criteria.
Completion citations are adjacent `Evidence: <task-id>=<evidence-id-or-commit>`
lines; multiple references are comma-separated. A commit citation must resolve to
an ancestor of HEAD or the proposed batch commit and have an inspectable change;
it is task evidence, not an automatic milestone PASS.

An unparseable roadmap produces a warning, `selection.mode=manual`, and no
automatic selection. It must not strand independent work. A gate needing that
roadmap fails with the exact annotation needed; a malformed overlay or parsed
inconsistent hierarchy is an error. Current markers are optional; when absent,
selection infers the first incomplete eligible hierarchy. Two current markers,
duplicate IDs, checked milestones with open tasks and out-of-order completion
are errors. An archived done goal may have no inline children only when its
record validates the completed milestone summary and evidence.

Selection overrides let agents do requested work immediately and log `Override:`.
They do not silently permit false acceptance or change ownership. Off-milestone
work can record evidence while the later milestone stays open. Authorized scope,
order or criteria changes have an adjacent `Policy-Approval:` entry identifying
who approved what; `gate --base` reports them and checks the overlay's ownership
setting. Text cannot authenticate a person: skills must obtain actual user
approval when reserved to the user. Lint/gate verify the record exists and is
consistent, not the user's identity. Sign-offs and exceptions have the same limit.

### 5. Readiness and preparation stay distinct from acceptance

Readiness JSON follows the spec's version-1 format; accept `exists`, `size`,
`sha256` and `probed` strengths. Add optional `checkout` and `generated_at` fields;
when checkout is supplied it must match this worktree. Missing/malformed reports
make required capabilities unknown, with recovery instructions. `ready: true`
satisfies only its named preparation level, never a validator. Map tags to named
levels, independent of machine nicknames. With no helper/report, untagged/`any`
tasks remain selectable; tags requiring readiness do not.

`lh.py` never launches startup or quota. Resume runs an authorized helper, then
calls status again. It makes at most one quota call when enabled and a declared
script is available. A missing plugin or failed quota read is informational and
uses the default batch; it never blocks. Default batching stays one task/blocker
resolution; low remaining usage shrinks work, higher usage alone does not expand
it beyond recorded policy. Readiness generation and human recovery remain
consuming-repository responsibilities.

### 6. Evidence lifecycle closes the pre-commit gap

A gate must inspect acceptance before committing, and an evidence ID cannot
contain the hash of the commit carrying it. Add `evidence prepare <check>` to
capture a content-addressed before-snapshot; it does not run the check. The skill
runs the authorized validator/command, then invokes `evidence record <check>
--snapshot <id>` with its outcome and provenance. Record recomputes the scope,
policy and external inputs, refuses PASS if they changed, and emits a canonical
trailer plus a pending immutable evidence document. Record does not commit,
stage, amend or create a second validator ledger. Snapshot/record are
idempotent for identical content; an existing ID with conflicting content is an
error. Pending records carry no live agent IDs.

Each canonical record includes check name, outcome, scope digest, acceptance
policy digest, all input digests, domain, claim class, observed command or
validator name, delegation result ID/tree when applicable, log recovery route
and result/log digest. Its ID is SHA-256 of canonical sorted-key JSON, excluding
the carrying commit, presentation timestamp and derived detail-file location.
The record does not hash its own ID or a path containing that ID. Log routes
must be independent of the evidence ID; copied logs may be named by their own
log-content digest. Trailers retain the spec's
fields and add `id`, `policy`, `claim` and `detail`:

```text
Accepted-Check: id=<sha256> name=unit outcome=PASS scope=<sha256> policy=<sha256> inputs=none domain=unit-v1 ledger=none claim=observed detail=docs/evidence/<id>.json log=docs/evidence/<id>.log
```

Use `shlex` quoting for trailer values, including paths with spaces. Repeated
fields or malformed values fail parsing. Detail records are durable tracked
JSON (default `docs/evidence/<id>.json`, configurable), with compact logs or a
specific persistent retrieval/regeneration route. The record command outputs
these files for review and writes only its XDG pending copy; the checkpoint
skill writes the proposed durable files. Exclude this configured evidence sink
from default code scope to avoid self-invalidation, but include acceptance
policy in the separate policy digest. No scratch log path alone qualifies.

`gate` and `evidence find` read reachable commit trailers plus explicit pending
records for this batch. Commit message assembly uses `--trailers-file` (output
from record) and `git commit --file <message>`; no amend or automatic empty
commit. After committing, checkpoint resolves each pending ID in that exact
commit before removing the pending copy. An interrupted cleanup is harmless:
deduplicate by ID. A fresh clone needs only committed trailers/detail records.
If a task/goal changes its status without code edits, its normal documentation
commit can carry trailers. Pending acceptance is reported as pending, never
already committed.

An allowed skip is only acceptable within its declared domain/condition; it
never becomes PASS. An explicit accepted exception is separately recorded:
`Accepted-Exception: id=<id> check=<name> target=<goal-or-milestone-id>
reason=<quoted-text> by=<user> policy=<digest>`. Require a reason, target and
matching criteria revision. It covers only that check/target, is listed in the
completion record, and cannot waive sign-off or authorize remote operations.
Non-delegation results are observations, not forged `checked` results. Human
judgment uses `observation:<name>` and an explicit dated reviewer record.

### 7. Scope and inputs are deterministic without changing Git

Enumerate tracked files plus untracked non-ignored files with NUL-delimited Git
commands. Include deletions, executable mode, symlink target and submodule commit;
refuse fresh evidence for a dirty/unavailable submodule unless its contents are
explicitly modeled as inputs. Hash the canonical sorted path/mode/blob-ID list
with SHA-256. Blob IDs use Git's object format and `hash-object --stdin` without
`-w`; neither the real index nor object database changes. A tracked deletion is
a missing entry in the current snapshot, so deletion changes the digest.
Unreadable files and unresolved index conflicts fail closed.

Use Git pathspec matching for includes/excludes, with repository-relative paths;
never shell globbing. Default scope is everything except declared non-code and
evidence-sink paths. Scope policy changes, required checks, domains, allowed
skips, input definitions and the referenced validator policy change a separate
canonical policy digest even if code scope stays identical. Documentation edits
outside those policy definitions do not invalidate an expensive check.

The per-check policy digest includes its normalized required criteria text and
check list, but excludes checkboxes, current/done markers, sign-off dates, task
refinement text and archive-link presentation. Moving unchanged accepted
criteria into the archive preserves that digest. Changing criteria, domain or
input definitions does not. Checkpoint status edits therefore do not make their
own evidence stale. Closing a goal preserves the historical evidence accepted
at each milestone; only the goal's own required checks must be fresh again,
unless its criteria explicitly require revalidating earlier milestones.

External input commands return one lowercase SHA-256 token; reject failures,
timeouts, extra output and undeclared inputs. They are executed only with
`--probe-inputs` on prepare/record/find/gate under existing authorization.
Default status/lint perform no probes and show external freshness as unknown.
Before/after probes are required for externally dependent PASS. Empty inputs
are `none`; required inputs cannot be omitted. Snapshot output cached in XDG is
not proof of current external state. Every unknown/stale/missing distinction
appears in text and JSON with a recovery command.

### 8. Delegation adapter uses the actual 0.6.2 interface

The current checker supplies `tree`, `lint`, `pending --json`, and `query
--delegation <id> --tree current --json`. `tree` and `lint` are text output;
do not assume nonexistent JSON flags or a global query. Call them through an
argv list using `sys.executable <configured-check.py> --root <root> ...`.
Import no code from its installation and copy no ledger implementation.
`evidence record --delegation <id> --result <result-id>` queries that delegation
and requires the named registered validator, stable true, ok true, exit 0,
no timeout and the checker-provided current tree. The prepare snapshot carries
the checker tree too. Preserve the result/log hash and host/domain limits.
An arbitrary `check.py exec` observation has no registered validator name and
cannot satisfy `validator:<name>`.

Immediately turn the stable current result into scoped durable evidence before
checkpoint changes the goals/handoff. Later docs-only edits can reuse that
durable scoped acceptance, clearly labeled historical provenance; they are not
a new current-tree delegation PASS. Current claims explicitly requesting a
checked delegation result still use the checker's exact-tree query. A missing
ledger does not erase verifiable committed scoped acceptance, and it cannot
recreate a current checked result. Wrong/malformed/unavailable checker output
is a finding. Pending workers block checkpoint closure until delegation hands
them back; the plugin never closes or resets them itself.

### 9. Closure is a resumable record, not an automation engine

`closure record --batch <id> --step <name> ...` is an added local bookkeeping
command. It records policy fingerprint, branch/remote, exact batch commit,
intended ordered steps and separately observed outcomes, with version 1.
`closure verify` never commits, merges, fetches, pushes or syncs. Skills perform
only authorized operations, update records after observing their outcomes and
use the verifier before a retry. A batch ID derives from its evidence IDs and
changed-path/content-digest manifest; retries reuse it. A changed policy/target or different
batch needs an explicit new record, not overwriting successful prior steps.

Committed means the exact batch commit exists and is reachable from the local
batch history; record its changed paths and check they include the intended
owned changes. Merged means it is an ancestor of the configured local target
branch, whether by fast-forward or merge commit. Squash integration requires a
new explicit integrated-commit mapping and review of the mapped content; never
infer equivalence from a commit message. Pushed means the integrated commit is
contained in the configured remote-tracking target ref, qualified **as of the
local remote-ref observation**. Report the last observed ref OID and observation
time; Git alone cannot establish the server's present state or last fetch time.
Missing/stale refs are unknown, not successful remote closure. A successful push
with its recorded result is distinct from this local ancestry verification.
Host sync is an observed claim and stays unverified by Git.

The skill preserves unrelated dirty files, stages only owned paths and does
not switch branches/worktrees, rewrite history or force a merge/push. If the
target checkout is dirty/unavailable, merging is a remaining operation with a
precise remedy. Retry from the first unfinished step; already merged commits
and identical records are no-ops. Post-commit push/sync results live in XDG and
chat, avoiding a recursive follow-up commit to claim the previous push. Another
host can reconstruct committed/merged/ref facts; unfinished sync or unsaved
local closure cannot be invented. Setup's closure choice supplies standing
authorization only for the named operations and stop conditions.

### 10. Goal lifecycle and mechanical repair

Archive names use UTC date and a normalized goal slug; existing records for the
same goal are updated rather than duplicated. Distinct same-slug goals add their
stable goal-ID suffix. Add `ID:` to explicit goal metadata during approved setup;
legacy implicit goals derive an ID from heading content with a warning. Records
have a version-1 JSON metadata fence plus readable outcome, per-milestone
criteria/evidence/exceptions, limitations, refuted approaches and follow-ups.
A record in progress does not prove completion. Gate checks all expected
milestones and the goal's own criteria against it before archival compression.
Default sign-off keeps the goal current and selects no new goal work when all
milestones are done; brief lists **Needs you: sign off**. After actual approval,
add `Signed-off: <who>, <UTC-date>`, mark done and retain the ID/sign-off/archive
link. The archive metadata preserves children removed from the roadmap.

Shelving/dropping requires actual user instruction, a reason and a record of
where work stopped; it claims no completion. Unshelving reopens preserved work,
not a fresh survey. Wind-down/add-goal/update are repeatable surgical changes:
one pointer, one import, one overlay, no duplicate archive/parked entries.
Replace or remove the handoff only as approved. Never remove unrelated sections
from `AGENTS.md`/`CLAUDE.md` or delegation. Setup discovers overlays on default
and other local branches/worktrees without fetching; prefer current checkout,
then default branch, then a unique other version. Multiple different candidates
become one explicit choice in the draft; never silently choose an arbitrary log
entry. Already-approved identical setup is a no-op, not another interview loop.

`lint --fix` prints a diff; `--fix --apply` is the explicit approval to apply
only unambiguous mechanical changes. Missing markers/IDs/headings can be added;
conflicting current markers, ownership changes and destructive edits require
manual repair. Never repair accepted task text/criteria or infer missing PASS.
Check the input file digest before application, preserve line endings and
unrelated prose, and make a second run produce an empty diff.

## Public CLI and result contract

Every subcommand supports `--root`, `--overlay` and `--json` in the documented
position after the subcommand. Paths resolve from the Git worktree root, except
an explicit draft overlay's managed relative paths resolve from that draft's
base directory with `--draft-root`. This lets setup put its entire draft in an
XDG draft directory and dry-run it without writing the repository. Git identity
always comes from the actual checkout. `--goals` and `--handoff` can override
only those input paths for a dry-run. Never treat a draft as active policy.

Commands:

```text
lh.py lint [--fix [--apply]]
lh.py status [--brief]
lh.py evidence prepare <check> [--probe-inputs]
lh.py evidence record <check> --snapshot <id> --outcome <outcome> ...
lh.py evidence find [<check>] [--probe-inputs]
lh.py gate [--base REV] [--probe-inputs] [--pending <id> ...]
lh.py closure record --batch <id> --step <step> ...
lh.py closure verify [--state PATH]
lh.py state gc [--apply] [--if-due]
```

Additional argument contracts:

- `state gc` works outside a Git checkout and scans only this plugin's XDG
  state root. It reports deleted-worktree, old-unreferenced and protected/unknown
  entries with reasons, retention deadlines and pending/unfinished summaries.
  `--apply` authorizes only the eligibility rules above; `--if-due` limits an
  applied sweep to once per seven days. There is no force flag that discards live
  pending state. A missing state root is an empty successful result, not created
  by preview. Wind-down may explicitly clear its own approved payload using the
  same locked removal helper. GC's own writes do not refresh payload ages.
- `evidence prepare` accepts `--attempt <identifier>`, defaulting to a generated
  identifier it prints for reuse. Preparing with that same identifier and
  unchanged scope/inputs reuses the snapshot; changed contents under that
  identifier are an error. A genuinely new validator execution gets a new
  attempt. Record includes that attempt in its canonical content, distinguishing
  a new run from a repeated invocation to save an existing result.
- `evidence record` accepts `--outcome PASS|FAIL|SKIP|UNSTABLE`, `--domain`,
  `--log <recovery-route>`, `--detail <tracked-path>`, `--probe-inputs` and
  `--trailers-file <output-path>`. Domain/detail default to overlay settings;
  log is required. Solo provenance requires `--command <observed-command>` and
  `--exit <integer>`; PASS requires exit 0. Delegated provenance instead requires
  `--delegation <id> --result <id>` and derives command/exit from checker output.
  Human observations instead use `--reviewer <name> --review-note <tracked-path>`;
  the skill confirms the actual review. These three provenance modes are
  mutually exclusive. External checks require `--probe-inputs` on both prepare
  and record. Explicit trailer-file output is atomic and idempotent; no write
  to Git's commit message or index occurs.
- Accepted exceptions use `evidence record <check> --exception --target <id>
  --reason <text> --by <user>`, after actual user acceptance. This mode emits
  an exception trailer/detail instead of PASS and needs no validator snapshot;
  it fingerprints the target's current criteria and carries no check result.
- `closure record` accepts `--step validate|commit|merge|push|sync`,
  `--outcome success|failed|pending`, `--commit <oid>`, optional
  `--integrated-commit <oid>`, `--observation <text>` and
  `--manifest <reviewed-paths-and-digests.json>`. The first record requires the
  manifest and derives target/remote/steps from approved policy. Success for a
  Git step requires its relevant OID; sync requires an observation. Verify
  derives Git facts again rather than trusting success strings. Validation
  references accepted evidence IDs in the manifest rather than running checks.
- `gate --pending <id>` repeats for each explicitly included pending check or
  exception; it never silently accepts every worktree scratch record.

The archive metadata fence has `version`, `goal_id`, `status`, `outcome`,
`milestones` (ordered IDs, criteria, evidence IDs and exceptions), `goal_checks`,
`signoff`, `limitations`, `refuted` and `followups`. Shelved/dropped records also
retain their original roadmap section and `reason`, so resumption can restore
it without synthesizing tasks. The batch manifest has `version`, `base`,
`paths` (relative path, content digest or deletion), and `evidence_ids`.

JSON uses `version: 1`, `command`, `ok`, `findings` with severity/code/path/line/
message/remedy, and command-specific structured data. Exit 0 means successful
inspection/no blocking findings, even with warnings, no eligible task, no active
goal or no evidence. Exit 1 means blocking consistency/gate/freshness findings
or unverified required closure. Exit 2 means invalid usage/environment. Missing
evidence is data in `find`, but a required missing item fails `gate`. All
exceptions become concise diagnostics; no traceback for normal user errors.
`--json` prints only JSON to stdout; stderr is for invocation/environment errors.
Text is compact, with commands/sentences that fix every finding.

`gate --base` defaults to HEAD, comparing the working proposed goals to the
committed version. CI/integration passes the explicit pre-batch base so already
committed changes are checked. On an unborn branch use an empty base and treat
adopted completion as needing explicit existing evidence/limitations; setup
must not manufacture retrospective PASS. Gate checks newly completed tasks,
milestones and goals, completion records and owned policy changes, not every
legacy checkbox on every invocation. Criteria edits invalidate evidence via
policy digest. Existing false structural claims are still lint errors.


## Readiness cache correction (0.3.0)

Startup readiness defaults to `cache:readiness.json`, resolved under the actual
worktree’s repository/worktree-keyed XDG cache `readiness/` directory, alongside
`drafts/`. Read-only `lh.py paths --root PATH --json` exposes state/cache/readiness
paths plus cache identity metadata. The producer persists that identity and its
report under the shared lifecycle lock, enabling readiness-only cache collection.
Relative JSON names are confined, with traversal/absolute/Windows drive/symlink
escapes rejected. Legacy readiness paths keep working but lint warns with the
`cache:` remedy. Lookup freshness and checkout matching remain unchanged.
Weekly GC recognises readiness JSON and preserves unknown files; confirmed deleted
and unregistered worktrees receive the existing seven-day recovery window.
Tests cover discovery without creation, worktree separation, escape rejection,
missing/stale/mismatched reports, legacy lint, GC and mocked Windows defaults.
No consuming repository is migrated by this plugin correction.
