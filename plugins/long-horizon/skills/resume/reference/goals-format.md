# Goals grammar and lifecycle

Outside fenced code, goals are `# Goal: Title` headings. Milestones without a
goal heading are not read; status reports them as a `layout-outdated` error. Ordered milestones are `## 1. Title` (a dot is
optional); `## Parked` is excluded. Goals may be open, current, done, shelved or
dropped; milestones only open/current/done. Literal suffixes come from overlay
markers. A missing current marker infers first incomplete work. Multiple current
siblings, duplicate IDs, done parents with open children and out-of-order
completion are errors. Earlier terminal goals permit later work.

A goal has `ID: stable-id`, `Done when: prose with named tokens`, optional
`Checks: ["validator:unit", "observation:review"]`, Context, Signed-off, Archive,
Reason and Policy-Approval lines. Metadata belongs to the preceding heading/task.
All named checks in criteria plus Checks are required. Free text alone displays
but cannot auto-pass. Do not reword adopted criteria to accommodate the parser.
`Done when:` needs its colon and goes directly under its heading, before any
tasks: metadata after a task belongs to that task. A criterion is a paragraph: the
`Done when` line plus the non-blank lines directly after it, up to a blank line,
heading, task or metadata key line, so it may wrap. Lint warns about a `Done when`
without a colon (it is otherwise ignored) and about a milestone with tasks but no
criteria, naming the task a trailing criterion attached to. `lint --fix` adds the
colon and moves that trailing paragraph intact, wrapping included, above the tasks. The gate treats whitespace,
`.,;:` and that move as formatting, not a criteria change; changed words still need
Policy-Approval. Evidence recorded under the old layout goes stale because it names
the criterion it proves; carry it over with `evidence rerecord`.

Tasks: `- [ ] [1.1] Task text. (fixtures, native)`; `- [x]` means done. Trailing
capability tags are comma-separated and all required. Without an explicit ID the
ID is milestone number plus the first 12 SHA-256 characters of normalized text;
warn that rewording changes it. IDs are globally unique. Adjacent
`Evidence: 1.1=<id-or-commit>,<second-reference>` cites completion. Commit citations
must resolve to inspectable ancestor changes. They do not automatically pass a
milestone. Unknown tags need configuration, never silently mean any.

If the overlay has a `## Lanes` section with `config`, [lanes](lanes.md) adds
task metadata and its own selection rule; otherwise it does not apply.

Status selects first eligible unblocked task in the first incomplete milestone
of the first active goal. States include selected, manual, all-blocked,
milestone-acceptance, awaiting-signoff, dormant and no-active-goal. Preparation
is independent of check acceptance. If parsing fails use manual requested work;
malformed parsed structure is a blocking consistency error.

A goal needs its own `Done when` with named checks to complete; status and lint
warn `goal-criteria-missing` while an active goal lacks them, and
`milestone-proof-missing` for each done milestone of an active goal with no named
checks or no recorded PASS under its current criteria. Both are warnings, raised
early so they can be settled before sign-off.

A last completed milestone enters awaiting-signoff. Status then adds a `signoff`
object: `gaps` (archive file, Archive line, unfilled slots, goal checks without a
fresh PASS) and `approvals` the user must give (`goal-criteria` with proposed
lines, `legacy-acceptance` with each milestone's reason, `signoff`), so they can
be asked together. After actual configured-owner
approval add `Signed-off: user, YYYY-MM-DD`, complete the goal and keep its stable
ID/sign-off/archive pointer. Archive metadata is a JSON fence with version=1,
goal_id, status, outcome, milestones (ordered objects with id, criteria, checks,
evidence, exceptions), goal_checks, signoff, limitations, refuted and followups;
goal_criteria and legacy_acceptance are optional. Every
removed milestone must remain verifiable. A record in progress proves no closure.

`archive prepare [--goal ID] [--write]` builds that JSON from the goals file and
the committed plus this worktree's pending evidence: each milestone's proving
record IDs, its other citations, and `<fill: ...>` slots for outcome, sign-off,
limitations, refuted ideas, follow-ups and any legacy acceptance. Rerunning it
keeps filled slots and the prose around the fence. `archive check` validates a
goal's archive with the gate's rules. Neither edits the goals file.

Milestone evidence proves a check through a record ID, bare or as `task=<id>`,
whose PASS (or exception) names that milestone's current criteria. Prose, commit
and tree-hash citations are kept but prove nothing. A milestone that closed before
Checks existed, or whose proof is only prose, validates through `legacy_acceptance`:
`{"milestones": [ids], "approved_by": who, "date": "YYYY-MM-DD", "reason": why}`,
recorded only after the user actually approves it, usually with sign-off. It names
exactly the milestones without recorded proof; it never covers a milestone or goal
completed in the gated batch, whose checks still need fresh PASS.
A shelved/dropped record also has reason and original_roadmap; shelving claims no
completion. Unshelving restores work/evidence with its existing ID.

`Policy-Approval: who approved which scope/order/criteria change, date` is adjacent
to changed hierarchy. Gate checks this record and ownership, but text does not
authenticate a person; skills obtain actual approval. Task refinement stays
within configured ownership. Selection overrides are logged in handoff and never
waive acceptance. Sign-off rejection reopens rejected work and preserves history.

Golden continuation states:

| Roadmap / inputs | Selection |
| --- | --- |
| First task blocked, second any task open | Second task in same milestone |
| All tasks blocked | all-blocked with recovery/Needs you |
| All milestone tasks done, milestone open | milestone-acceptance |
| All milestones done, goal current | awaiting-signoff |
| Earlier goal shelved, later goal current | Later first eligible task |
| Prose-only roadmap | manual; requested independent work allowed |
| Dormant overlay | dormant; no automatic task |
| All goals terminal | no-active-goal |

`lint --fix` previews unambiguous task ID additions and the `Done when` repairs
above. `lint --fix --apply` authorizes only that mechanical diff, checks original bytes and preserves line endings.
Conflicting markers, missing accepted proof and policy changes need manual repair.

Archive filenames use UTC date plus normalized goal slug. Reuse an existing record
for the same goal; distinct same-slug goals add their stable ID suffix. Include
checks arrays when Checks annotations add obligations beyond tokens in criteria.

Handoff hygiene recognizes sk-/sk-proj-, ghp_, github_pat_ token shapes, private-key
headers, long password/api-key/access-token assignments and explicit live agent
ID assignments. Findings redact values; durable d1#1-style result IDs are allowed.
These narrow patterns are a lint aid, not a general secret scanner.
