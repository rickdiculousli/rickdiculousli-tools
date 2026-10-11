# Long-horizon: reliable progress across sessions (2026-10-11)

Status: proposed specification, based on Rick's approval to generalize the
game-decomp workflow. Revised after written-spec review to add deterministic
checks, an interview-led setup flow, default session closure, the goal
lifecycle and friction controls. Implementation planning is linked below.
This document does not add an installed plugin or change any consuming repository.

The [implementation plan](../plans/2026-10-11-long-horizon.md) resolves the
implementation contracts. The
[XDG state and locks addendum](2026-10-11-xdg-state-and-locks-addendum.md)
supersedes the worktree-local state paths below and specifies separately
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
| `closure verify` | Verifies the Git-checkable closure claims in `.long-horizon/closure.json`: committed, merged into the target branch, and pushed as of the last fetch (no fetch is performed). Host sync remains a recorded claim. |

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
   not import `AGENTS.md`), an ignore rule for `.long-horizon/`, and ignore
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
   its readiness report. Startup may prepare declared ignored state, but does
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
   `.long-horizon/closure.json`, then run `lh.py closure verify`. Committed,
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
- Delete ignored long-horizon state (`.long-horizon/`) in this worktree.
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
