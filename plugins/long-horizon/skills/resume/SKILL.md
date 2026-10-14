---
name: resume
description: Continue a long-horizon project, inspect where we are, reconcile handoff, select one eligible task and preserve honest readiness and acceptance boundaries.
---

# Long-horizon resume

Resolve `scripts/lh.py` relative to this skill directory or an explicit
`LONG_HORIZON_SCRIPT`/script path. Quote paths. Read the
[overlay](reference/overlay.md), [goals](reference/goals-format.md),
[readiness](reference/readiness.md) and [state retention](reference/state.md) contracts.

“Where are we?” means read-only status and a short answer. Do not run startup,
quota, validators or GC for that request. No overlay: explain setup is missing,
then perform explicitly requested work; invent no closure policy.

For “continue”, first inspect:

```sh
python3 "$LONG_HORIZON_SCRIPT" status --root "$PROJECT" --json
python3 "$LONG_HORIZON_SCRIPT" state gc --apply --if-due --json
```

If status warns `version-mismatch`, ask the user once: "long-horizon plugin is
X, this repo is tagged Y. Run a migration?" On yes, follow `long-horizon:migrate`
before selecting work; on no, continue without asking again this session.
`version-newer` means the installed plugin is older than the repo: suggest
updating it. An invalid overlay whose message names an outdated form is the same
offer.

Status also lists this worktree's uncommitted pending evidence (`pending_evidence`,
and `pending: true` on acceptance it would satisfy) and the handoff's `lines` and
`budget`. Pending records still reach the gate only through explicit `--pending`.
An over-budget handoff is trimmed before this session adds to it.

Reconcile new/missing/stale/dirty handoff against relevant commits and dirty
changes. Do not discard work or read full history unnecessarily. Load only the
current goal/milestone/task and their context/recovery links. Malformed policy or
inconsistent hierarchy blocks dependent selection/acceptance; a manual roadmap
still allows independent requested work. Warning-only findings can proceed.

Run a declared startup helper only under actual authorization for its command and
permitted effects. It prepares inputs/context, never supplies validator PASS.
Never install missing tools or execute arbitrary overlay commands silently. Then
call status again to read its readiness JSON. All capability tags and mapped
levels must be ready. Untagged/any tasks need none. Unknown tags need a mapping.

Select the first eligible unblocked task within the first incomplete milestone
of the first active goal. Do not skip a milestone because it is blocked. Offer
specific choices when all tasks are blocked: recover the first input, research
its blocker, obtain the listed user decision, or label requested off-milestone
work. If all milestones are done, Needs you asks for goal sign-off (with any
approvals it needs, listed under status `signoff`) and selects no new goal work;
`long-horizon:checkpoint` closes the goal. `goal-criteria-missing` and
`milestone-proof-missing` warnings mean closing will stall: bring them up with the
user at the next milestone boundary. Dormant/no-active-goal reports that state without error.

If quota is enabled and a declared script resolves, make at most one quota call
at resume, using that script's documented CLI. Failure/absence is informational;
use the default batch. Low capacity can shrink work; high capacity does not expand
one-task/blocker batching without recorded policy. With quota disabled make zero
calls. `lh.py` itself never launches startup, quota or validators.

Give three lines (goal, milestone/progress, next task/Needs you), then do the
bounded work. A user override is immediate requested work plus one handoff
`Override:` line; it does not create acceptance or transfer reserved ownership.
Off-goal work is labeled; park ideas without changing the roadmap. Explicit pause
records next steps and preserves work. Use `long-horizon:checkpoint` after the
bounded batch. Recommending a fresh session is useful after honest closure, not
a claim of token savings or automatic scheduling.

If the overlay has a `## Lanes` section with `config`, read
[lanes](reference/lanes.md) before selecting work; otherwise ignore lanes entirely.

Preserve the host’s existing shared XDG state/cache roots across every CLI call.
Never redirect them into a checkout, Git directory or installed plugin, including
for temporary isolation. For tests use an explicitly supplied external disposable
XDG root; no checkout-local scratch state.
