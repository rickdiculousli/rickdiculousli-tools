# Interview and draft review

Quick questions, combined in one message; reuse existing answers:

1. What outcome should this project reach, or which existing roadmap should we adopt?
2. What would convince you it works? Name checks and any human review; who signs off?
3. What can this checkout prepare now, and what input needs a recovery route?
4. Keep defaults (one task/blocker per batch; agent task refinement/completion,
   user milestone scope/order/criteria and goal sign-off), or adjust them?
5. Recommend validate, commit, merge to default branch and push each batch;
   prefer that, commit only, merge without push, a PR or ask each time?

“You decide” permits drafting defaults. It does not fabricate checks or remote
permission. The final review presents the concrete files and operation policy.

Full mode adds readiness levels/all-of capability tags, validator scope/domain,
external read-only SHA-256 probes/timeout/recovery, allowed skips, observation
reviewers, archives/limitations, shared-document ownership, startup effects,
stop conditions, sync and opt-in quota path. Unknown input is a blocker with a
specific recovery choice; untagged tasks remain usable. Do not ask about machine
nicknames or subscription budget unless relevant.

New goals get stable IDs, early evidence-building milestones and coarse later
milestones. Adopted goals keep their wording and order. Add Checks annotations to
free-text criteria after approval; historical checked boxes receive documented
limitations, never new invented PASS. Reserve milestone scope/order/criteria and
sign-off to the configured owner. Policy-Approval and Signed-off record approval;
they cannot authenticate a person. The skill must obtain the actual instruction.

The review includes the selected task and a sample continuation:

```text
Goal: Tiny project
Milestone: 1. Build (0/2 tasks)
Next: 1.1 Implement tiny function; Needs you: none
```

Setup draft inventory: overlay, roadmap, short handoff, instruction pointer diffs,
closure recommendation/alternatives, retained existing policy and exact missing
input recovery. Verify a second identical application produces no diff.

With a startup helper, draft `readiness: "cache:readiness.json"`. Helpers use
`lh.py paths --root PATH --json` for the per-worktree destination and cache
identity; follow [publication and recovery](../../resume/reference/readiness.md).
