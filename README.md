# Rickdiculousli personal plugins

A personal plugin repository for Claude Code and Codex. Each plugin contains one
portable manifest and one set of skills. A small generator produces the host
compatibility manifests and marketplaces; consumers install directly from the
committed repository without a build step.

Both stub plugins have been installed, inspected, and uninstalled through the
real native marketplaces on Codex **0.160.1** and Claude Code **2.1.290**.
See [verification evidence and scope](docs/verification.md).

## Install from this checkout

Run these commands from the repository root. They register this local checkout
and install both examples in your normal user profile.

### Claude Code

```sh
claude plugin marketplace add "$PWD"
claude plugin install hello-world@rickdiculousli-plugins
claude plugin install repository-info@rickdiculousli-plugins
claude plugin list --available --json
claude plugin details hello-world
claude plugin details repository-info
```

In a new Claude Code session, invoke `/hello-world:hello` or
`/repository-info:about`. Restart an existing session after changing plugins.

### Codex

```sh
codex plugin marketplace add "$PWD"
codex plugin add hello-world@rickdiculousli-plugins
codex plugin add repository-info@rickdiculousli-plugins
codex plugin list --marketplace rickdiculousli-plugins --available --json
```

In a new Codex session, ask it to use the `hello` skill from `hello-world` or
the `about` skill from `repository-info`.

### Uninstall

```sh
claude plugin uninstall hello-world@rickdiculousli-plugins
claude plugin uninstall repository-info@rickdiculousli-plugins
claude plugin marketplace remove rickdiculousli-plugins

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
.claude-plugin/marketplace.json       # generated Claude marketplace
.agents/plugins/marketplace.json      # generated Codex marketplace
scripts/sync_marketplaces.py          # deterministic metadata generation
scripts/verify_lifecycle.py           # real CLI integration checks
tests/                               # generator and failure-handling tests
```

`hello-world` provides a greeting stub. `repository-info` provides an
informational stub describing this layout. They need no credentials or external
services. The adapters share identity and content, while translating the hosts'
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
host verification; the two stubs establish portable skills only.

## Verify without changing your installed plugins

Development scripts require Python **3.10+**, with no third-party packages.
Lifecycle verification additionally requires `codex` and `claude` on PATH with
the plugin subcommands used above. The tested versions are recorded in
[docs/verification.md](docs/verification.md); older releases may differ.

```sh
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```

This registers the marketplace, discovers and installs every catalog plugin,
confirms enabled state and installed skill bytes, uninstalls the plugins, and
removes the marketplace in disposable profiles. It fails on missing CLIs,
unsupported output, or incomplete stages. A JSON report retains command output
and any cleanup failures. Temporary profiles are deleted afterward.

Contributor instructions live in [AGENTS.md](AGENTS.md); Claude Code imports
that same file through [CLAUDE.md](CLAUDE.md).
