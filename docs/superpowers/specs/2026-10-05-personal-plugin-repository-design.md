# Personal plugin repository

## Outcome

Initialize this empty repository as Rick Li's personal plugin marketplace for
Claude Code and Codex. Author reusable plugin content once. Completion requires
real CLI evidence that both marketplaces discover the stub plugins and that each
stub can be installed, inspected while installed, and uninstalled.

The user approved the proposed shared-content design with “Go.” This document
makes that design concrete for review before implementation planning.

## Layout and sources of truth

```text
catalog.json
plugins/
  hello-world/
    plugin.json
    skills/hello/SKILL.md
    .claude-plugin/plugin.json       (generated)
    .codex-plugin/plugin.json        (generated compatibility fallback)
  repository-info/
    plugin.json
    skills/about/SKILL.md
    .claude-plugin/plugin.json       (generated)
    .codex-plugin/plugin.json        (generated compatibility fallback)
.claude-plugin/marketplace.json      (generated)
.agents/plugins/marketplace.json     (generated)
scripts/
  sync_marketplaces.py
  verify_lifecycle.py
tests/
README.md
AGENTS.md
CLAUDE.md
docs/verification.md
```

`catalog.json` supplies the marketplace name `rickdiculousli-plugins`, owner
`Rick Li`, and ordered plugin paths. Each root `plugin.json` supplies canonical
plugin identity, version, description, and author using the portable Agent
Plugins format. Metadata is never authored separately for the two hosts.

The generator reads these sources and produces both marketplace files and thin
host compatibility manifests. Generated files are committed so a consumer can
install directly from a checkout without running a build. A check mode reports
drift without rewriting files. It rejects duplicate names, unsafe paths, missing
plugins, and conflicting identities before writing output.

Plugin folders are self-contained: all skill content and future scripts or
assets belong inside their plugin. Both hosts consume the same folders and
bytes. No symlinks, duplicated skill trees, external shared runtime folders, or
host-specific instructions in the stub skills are needed. Future host-specific
features can extend the adapters without changing this ownership model.

## Stub behavior

`hello-world` contains one deliberately small skill, `hello`, which responds
with a recognizable greeting when explicitly invoked. `repository-info`
contains one skill, `about`, which describes the portable plugin layout. Both
are marked as examples in their descriptions and have version `0.1.0`.

Neither stub includes hooks, external services, credentials, or MCP servers.
These examples establish packaging and skill discovery; they do not imply that
future host-specific hooks or agents are portable.

## Tooling and documentation

Use Python's standard library for generation and lifecycle verification, with
no package installation or language-specific build system. Tests cover useful
invariants: output drift, invalid catalog paths or duplicate identities, and
failure reporting. Real CLI verification supplies the installation evidence.

The README explains authoring, regeneration, local marketplace registration,
install and uninstall commands for each CLI, and how to add a plugin. Document
Git repository installation as a supported consumer route, but do not claim a
remote deployment has been tested: this checkout currently has no Git remote.

AGENTS.md holds shared contributor guidance. CLAUDE.md refers to that guidance
instead of maintaining a second copy. Generated output is clearly identified.

## Verification and cleanup

Run verification against the available Codex and Claude Code executables, record
their actual versions, and use temporary isolated configuration directories
through the tools' supported environment settings. Do not overwrite HOME or
copy credentials. Verify that all test installation state stays in these
profiles before using them for mutations.

For each host, the verifier must:

1. Validate manifests with native validation where available and run the
   generator's consistency checks.
2. Register this repository using the native marketplace CLI.
3. List marketplaces and assert the expected marketplace is present.
4. List available plugins and assert both stub identities are discoverable.
5. Install both stubs through the marketplace, asserting command success and
   installed/enabled state from native structured output where available.
6. Inspect installed plugin content or native component inventory and confirm
   each expected skill is present; compare copied skill content with its source
   when the host exposes an installed cache path.
7. Uninstall both stubs and assert neither remains installed. A plugin may
   remain in an available catalog or host cache according to that host's normal
   uninstall behavior; distinguish this from installed state.
8. Remove the test marketplace and assert registration is gone.

Cleanup also runs on failure without hiding the original error. Capture command
exit codes and relevant output in a verification report. Missing executables,
unsupported isolation, or failed assertions fail verification and must be
reported, never silently skipped. Save a concise human-readable record in
`docs/verification.md`, including versions, stages passed, and any limitations.

Successful lifecycle verification concerns CLI marketplace discovery,
installation, skill packaging, and uninstall behavior. Model-driven skill
execution and graphical desktop marketplace behavior are outside the acceptance
criteria and must not be claimed as tested.

## Alternatives considered

Separate host plugin trees make installation straightforward but duplicate
content and encourage drift. Hand-maintained dual manifests share content but
repeat metadata. Shared plugin folders with generated host metadata provide
direct installation and a single authoring workflow, matching the requested
maximal reuse.

## Reference formats

- [OpenAI plugin packaging and marketplace documentation](https://developers.openai.com/plugins/build/plugins)
- [Claude Code marketplace documentation](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code manifest reference](https://code.claude.com/docs/en/plugins-reference)

These formats evolve. Native CLI lifecycle checks, rather than manifest shape
alone, determine compatibility with the installed versions.
