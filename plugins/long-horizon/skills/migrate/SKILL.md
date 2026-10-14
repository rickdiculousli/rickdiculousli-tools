---
name: migrate
description: Use only when the user asks to migrate or upgrade a repository's long-horizon files, or accepts the version-mismatch offer from long-horizon:resume. Lints the checkout against the installed plugin's current contract, fixes what differs through a reviewed draft, and tags the overlay with the plugin version.
---

# Long-horizon migrate

Use this as `long-horizon:migrate`. It brings a repository's long-horizon files
in line with the installed plugin. There is no list of past versions to replay:
`lh.py lint` knows only the current contract and reports what differs. Fix that
until lint is clean, then tag the overlay.

Locate the CLI as `../resume/scripts/lh.py` relative to this skill directory, or
use the user's explicit `LONG_HORIZON_SCRIPT`/script path. Quote paths. Read the
[overlay](../resume/reference/overlay.md), [goals](../resume/reference/goals-format.md)
and [readiness](../resume/reference/readiness.md) contracts for the current forms.

## 1. Inspect

```sh
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT" --json
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT" --fix --json
```

The first lists findings; the second also previews `lint --fix`'s mechanical
goals repairs as `diff`. Migration findings are:

- `version-mismatch` / `version-newer`: the overlay's `## Version` against the
  installed plugin. With `version-newer`, stop and suggest updating the plugin.
- `layout-outdated`: a form the runtime no longer reads (a `## Schema` heading,
  a readiness path without `cache:`, milestones without a `# Goal:` heading).
- `layout-missing`: a configured goals or handoff file that does not exist.
- `layout-unexpected`: a path that is not part of the layout, such as a
  checkout-local `.long-horizon/` directory.
- `activation-unreachable` and other `pointer-*` codes: the AGENTS.md/CLAUDE.md
  pointer.

If lint exits 2 with `invalid-environment`, the overlay doesn't parse; its
message names the line. Fix that first, the same way as below.

Add nothing the findings don't ask for: never add a `## Lanes` section (absent
means off), and leave an existing one alone. Goal-content findings are not
migration findings: `goal-criteria-missing`, `milestone-proof-missing`,
`signoff-precheck` and `archive-invalid` concern goal acceptance, which only the
user can settle. Leave them for resume/checkpoint and mention them in the report.
For an already completed goal whose archive fails, offer `archive check` and the
legacy acceptance path in the [goals format](../resume/reference/goals-format.md)
as a separate step, applied only after the user approves. A repository whose only finding is
`version-mismatch` gets exactly one change, the `## Version` tag (step 3).

Without an installed overlay there is nothing to migrate; offer
`long-horizon:setup`.

## 2. Draft and propose

Create a draft with `state draft --root "$PROJECT" --json` and write the changed
owned files under its `draft_directory`, as `long-horizon:setup` does. Follow
each finding's remedy and the reference for the current form; preserve
unrelated prose, ordering, criteria and evidence. A readiness path moving to
`cache:` also needs the startup helper to discover its destination with
`lh.py paths --root "$PROJECT" --json`; draft that change for the helper's owner.

Check the draft with `lint --overlay "$DRAFT/overlay.md" --draft-root "$DRAFT"`,
then show the user one list:

1. **Rewrites**: exact diffs of the drafted files and the `lint --fix` diff.
2. **Deletions**: every `layout-unexpected` path, plus an old checkout-local
   readiness file. Nothing is deleted unless the user approves it.
3. **Anything unclear**: a fix that needs a decision the repo can't settle, such
   as a goal title for headless milestones.

Wait for approval.

## 3. Apply

- Apply approved edits after checking the originals' digests, as setup does, and
  `lint --fix --apply` if its diff was approved. Make approved deletions.
- Run `lint --json` again. Repeat steps 2 and 3 until no error, `layout-*` or
  `pointer-*` finding remains, apart from deletions the user declined.
- Then set `## Version` in the overlay to the installed version named by the
  `version-mismatch` finding, and lint once more: no `version-*` finding remains.
- Remove the applied draft from the XDG cache. Don't commit unless the user asks
  or the overlay's integration authorization covers it.

## 4. Report

Run `status --root "$PROJECT" --brief`. Report what changed, what was deleted,
what the user declined, the new `## Version`, and any goal-content warnings left
for the user. Migration records no evidence
and creates no PASS; acceptance whose inputs changed needs its checks rerun.
