# Migrate skills for delegation and long-horizon

Status: design agreed 2026-10-12; targets delegation 0.10.0 and long-horizon 0.5.0.
Supersedes the migration sections of the
[XDG addendum](2026-10-11-xdg-state-and-locks-addendum.md).

## Purpose

Each plugin gets a `migrate` skill (`delegation:migrate`, `long-horizon:migrate`)
that brings a consuming repository in line with the installed plugin. The skill
does not replay a history of upgrades. The CLI's `lint` knows only the current
contract and reports what is missing, unexpected or outdated; the agent fixes
those findings, re-lints until clean, then records the plugin version in the
overlay. Future releases change what lint expects, not the skill.

## Decisions

1. **Current contract only.** No migration step list and no compatibility shims.
   Nothing predates the XDG layout, so pre-XDG handling is removed:
   - delegation: `check.py state migrate`, the legacy `.delegation/` ledger
     guard, migration receipts and `.delegation/context/` references;
   - long-horizon: the `legacy-state` finding.
   Other superseded forms stop working at runtime and become lint errors:
   - delegation role runbooks named `state:context/...` (roles name tracked
     sources);
   - long-horizon readiness paths without `cache:`;
   - long-horizon roadmaps without `# Goal:` headings;
   - the long-horizon `## Schema` overlay heading (replaced by `## Version`).
2. **Lint is the single definition of "current".** `check.py lint [--json]` and
   `lh.py lint` report layout findings tagged `missing`, `unexpected` or
   `outdated`, each with a remedy. There is no separate migrate subcommand.
3. **Scope** is plugin-owned paths in the consuming checkout:
   - delegation: `.agents/delegation.md`, `.agents/delegation/**`, its AGENTS.md
     pointer, and a stray `.delegation/` directory;
   - long-horizon: `.agents/long-horizon.md`, the configured goals, handoff,
     archive and evidence paths, the pointer, a stray `.long-horizon/` directory
     and a leftover checkout-local readiness file.
   XDG payloads stay with `state gc`.
4. **Deletion needs approval.** `unexpected` findings are proposals; the agent
   deletes only after the user approves the list. Tracked rewrites go through
   the plugin's normal draft and review flow.
5. **Version tag.** Each overlay carries `## Version` with the plugin version
   (for example `0.10.0`) it was last linted clean against. Setup and migrate
   write it, and only after a clean lint.
6. **Mismatch prompt.** `lh.py status` (used by resume) and `check.py lint`
   (run at delegation session start) emit a `version-mismatch` warning when the
   installed plugin's major.minor differs from the tag or the tag is missing.
   The skills ask "run migration?". Patch differences are ignored. A tag newer
   than the installed plugin emits `version-newer`: update the plugin, do not
   migrate. Declining continues the session without repeating the prompt.
7. **Triggering.** Migrate runs only when the user asks or accepts the prompt.
8. **Release.** Minor bumps, regenerated host manifests, tests, and a
   `docs/verification.md` entry.

## Installed version discovery

The CLIs read the version from the nearest `plugin.json`, falling back to
`.claude-plugin/plugin.json` or `.codex-plugin/plugin.json`, walking up from the
script. If none is found the version check is skipped and reported as unknown.

## Finding shape

Long-horizon findings keep their existing JSON shape; new codes are
`layout-missing`, `layout-unexpected`, `layout-outdated`, `version-mismatch` and
`version-newer`. Delegation lint keeps its text output (problems, then
`warning:` lines) and adds `--json`:

```json
{"ok": true, "overlay": "...", "version": {"installed": "0.10.0", "tagged": "0.9.1", "status": "mismatch"},
 "problems": ["..."], "warnings": ["..."],
 "layout": [{"kind": "unexpected", "path": ".delegation", "message": "...", "remedy": "..."}]}
```

Outdated constructs that the runtime refuses are errors; unexpected paths and
version findings are warnings, so they never block work.
