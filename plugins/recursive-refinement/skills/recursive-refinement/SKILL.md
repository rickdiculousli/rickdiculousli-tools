---
name: recursive-refinement
description: Runs one refinement pass on one repo, measured against its jobs and the week's real conversations; small reversible changes land on their own, the rest become specs. Use when the weekly scheduler starts a pass or the user runs it on a repo.
disable-model-invocation: true
---

# Recursive refinement

Without this, a pass grades the setup against tests the agents wrote, hands the user a list of findings, or grows the setup it was meant to trim.

The prompt names `repo=<path>` and `mode=land` or `mode=dry-run <file>`. A dry run changes nothing in the repo: it writes every item, with its landing-line checks, to `<file>` and stops.

## Read first

- `<repo>/docs/refinement/rules.md`: the user's leash. `paused: yes` → stop and write nothing. Its limits override everything below.
- `<repo>/docs/refinement/jobs.md`: the yardstick. `status: pending` → this pass writes specs only.
- The repo's `AGENTS.md` (or `CLAUDE.md`): its checks and commit rules apply to every change.
- `<repo>/docs/refinement/specs/*.md` with `status: approved`: the user said yes. Build these first, through the same landing steps; then set `status: built`.
- The week's conversations, by script, never a transcript whole:
  `uv run --script <skill-dir>/scripts/refine.py conversations <repo>`
  (`--session <id>` reads one session; `<skill-dir>` is this file's folder). They are the only evidence of use: never a question set, eval or fixture, and never agent-written audits, reviews or notes. When `jobs.md` names other repos, read theirs too.

## Find

1. Use `pick-principles` at this design threshold.
2. Read pocock's `retro` and `improve-codebase-architecture` by path (`ls -d ~/.claude/plugins/cache/*/pocock/*/skills/<name>/SKILL.md | sort -V | tail -1`; both are explicit-only). Apply retro's categories to the conversations and the architecture scan's step 1 (hot spots from the week's `git log`, the deletion test) to the code. Skip their reports, questions and grilling: findings go through the landing line below, never to the user as a list.
3. Keep a finding only if it names the job it serves (from `jobs.md`) and its evidence: a dated moment in the conversations or a hot spot. Something that serves no job is a candidate to delete.

## The landing line

A change lands on its own only if every part holds. Check each and write down how:

1. One `git revert` undoes it: one commit, no data migration, nothing outside the repo.
2. Nothing in the user's record is lost, checked (the diff touches no record file `rules.md` lists, or a count before and after matches).
3. What the user sees changes by one noticeable line at most.
4. Where the data lives and who sees it stay the same.
5. It fits the pass's budget.

It also needs `rules.md` to allow it and `jobs.md` to be confirmed. Settle and record items one at a time (land it, or write its spec or its dry-run entry), so a pass cut off by its budget keeps what it finished. Everything else is a spec. Removing anything the user asked for is always a spec, and so is any change to `rules.md`.

## Land (mode=land)

One change per branch, in a worktree outside the repo:

```sh
W="${XDG_CACHE_HOME:-$HOME/.cache}/rickdiculousli-tools/recursive-refinement/worktrees/<repo-name>-<slug>"
B=$(git -C <repo> symbolic-ref --short HEAD)
git -C <repo> worktree add -b refinement/<yyyy-mm-dd>-<slug> "$W" "$B"
```

A worktree has no `.venv`: link the checkout's (`ln -s <repo>/.venv "$W/.venv"`) or let `uv` make one. Make the change and append its note to `docs/refinement/notes.md` in the same commit: `- <yyyy-mm-dd>: <what changed for the user, one line, plain words>`. Run the repo's checks in `$W`, commit under the repo's commit rules, then `git -C <repo> merge --ff-only <branch>` and `git -C <repo> push origin "$B"`. If a check fails or the merge won't fast-forward after one rebase, drop the change and write it as a spec. Remove the worktree and branch either way.

## Spec

One file per idea, `docs/refinement/specs/<yyyy-mm-dd>-<slug>.md`, committed through the same steps:

```markdown
---
status: open
---
# <the idea in the user's terms>

- **Job:** which job in `jobs.md` it serves.
- **Value to the user:** what gets better for them, in their words where possible.
- **Cost:** money, effort, and what they'd see change.
- **Recommendation:** yes or no, and why, in one line.
- **Evidence:** dated moments from the conversations (paraphrase marked) or the hot spot.
- **Plan:** how it would be built, short enough to build from once approved.
```

The session-start hook shows each open spec as one "Needs you" item. The user answers yes, no or "tell me more"; the advisor sets `status: approved` or `rejected`.

## Report

The final message is for the scheduler's log: what landed (one line each), what was specced, and anything that failed. End it, and a dry-run file, with: "You can refine this weekly pass too: say what it should stop touching, to be bolder, or to pause, in any session."
