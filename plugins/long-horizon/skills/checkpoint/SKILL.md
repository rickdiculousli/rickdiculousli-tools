---
name: checkpoint
description: Checkpoint bounded long-horizon work with scoped durable evidence, owned roadmap/handoff edits, acceptance gates and separately verified authorized closure steps.
---

# Long-horizon checkpoint

Resolve `../resume/scripts/lh.py` relative to this skill directory or an explicit
`LONG_HORIZON_SCRIPT`/path; quote paths. Read [evidence](reference/evidence.md),
[goals](../resume/reference/goals-format.md) and [retention](../resume/reference/state.md).

1. Collect due state cleanup. If delegation is configured, inspect its pending
   workers through the declared checker CLI; they must hand back before closure.
   Do not close/reset workers here or implement another ledger/tree hash.
2. Reuse fresh scoped durable evidence where appropriate. For a new check prepare
   before running it; run only the actually authorized validator/review; record
   the observed result afterward. The CLI runs no validator. External checks need
   authorized `--probe-inputs` before and after. Record failures, skips and unstable
   runs honestly. A current delegation claim needs the exact-tree registered
   stable result; convert it before changing goals/handoff. To run a registered
   validator yourself use delegation's `check.py run <name> --judge`; it records a
   `judge-*` delegation that closes with the run. Reviewed observations record
   `--reviewer-kind`; only a check with `"reviewer": "any"` accepts an agent.
   Subsequent docs edits retain historical scoped provenance, not new current-tree
   checked results.
3. Honor the user’s checkpoint boundary: when asked to keep tasks open, record
   evidence only and leave every checkbox open. Completion defaults do not override
   that instruction. Review record's proposed durable JSON/log recovery files and write only those
   owned paths (`--write-proposed` writes exactly them; `--trailers-file` accumulates
   the batch's trailers). After an approved criteria change use `evidence rerecord`. Add adjacent task citations. A task done is not a milestone PASS:
   whole-call milestone criteria need their named fresh checks. At a milestone
   boundary triage parked work and refine the next coarse milestone according to
   ownership; obtain actual approval for reserved order/scope/criteria changes.
4. Update only owned goals/handoff/findings. Before writing the handoff read its
   `lines`/`budget` from status and trim first if it is near or over. A tiny batch
   needs one continuation line. On last milestone build a completion archive with every ordered milestone,
   criteria, evidence/exceptions, limitations, refuted ideas and follow-ups; wait
   for actual required user sign-off. Rejection reopens the rejected work. Shelve,
   drop, unshelve and wind-down follow setup's preserved-record flow.
5. Gate against HEAD before committing, or explicit pre-batch base after commit.
   Pass each pending ID explicitly. Run lint; warning-only findings can proceed.
   A missing gate proof offers run-check, task-only completion with milestone open,
   or an explicitly accepted targeted exception. No automatic PASS from prose,
   readiness, missing ledger, skipped tests or sign-off text.
6. Build the owned path/content manifest with `closure manifest --base <pre-batch>`
   (`--path` to exclude unrelated dirty work), review it, and assemble the commit
   message with canonical trailers. Stage only owned paths, preserving unrelated dirty work.
   Perform only the recorded authorized integration steps in order. `lh.py` never
   commits/merges/fetches/pushes/syncs. Record actual outcomes and verify before
   retrying. Dirty/unavailable target worktree means a precise remaining merge,
   never a forced switch, history rewrite or destructive cleanup.
7. Resolve pending IDs in the exact carrying commit, then clean their XDG copies;
   interrupted cleanup is harmless. Verify commit, target ancestry, local remote
   ref observation and host sync independently. Preserve successful steps if a
   later push/sync fails; retry only the first unfinished authorized operation.
8. Report completed task, evidence status and exact closure/remaining step, Needs
   you, and recommend a fresh session once the batch actually closes. Do not write
   another commit merely to claim the preceding push.

Standalone walkthrough (variables are explicit paths/IDs from reviewed output):

```sh
python3 "$LONG_HORIZON_SCRIPT" state gc --apply --if-due
python3 "$LONG_HORIZON_SCRIPT" evidence prepare validator:unit --root "$PROJECT" --attempt "$ATTEMPT" --json
# Run the project's actually authorized unit check now.
python3 "$LONG_HORIZON_SCRIPT" evidence record validator:unit --root "$PROJECT" --snapshot "$SNAPSHOT" --outcome PASS --command "$OBSERVED_COMMAND" --exit 0 --log "regenerate:the declared unit check against this commit" --trailers-file "$TRAILERS" --write-proposed --json
# Review the written detail files; add task Evidence and owned handoff edits.
python3 "$LONG_HORIZON_SCRIPT" evidence find validator:unit --root "$PROJECT" --pending "$EVIDENCE" --json
python3 "$LONG_HORIZON_SCRIPT" gate --root "$PROJECT" --pending "$EVIDENCE"
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT"
python3 "$LONG_HORIZON_SCRIPT" closure manifest --root "$PROJECT" --base "$BASE" --json
# Review the manifest (path, batch) and a message containing TRAILERS; stage owned paths.
# When authorized: git -C "$PROJECT" commit --file "$MESSAGE"
python3 "$LONG_HORIZON_SCRIPT" closure record --root "$PROJECT" --batch "$BATCH" --step commit --outcome success --commit "$COMMIT" --manifest "$MANIFEST"
python3 "$LONG_HORIZON_SCRIPT" evidence cleanup --root "$PROJECT" --commit "$COMMIT" --id "$EVIDENCE" --json
python3 "$LONG_HORIZON_SCRIPT" closure verify --root "$PROJECT" --json
```

If policy starts with validate, record that step first with the same manifest and
explicit accepted IDs. Batch is the SHA-256 digest reported by manifest validation
(see evidence reference); `closure manifest` reports both. Validate against the
pre-batch base for committed goals.

Combined walkthrough, using delegation's declared public checker:

```sh
python3 "$LONG_HORIZON_SCRIPT" evidence prepare validator:unit --root "$PROJECT" --json
# Run the registered validator via delegation (a worker's run, or the judge's own
# `check.py run unit --judge`, whose judge-* ID is the delegation); do not restate its command.
python3 "$LONG_HORIZON_SCRIPT" evidence record validator:unit --root "$PROJECT" --snapshot "$SNAPSHOT" --outcome PASS --delegation "$DELEGATION" --result "$RESULT" --log "regenerate:registered unit validator via the declared checker" --json
```

Do not use `check.py exec` as a forged registered validator. A missing ledger can
leave durable evidence fresh and still means no current checked result. Exceptions
need actual approval, reason, check, target and matching policy revision; they
cannot waive sign-off or authorize integration operations.

If the overlay has a `## Lanes` section with `config`, read
[lanes](../resume/reference/lanes.md) before step 6: it says who runs the
integration steps. Otherwise ignore lanes entirely.

Preserve the host’s existing shared XDG state/cache roots across every CLI call.
Never redirect them into a checkout, Git directory or installed plugin, including
for temporary isolation. For tests use an explicitly supplied external disposable
XDG root; no checkout-local scratch state.
