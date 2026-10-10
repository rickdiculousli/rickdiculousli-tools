---
name: setup
description: Use only when the user asks to set up, enable, or update delegation for a repository (or invokes delegation setup). Surveys the repo, drafts the .agents/delegation.md overlay and the AGENTS.md pointer, gets the user's approval, writes them, and proves every validator runs through check.py.
---

# Delegation setup

Prepare a repository for the `delegation` skill: an overlay at
`.agents/delegation.md` and one pointer line in `AGENTS.md`. The overlay format is
in `<delegation-dir>/reference/overlay.md`; read it first.

`<skill-dir>` is the directory containing this SKILL.md, and `<delegation-dir>` is
its sibling `<skill-dir>/../delegation`. Commands:

```sh
python3 <delegation-dir>/scripts/check.py [--root <worktree>] <command> ...
```

Work from the target repo's worktree root. Write nothing until step 4.

## 1. Check the starting point

- It must be a git worktree (`check.py tree` exits 2 otherwise).
- If `.agents/delegation.md` exists, this is an update: run `check.py lint`, read
  the overlay, and in the remaining steps propose changes to it, not a rewrite.
- Note whether `AGENTS.md` already has the pointer line, and whether the repo has a
  `CLAUDE.md` that doesn't import `AGENTS.md` (`@AGENTS.md`). Claude Code reads
  only `CLAUDE.md`, so the pointer must be reachable from it too.

## 2. Survey (read-only)

Read the repo's own instructions first (`AGENTS.md`, `CLAUDE.md`, `README`), then
its build and test entry points (`pyproject.toml`, `package.json` scripts,
`Makefile`, `justfile`, `Cargo.toml`, CI workflows). Skim the tree; don't read
source in bulk. Collect:

| Overlay heading | Look for |
|---|---|
| `## Validators` | Commands that pass or fail mechanically: test suites, linters, type checks, consistency scripts. Each must run from the root, exit 0 on success, not edit tracked files (that makes results `unstable`), and finish in minutes. Prefer offline ones. Mark fast linters and format checks `[cheap]`; give slow suites `[timeout=<seconds>]`; give builds that compete for memory or a device the same `[lock=<name>]`. |
| `## Locks` | Each lock the validators use, with `slots` (how many such builds this machine can run at once; ask if unsure) and a `wait` limit. A validator with a lock needs a `timeout`. |
| `## Oracle` | What ultimately says work is right (golden files, reference traces, a spec suite). Tie prose to checks with `validator:<name>`. |
| `## Extra inputs` | Git-ignored files the validators depend on: golden traces, built binaries, downloaded fixtures. Only paths inside the repo. |
| `## Single writer` | Resources that break under concurrent writes or that only the judge should change: databases, tool projects behind an MCP server (Ghidra, Figma), generated tables fed to an apply step, shared lockfiles. |
| `## Findings` | An existing findings, decisions or research log and its schema. Its statuses must include `refuted`; propose adding it if missing. |
| `## Bulk work`, `## Tier hints` | Recurring high-volume work (per-module reading, porting, probe batches, triage of test output) and which tier fits: `execute` when it needs reasoning pinned by an oracle, `routine` when the right answer is obvious. |
| `## Return fields` | Facts the judge always wants back for this repo's work (offsets touched, files read, APIs called). |
| `## Parallel limit` | Lower it below 3 if a shared resource (an MCP server, a device, a rate-limited API) can't take parallel readers. |

Also run `git status --porcelain`. Untracked files that aren't ignored and churn on
their own (`.DS_Store`, editor swap files, local logs) change the tree hash and
make checks stale; list them for an ignore rule.

## 3. Draft and ask

Show the user, in chat:

1. The full overlay draft. Leave out any heading you have nothing real for; the
   base defaults cover it. Keep guesses out of the file.
2. The pointer line, exactly:
   `Delegation: follow the delegation skill; this repo's overlay is .agents/delegation.md.`
   and where it goes (`AGENTS.md`, plus `CLAUDE.md` if it doesn't import `AGENTS.md`).
3. Ignore-rule suggestions from the survey.
4. Open questions only for what the repo can't tell you: which resources are
   single-writer, which validators are trustworthy enough to count as `checked`,
   where findings should go, and the parallel limit for shared tools.

Wait for approval or edits.

## 4. Write

- Write `.agents/delegation.md` (create `.agents/` if needed).
- Append the pointer line to `AGENTS.md` (create it with just that line if
  missing), and to `CLAUDE.md` when step 1 found it doesn't import `AGENTS.md`.
- Apply the ignore rules the user approved.
- Don't commit unless the user asks.

## 5. Prove it

1. `check.py lint` must print `Overlay OK`. Fix and repeat.
2. Run every validator once through the ledger, under one setup delegation:
   - write a short brief to `.delegation/briefs/setup.md` ("Setup: prove each
     validator runs");
   - `check.py open --delegation setup-<YYYYMMDD> --tier routine --brief .delegation/briefs/setup.md`;
   - for each validator, `check.py run <name> --delegation setup-<YYYYMMDD>`, adding
     `--timeout 1800` for one without its own timeout;
   - `check.py close --delegation setup-<YYYYMMDD> --outcome done`, or
     `--outcome stuck --note "<which failed>"`.
3. A validator that fails or prints `unstable` isn't usable as written. Show its
   output tail (the full output is in the log it prints), propose a fix (a narrower command, an ignore rule, a missing build
   step), and re-run after the user agrees. A validator that is red for real
   (existing test failures) can stay, but say so.
4. `check.py pending` must print `No open delegations.`

Report one table: validator, result (`PASS`, `FAIL` or `unstable`), duration and
ledger id. Then list what was written, and anything left for the user.
