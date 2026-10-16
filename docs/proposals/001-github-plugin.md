---
id: 001
title: A github plugin: watch a pull request, post review findings, and edit these plugins end to end
kind: feature
size: M
judge: opus
status: proposed
lens: eng
proposed_by: operator
proposed_on: 2026-10-16
---

## Opportunity
Three tools the operator uses on every box live in a separate coordinator repository that is being retired:
- **A PR watcher** (192 lines): it reads an upstream pull request through `gh api graphql`, keeps a snapshot, and prints only what changed since the last look: head moved, state or milestone changed, new replies on our review threads, threads resolved or outdated, new top-level comments.
- **A skill that posts review findings** (72 lines): inline comments on the line where the bug is, in the operator's terse register, with one signoff line, checking the PR head against the commit reviewed first.
- **A skill that edits these plugins end to end**: level the boxes, edit under this repo's AGENTS.md, bump the version, verify, push `main`, then roll out to every box.

None of them is about the coordinator. They belong with the operator's other plugins, installed from here on every box.

## Proposal
In:
- **`plugins/github/`**, a new plugin with:
  - `skills/pr-watch/` and its PEP 723 script. Its snapshot moves from the coordinator's `cache/pr-watch/` to `${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/github/pr-watch/`, and the script takes `--state-dir`. Behaviour is otherwise unchanged.
  - `skills/pr-comment/`, the posting skill. Every mention of a client repository or its tracker becomes generic: "the tracker that owns the review", as this repo's anonymization rule requires.
  - Tests for the watcher's diffing, against recorded GraphQL fixtures.
  - `plugin.json` at `0.1.0`, an entry in `catalog.json`, and manifests regenerated with `scripts/sync_marketplaces.py`.
- **The editing skill** becomes `plugins/github/skills/plugin-editor/`, reworded for this repo:
  - It levels and rolls out through a configurable sync command, `PLUGIN_SYNC_COMMAND`, defaulting to `bmesh sync --repo <this checkout>`, instead of the coordinator's script.
  - When that command is missing, it says how to roll out by hand: pull on each box, then `claude plugin update` and `codex plugin add`.
  - It names `method:writing-skills`, or the written default, in place of the retired superpowers skill.
- **The README** gets the plugin's section.

Out: deleting the originals (the coordinator's retirement does that); any change to the watcher's output.

Judge: opus, because the moves are mechanical, but the skills must lose every client-specific detail without losing what makes them work.

## What you'll see
`/plugin` lists `github@rickdiculousli-tools` with three skills. "What changed on PR 312 of owner/repo" runs the watcher from the plugin, keeping its snapshot under XDG state.

## Verification
The repo's verify (`sync_marketplaces.py --check`, `run_tests.py`, `verify_lifecycle.py`), with the watcher's new tests; results recorded in `docs/verification.md`.

## Risks and the alternative considered
Folding these into the buildermesh plugin was the other option, but that plugin may name nothing of any one fleet or operator, and a PR watcher isn't about a mesh.

## Needs from the operator
Move the existing snapshot (`~/repos/command-center/cache/pr-watch/`) to the new state dir on k16, or let the first run take a new baseline.
