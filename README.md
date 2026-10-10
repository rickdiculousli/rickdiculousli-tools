# Rickdiculousli personal plugins

A personal plugin repository for Claude Code and Codex. Each plugin contains one
portable manifest and one set of skills. A small generator produces the host
compatibility manifests and marketplaces; consumers install directly from the
committed repository without a build step.

All three plugins have been installed, byte-compared, and uninstalled through the
real native marketplaces on Codex **0.160.1** and Claude Code **2.1.290**.
See [verification evidence and scope](docs/verification.md).

| Plugin | What it does |
| --- | --- |
| `visual-audit` | `audit-report` skill: renders what the agent did in a session as one self-contained HTML page for visual auditing |
| `hello-world` | Greeting stub for testing installation |
| `repository-info` | Informational stub describing this layout |
| `delegation` | `delegation` skill: the main session (judge) routes bulk work to `execute` and `routine` tier subagents and records validator evidence by git tree hash. Not yet lifecycle-verified |

## Visual audit reports

Ask for an audit report at the end of a session (`/visual-audit:audit-report` in
Claude Code, or ask Codex to use the `audit-report` skill). The agent writes
`.audit/<timestamp>-<slug>.json` in the working directory and renders it with the
bundled Python 3 standard-library script into `.audit/<timestamp>-<slug>.html`. The
renderer creates `.audit/.gitignore`, so reports stay out of version control.

The page opens with a verdict band (outcome, contradictions, failure and provenance
counts, a run strip of every step), then a "Needs attention" list, then the timeline,
file changes, commands and tests, claims with linked proof, and any figures. Items
the agent could not back with observed evidence are outlined with dashes. See the
[schema reference](plugins/visual-audit/skills/audit-report/reference/schema.md) and
[example report](plugins/visual-audit/skills/audit-report/reference/example-report.json).
To render a report by hand:

```sh
python3 plugins/visual-audit/skills/audit-report/scripts/render_report.py report.json -o report.html
```

## Install from this checkout

Run these commands from the repository root. They register this local checkout
and install the plugins in your normal user profile.

### Claude Code

```sh
claude plugin marketplace add "$PWD"
claude plugin install visual-audit@rickdiculousli-plugins
claude plugin install hello-world@rickdiculousli-plugins
claude plugin install repository-info@rickdiculousli-plugins
claude plugin list --available --json
claude plugin details visual-audit
```

In a new Claude Code session, invoke `/visual-audit:audit-report`,
`/hello-world:hello`, or `/repository-info:about`. Restart an existing session after changing plugins.

### Codex

```sh
codex plugin marketplace add "$PWD"
codex plugin add visual-audit@rickdiculousli-plugins
codex plugin add hello-world@rickdiculousli-plugins
codex plugin add repository-info@rickdiculousli-plugins
codex plugin list --marketplace rickdiculousli-plugins --available --json
```

In a new Codex session, ask it to use the `audit-report` skill from
`visual-audit`, the `hello` skill from `hello-world`, or the `about` skill from
`repository-info`.

### Uninstall

```sh
claude plugin uninstall visual-audit@rickdiculousli-plugins
claude plugin uninstall hello-world@rickdiculousli-plugins
claude plugin uninstall repository-info@rickdiculousli-plugins
claude plugin marketplace remove rickdiculousli-plugins

codex plugin remove visual-audit@rickdiculousli-plugins
codex plugin remove hello-world@rickdiculousli-plugins
codex plugin remove repository-info@rickdiculousli-plugins
codex plugin marketplace remove rickdiculousli-plugins
```

Once this repository is hosted in Git, both marketplace `add` commands also
accept its Git repository URL. The marketplace uses relative plugin paths, so
the same committed layout can be consumed from a clone. Remote hosting and Git
URL installation have not been verified yet.

## Layout

```text
catalog.json                         # marketplace owner and ordered plugin paths
plugins/<name>/
  plugin.json                        # authored portable metadata
  skills/<skill>/SKILL.md             # authored once; shared by both hosts
  .claude-plugin/plugin.json          # generated compatibility metadata
  .codex-plugin/plugin.json           # generated compatibility metadata
  tiers.json                          # optional: subagent tiers (delegation)
  agents/<tier>.md                    # generated from tiers.json (Claude Code)
.claude-plugin/marketplace.json       # generated Claude marketplace
.agents/plugins/marketplace.json      # generated Codex marketplace
scripts/sync_marketplaces.py          # deterministic metadata generation
scripts/verify_lifecycle.py           # real CLI integration checks
tests/                               # generator, verifier, and renderer tests
```

`visual-audit` ships its renderer, templates, and references inside its skill
folder. `hello-world` and `repository-info` are stubs. None of them need
credentials or external services. The adapters share identity and content, while translating the hosts'
different marketplace source formats.

## Add or change a plugin

1. Create `plugins/<name>/plugin.json` using the portable format shown in an
   existing stub. Use a unique lowercase kebab-case name matching the directory,
   a version, and a description.
2. Add at least one `skills/<skill>/SKILL.md` inside that plugin, with `name` and
   `description` YAML frontmatter. Put any resources the skill needs inside the
   same plugin so installation remains self-contained.
3. Add `"plugins/<name>"` to `catalog.json` in the desired listing order.
4. Regenerate host metadata and verify the changes:

```sh
python3 scripts/sync_marketplaces.py
python3 scripts/sync_marketplaces.py --check
python3 -m unittest discover -s tests -v
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```

Commit the sources and generated files together. Edit root `plugin.json` and
`catalog.json`; regeneration replaces host manifests. Bump the plugin version
when releasing changed content. To refresh an installed plugin after edits,
regenerate, uninstall and reinstall it, then start a new session. Marketplace
registration alone does not guarantee an existing installed cache has refreshed.

New plugins are included automatically in lifecycle verification. Future MCP
servers, hooks, or host-specific components need explicit adapter support and
host verification.

A plugin with a `tiers.json` (currently only `delegation`) also gets generated
subagent tiers: one Claude Code agent `agents/<tier>.md` per tier marked
`"subagent": true`, carrying its `model` and `effort`, and a host table at the
path named by `reference`, which tells each host how to start a tier. Codex
plugins can't ship agent definitions, so `routes.codex` (`spawn`, `same-model`
or `definitions`) selects the Codex instructions in that table. Model ids live
only in `tiers.json` and the generated files. In such a plugin, any
`agents/*.md` the generator doesn't produce is drift: `--check` fails and a
sync deletes it.

## Verify without changing your installed plugins

Development scripts require Python **3.10+**, with no third-party packages.
Lifecycle verification additionally requires `codex` and `claude` on PATH with
the plugin subcommands used above. The tested versions are recorded in
[docs/verification.md](docs/verification.md); older releases may differ.

```sh
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```

This registers the marketplace, discovers and installs every catalog plugin,
confirms enabled state, compares every committed plugin file with its installed
copy byte for byte (reporting missing, changed, and extra files), uninstalls the
plugins, and
removes the marketplace in disposable profiles. It fails on missing CLIs,
unsupported output, or incomplete stages. A JSON report retains command output
and any cleanup failures. Temporary profiles are deleted afterward.

Contributor instructions live in [AGENTS.md](AGENTS.md); Claude Code imports
that same file through [CLAUDE.md](CLAUDE.md).
