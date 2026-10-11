# Long-horizon: reliable progress across sessions (2026-10-11)

Status: proposed specification, based on Rick's approval to generalize the
game-decomp workflow. Written-spec review and implementation planning remain next.
This document does not add an installed plugin or change any consuming repository.

## Purpose and success

Package the practices that let an agent advance a large project over many
sessions, worktrees, hosts and model changes without drifting into later work,
forgetting evidence or mistaking a successful batch for a completed goal.

The plugin is named `long-horizon`. It works with a solo agent and optionally
composes with `delegation`: long-horizon selects and preserves work across
sessions; delegation assigns workers and records execution evidence within a
session. Both hosts consume the same skills and templates.

Success means a fresh session can identify the current milestone, select the
next eligible task, determine whether its host has the necessary inputs, recover
relevant decisions and evidence, and finish a bounded batch with an accurate
handoff. It must never infer acceptance from missing, skipped or stale checks.

## Lessons from game-decomp

These are observations from `game-decomp` at revision
`ea0fd97a6d0f5e3f7abddf83867070a131d26e57`, not claims that this plugin has been
implemented or evaluated. Source paths below are relative to that repository.

| Observed practice or failure | General requirement | Source |
| --- | --- | --- |
| Isolated later-stage ports were accepted before golden traces existed; their real calling context still needs acceptance. | Preserve bounded acceptance, enforce milestone order, and require integration evidence before closing an integrating milestone. | `docs/goals.md`, Existing partial work |
| Goals contain ordered tasks and an explicit “Done when” condition. | Separate task completion, batch completion and milestone acceptance. | `docs/goals.md` |
| Startup prepares context and reports host capabilities without running tests or installing tools. | Resume is preparation, with named readiness levels and actionable missing inputs. | `tools/resume.py` |
| Fixture bytes persist outside Git; the live ledger belongs to a worktree and is disposable. | Durable evidence must survive independently of scratch state; referenced bytes need an explicit recovery route. | `docs/delegation/README.md` |
| A fixture skip cannot establish acceptance; cheap checks and scoped gates avoid repeated full-suite runs. | Validation scope and accepted exceptions are repository policy; checkpoint preserves precise evidence. | `.agents/delegation.md`, Oracle |
| Ghidra changes invalidate a check even when the source tree stays unchanged. | Acceptance includes external dependencies, not just a Git tree hash. | `.agents/delegation.md`, `ghidra-sync` |
| Descriptive static names, runtime observations and unproved causes have different statuses. | Findings retain their evidence class, domain and uncertainty. | `research/findings.jsonl`, `docs/handoff.md` |
| Host-specific merge, push and sync rules have standing authorization and exceptional stop conditions. | Follow explicit local integration policy and record each step's outcome separately. | `AGENTS.md`, Workflow |

These practices motivate the design; one project is insufficient evidence that
the plugin improves cost, speed or correctness in every repository.

## Boundaries and alternatives

A separate plugin with optional delegation integration is preferred. Adding
these rules to delegation would make multi-session progress depend on worker
routing. A larger autonomous scheduler would introduce budgets, orchestration
and state recovery before the simpler workflow has been tested.

| Owner | Responsibility |
| --- | --- |
| Long-horizon | Milestone selection, startup context, readiness interpretation, durable continuation and batch closure |
| Delegation | Tiers, briefs, agents, concurrency, locks, validators, live ledger and pending-worker checks |
| Repository | Goal content, acceptance authority, domain bootstrap, evidence stores, validation budget and integration authorization |
| Host or user | Session launch, tool permissions, model selection, subscription budget and exceptional approvals |

Long-horizon does not spawn agents, maintain a second validator ledger, supply
fixture storage, switch providers or authorize remote actions. No hooks,
background loop, automatic quota polling or database are required in v1.
It does not replace brainstorming or implementation plans: a roadmap orders
work; a plan explains how to perform an approved piece of work.

## Plugin contents

Proposed layout follows this repository's portable packaging convention:

```text
plugins/long-horizon/
  plugin.json
  skills/
    setup/SKILL.md
    setup/reference/overlay.md
    setup/reference/goals-template.md
    setup/reference/handoff-template.md
    resume/SKILL.md
    checkpoint/SKILL.md
    checkpoint/reference/evidence.md
```

Authored identity belongs in `plugin.json` and `catalog.json`; host manifests
and marketplaces are generated with `scripts/sync_marketplaces.py`. Initial
released version is `0.1.0`. No consumer build step or added runtime dependency
is needed for the skills themselves. Existing domain helpers remain in their
repositories. V1 ships instructions and templates; a generic checker is deferred
until a pilot identifies rules that can be enforced without duplicating delegation.

## Consuming repository contract

Activation is an explicit pointer in `AGENTS.md`:

```text
Long horizon: follow the long-horizon resume and checkpoint skills; this repo's overlay is .agents/long-horizon.md.
```

Setup proposes this pointer and a tracked overlay. Defaults are
`docs/goals.md` and `docs/handoff.md`, but existing paths and document formats
are adopted rather than replaced. The overlay specifies:

- **Goals and ownership:** goals path; who may change order, scope and acceptance
  criteria; who may mark tasks or milestones complete.
- **Continuation:** handoff path, durable findings/acceptance paths, and minimal
  additional context to load for the current task.
- **Startup:** optional repository bootstrap command, its permitted effects,
  generated context path, and named capability reports.
- **Evidence:** acceptance backend, validator policy reference, external input
  identity requirements, and allowed skips with their precise scope.
- **Hosts:** task capability requirements and the repository's supported routes.
- **Integration:** authorized commit/merge/push/sync steps, their order,
  exceptions, and ownership of shared documents.

Commands and paths resolve from the consuming checkout or an explicitly supplied
installed skill path; no author-specific clone, cache version or machine name
belongs in the base. Host restrictions and integration commands are local policy.
The overlay references delegation's validators and locks rather than restating
them. It is configuration to inspect, never automatic authorization to execute
an unapproved command.

No overlay means resume reports that setup is missing and works from explicit
session instructions and existing goals/handoff if unambiguous. It invents no
integration policy. A conflicting or malformed overlay is reported and dependent
actions stop; independent read-only context gathering may continue.

## Setup skill

Use only when asked to enable, configure or update long-horizon for a repository.
Survey existing goals, plans, handoff, findings, startup helpers and delegation
policy. Propose the smallest overlay and activation pointer. Present a concrete
diff for review when configuration approval is required; existing explicit
authorization governs whether another approval is needed.

Preserve existing roadmap order, checkboxes, evidence and handoff contents.
For a new project, propose milestone outcomes and completion criteria; do not
silently decide the project's scope. Establish who owns roadmap edits and
acceptance. Default new policy reserves scope/order/criteria changes for the
user, while allowing agents to record supported completion. Existing policy
takes precedence, including game-decomp's user ownership of goal edits.

Setup does not install tooling, capture inputs, run expensive acceptance gates,
create repository helper scripts or change unrelated plugin configuration.
Such actions need their own task authorization. Validate document links and
policy consistency, then record what was configured and what remains missing.

## Resume skill

1. Read the activation pointer, overlay, ordered goals and current handoff.
   Follow minimal context links for the active task, not the entire archive.
2. Inspect checkout identity and uncommitted changes; preserve unrelated work.
   Reconcile the handoff's revision and claims with the current tree and goals.
   Goals define scope; a newer handoff cannot silently reorder them.
3. Run only the authorized startup helper and read its report/generated context.
   Startup may prepare declared ignored state, but does not perform acceptance,
   installs, downloads, captures or cache regeneration by default. Readiness is
   labeled at the strength actually checked, such as existence/size versus hash.
4. Select the first incomplete milestone and its first incomplete eligible task.
   Record a concrete blocker before selecting the next task within that milestone.
   Never advance to a later milestone merely because its work is easier or this
   host lacks a capability. If all current tasks are blocked, report the inputs
   or decision needed and stop dependent work.
5. State the bounded session batch, relevant completion criteria and verification
   scope. Keep observed facts, hypotheses, bounded prior acceptance and open
   integration gaps distinct. Resume normal implementation/research workflows.

An authorized detour must unblock the current task; record its reason and return
condition. Changes to milestone scope or order follow the overlay's ownership
policy. An explicit user request can override normal selection; preserve the
remaining original work unless the user cancels it.

Named readiness levels are repository-defined. For example, context-ready,
fixtures-ready and native-ready can describe different capabilities; none means
tests passed. Missing native capability need not block a fixture-only task.
If a helper fails, preserve the diagnostic and continue only work whose inputs
and safety do not depend on the failed preparation.

## Checkpoint skill

Use when finishing a batch, handing over to another session/host, or responding
to an explicit pause. It also guides recording findings during work: discoveries
and rejected approaches belong in the durable sink when established, not only
in a final transcript. If delegation already governs that sink, follow its
single-writer and open-check rules instead of creating another findings stream.

1. Review final changes and evidence. Close or explicitly hand back workers using
   delegation when active; inspect pending state through its checker. Never reset
   a ledger, close someone else's work blindly or treat a dead worker as resumed.
2. Run the proportional checks required for the changed component and integrated
   batch. Consult existing evidence first; avoid a duplicate expensive gate on
   the same tree with unchanged relevant inputs. Failed, skipped, unstable or
   out-of-domain results remain limitations, not PASS.
3. Persist acceptance in an allowed durable location: component note, findings
   record or commit message. Include check identity, outcome, source tree or
   revision, tested domain, relevant external input identities and evidence
   location/recovery route. A disposable log path alone is insufficient.
4. Update the handoff and permitted task statuses. Mark a milestone complete
   only when its own acceptance condition passes and the agent has authority
   to mark it. Passing isolated functions cannot close a whole-call integration
   milestone. A finished batch may leave every milestone checkbox unchanged.
5. Perform the locally authorized integration sequence, preserving unrelated
   changes and enforcing declared exceptional stops. Record partial outcomes:
   committed, merged, pushed and host-synced are separate claims. On failure,
   preserve completed steps and state the exact remaining operation; do not
   force a merge, rewrite history or restart successful steps unnecessarily.
6. Return a concise result with the durable handoff/spec link, commit when made,
   validation scope, limitations and next concrete task.

Tracked handoffs record the batch's verified state and intended closure steps
before committing. Commit messages can contain the final accepted tree evidence
without a self-referential hash edit. Later push/sync outcomes are reported in
the final response; a failure is also saved in ignored local closure state or a
subsequent authorized handoff correction. A pre-commit handoff must never claim
that a future push or sync already succeeded.

An explicit pause overrides normal persistence. Preserve a useful checkpoint
and report unfinished checks or integration; do not start more implementation
or invoke unauthorized closure actions merely to satisfy the template.

## Durable handoff and evidence

The handoff describes current state, not a transcript. Its template contains:

- Current milestone/task and the batch's actual result.
- Accepted scope, evidence identifiers, exceptions and remaining integration gaps.
- Decisions/hypotheses/refuted approaches with links to durable findings.
- Concrete blockers, required host capabilities and missing-input recovery steps.
- Relevant startup command and context links; read-only defaults are explicit.
- The next concrete action, remaining milestone work and any pending user decision.
- Integration state and incomplete closure steps, without credentials or live
  agent IDs. Ephemeral agent mappings stay in ignored worktree state.

Acceptance survives a lost live ledger as historical evidence with its original
provenance. It is not forged into a new ledger PASS or presumed valid on changed
sources/inputs. Delegation remains the authority for current checked claims:
stable registered-validator results at the required tree. Command observations
and prose assertions are labeled accordingly. With no delegation, preserve the
observed command, outcome and scope directly; never imitate a checked ledger id.

Persistent external inputs belong to the repository's storage design, not the
plugin. Document how to acquire or regenerate missing bytes; a hash cannot
restore them. Never overwrite active hashed context during bootstrap, copy a
live ledger between worktrees, or archive scratch state as the continuation plan.
When required context is pinned by active work, defer refresh until it closes.

## Acceptance for the plugin

Implementation should verify packaging with the repository's generated-metadata
check, unit suite and disposable-profile lifecycle verifier. Record actual host
versions and observed results in `docs/verification.md`. Do not modify normal
user plugin settings or claim model-behavior checks from manifest tests.

Run behavioral pilot scenarios on both supported hosts and inspect their written
outputs and actions. A scenario may use a small temporary repository; it must
not depend on copyrighted game files. Required cases are:

| Scenario | Expected behavior |
| --- | --- |
| Fresh checkout with goals and handoff | Identifies the active milestone and next eligible task without loading the full history |
| Isolated later-stage work already accepted | Preserves bounded acceptance and selects current-milestone work |
| Missing native inputs but available fixtures | Reports distinct capability levels and chooses only eligible work |
| First task blocked; all tasks blocked | Records a blocker, selects the next within the milestone, or stops dependent work |
| Existing or stale handoff and dirty worktree | Reconciles with goals/tree and preserves unrelated changes |
| Failed, skipped, stale or externally invalidated acceptance | Refuses milestone completion and records the exact gap |
| Same integrated tree already has sufficient evidence | Reuses applicable evidence without repeating an expensive gate |
| Delegation absent; delegation active | Works solo; with delegation, uses its pending/evidence interfaces and maintains no duplicate ledger |
| Fresh worktree or provider handover | Reconstructs from tracked context and durable evidence, without reusing live agent identities |
| Push or sync failure after commit | Reports partial closure and a precise retry step without claiming full completion |
| Explicit pause or user scope override | Preserves unfinished work and follows current authorization |

V1 is acceptable when the packaging checks pass and observed pilots demonstrate
selection, honest acceptance and useful continuation. Report untested hosts or
scenarios plainly. Generic automation and claims of reduced token cost require
later evidence; they are not prerequisites for shipping the initial skills.

## Adoption and next step

After written-spec review, create the implementation plan for packaging,
skills/templates and pilots. game-decomp is the first consuming repository candidate:
adopt its existing documents and bootstrap, retain its milestone ownership and
host policies, and replace duplicated generic instructions only in a separately
authorized adoption change. This spec alone changes neither game-decomp nor the
delegation plugin.
