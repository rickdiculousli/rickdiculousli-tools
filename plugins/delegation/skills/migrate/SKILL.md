---
name: migrate
description: Use only when the user asks to migrate or upgrade a repository's delegation files, or accepts the version-mismatch offer from the delegation skill. Lints the checkout against the installed plugin's current contract, fixes what differs with approval, and tags the overlay with the plugin version.
---

# Delegation migrate

Bring a repository's delegation files in line with the installed plugin. There
is no list of past versions to replay: `check.py lint` knows only the current
contract and reports what differs. Fix that until lint is clean, then tag the
overlay.

`<skill-dir>` is the directory containing this SKILL.md, and `<delegation-dir>`
is its sibling `<skill-dir>/../delegation`. Commands:

```sh
python3 <delegation-dir>/scripts/check.py [--root <worktree>] <command> ...
```

Read `<delegation-dir>/reference/overlay.md` for the current format. Work from
the target repo's worktree root.

## 1. Inspect

- `check.py pending` must print `No open delegations.` Close or hand back open
  work first; migrating under an open brief can change files it relies on.
- Run `check.py lint --json`. It reports:
  - `version`: `installed`, `tagged` and `status` (`mismatch`, `newer`,
    `current`, `none` without an overlay, `unknown` when the installed version
    can't be found);
  - `problems`: overlay errors, including `outdated` constructs the runtime no
    longer reads;
  - `warnings`: nonfatal overlay notes;
  - `layout`: items with `kind` (`missing`, `unexpected` or `outdated`), `path`,
    `message`, `remedy` and `severity`.
- If `status` is `newer`, stop: the installed plugin is older than the repo.
  Suggest updating it.
- If there is no overlay, there is nothing to migrate; offer the `setup` skill.

## 2. Propose

Show the user one list, grouped:

1. **Rewrites**: overlay and pointer edits that fix `problems`, `outdated` and
   `missing` items, as exact diffs. Use each item's `remedy`, and the overlay
   reference for the current form. Preserve unrelated prose.
2. **Deletions**: every `unexpected` path, with its `message`. Say what each one
   is. Nothing is deleted unless the user approves it, path by path or as a list.
3. **Anything unclear**: an item whose fix needs a decision you can't make from
   the repo, such as which runbook an unregistered file belongs to.

Wait for approval.

## 3. Apply

- Make the approved rewrites and deletions. Don't commit unless the user asks.
- A runbook or script you create or move must be tracked: `git add` it.
- Run `check.py lint --json` again. Repeat steps 2 and 3 until `ok` is true and
  no `layout` items remain, apart from deletions the user declined.
- Then set `## Version` to `version.installed` (add the heading if missing) and
  lint once more: `version.status` must be `current`.

## 4. Prove it

Migration changes repository files, so registered validators may need to run
again. Run each validator whose inputs changed through one delegation, as in
the setup skill's "Prove it" step, and report the results. A migration never
creates a PASS by itself.

Report what changed, what was deleted, what the user declined, and the new
`## Version`.
