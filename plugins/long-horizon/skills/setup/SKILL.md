---
name: setup
description: Set up, adopt, update, add a goal to, or wind down long-horizon progress across sessions, using reviewed concrete drafts and a shared portable CLI.
---

# Long-horizon setup

Use this as `long-horizon:setup`. Read [interview](reference/interview.md),
[goals template](reference/goals-template.md), [handoff template](reference/handoff-template.md)
and [overlay grammar](../resume/reference/overlay.md). Locate the sibling CLI as
`../resume/scripts/lh.py` relative to this skill directory, or use the user's
explicit `LONG_HORIZON_SCRIPT`/script path. Quote the resolved path in commands.
Do not guess an installed cache version. Python 3.10+ and Git are sufficient.

A goal is the outcome; ordered milestones bound acceptance; tasks are the next
pieces of work. Readiness says inputs are prepared. Evidence says a named check
was actually observed. The default batch is one task or one blocker resolution.

1. Survey once, read-only: discover the Git worktree/common directory, branch,
   default branch, dirty paths, AGENTS/CLAUDE policy, roadmap, handoff, validator
   names, readiness helpers and declared script paths. Inspect current overlay
   first, then default and other local branches/worktrees without fetching. Reuse
   existing answers. A unique other overlay can be offered; differing candidates
   need one choice in the draft. Preserve branch-specific policy and dirty work.
2. Choose the requested mode: new, adopt, update, add-goal or wind-down. New starts
   from an aim. Adopt preserves existing prose, ordering, criteria and evidence;
   add IDs and check annotations without inventing historical PASS. Update edits
   only the requested policy. Add-goal reuses the previous survey and reactivates
   a dormant overlay. Unshelving restores the preserved roadmap, not a new goal.
3. Ask the quick questions together (at most five; see interview). “You decide”
   means choose safe defaults and explain them in the draft. Full mode expands
   acceptance, inputs, ownership and recovery only where the project needs it.
   Suggest `delegation:setup` if bulk work or ledger-worthy validators warrant it;
   pass along survey notes and validator names, never duplicate their commands.
   Do not install tools, configure delegation or run startup implicitly.
4. Create an identity-bearing draft with `python3 "$LONG_HORIZON_SCRIPT" state draft --root "$PROJECT" --json`. Draft only owned files under its returned `draft_directory`. The status `cache_directory` is scoped by repository/worktree keys; drafts live in its `drafts/<unique-id>/` directory. This is ${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/long-horizon/, resolved in Python; do not use a sibling XDG cache directory or shell-expand a home fallback. Use the actual root
   for Git identity and `--draft-root` for all draft managed paths. Show together:
   goals/overlay/handoff, exact pointer edits, dry-run status and chosen task,
   missing inputs, a sample three-line session, and closure recommendation.
   Recommend validate/commit/merge to the configured default branch/push: a fresh
   session can start from current shared history. Offer commit only, merge only,
   PR or ask each time. Write standing integration authorization only after actual
   approval for the named steps/target/remote/stop conditions. Existing session
   authorization applies; an identical already-approved rerun is a no-op.
5. Approval is the final step before applying the concrete draft. Apply surgical
   edits after checking original file digests; preserve unrelated prose and dirty
   paths. Add exactly one pointer to AGENTS.md:
   `Long horizon: follow long-horizon:resume and long-horizon:checkpoint; overlay .agents/long-horizon.md.`
   Ensure CLAUDE.md reaches it, normally through one `@AGENTS.md` import. Preserve
   existing imports/host policy. Do not add a repository runtime directory/ignore.
6. Run the commands below with the resolved CLI and actual checkout. Lint errors
   require repair; warnings can proceed. Remove applied/cancelled scratch drafts from XDG cache after verifying their owned files; preserve the generated `identity.json` while drafting so collection can recognize the payload. Use `state draft --id <id>` to renew an existing draft before reuse; keep any explicitly retained recovery draft with a 30-day expiry. Show chosen task, Needs you, and where
   acceptance/integration still need approval. Do not claim a model pilot from
   source review, installation or these CLI checks.

```sh
python3 "$LONG_HORIZON_SCRIPT" status --root "$PROJECT" --overlay "$DRAFT/overlay.md" --draft-root "$DRAFT" --json
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT" --overlay "$DRAFT/overlay.md" --draft-root "$DRAFT" --json
python3 "$LONG_HORIZON_SCRIPT" state gc --apply --if-due --json
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT"
python3 "$LONG_HORIZON_SCRIPT" status --root "$PROJECT" --brief
```

Wind-down requires an approved exact diff: mark state dormant, remove only this
plugin's pointer/import, retain goals/archives/findings and other plugin policy;
keep, replace or remove handoff only as approved. Display the resolved XDG payload
path. Clear that payload only after approval using the locked helper described in
[retention](../resume/reference/state.md); no deletion of repository files or
other worktrees. A later add-goal restores one pointer/import and retained policy.
Shelve/drop only on actual user instruction, with reason and preserved roadmap.
Sign-off rejection reopens the rejected work with its reason and keeps historical
evidence; a later acceptance needs appropriate fresh checks.

Preserve the host’s existing shared XDG state/cache roots across every CLI call.
Never redirect them into a checkout, Git directory or installed plugin, including
for temporary isolation. For tests use an explicitly supplied external disposable
XDG root; no checkout-local scratch state.
