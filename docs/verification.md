# Native lifecycle verification

Last verified on October 6, 2026 (report timestamp 2026-10-06T15:01:41Z, after the
final review fixes), using the real locally installed CLIs, with a fresh temporary
configuration profile for each host.

| Check | Codex 0.160.1 | Claude Code 2.1.290 |
| --- | --- | --- |
| Generated metadata matches portable sources | Passed | Passed |
| Native manifest and skill validation | Discovery/install accepted manifests | `claude plugin validate` passed |
| Empty isolated profile confirmed | Passed | Passed |
| Repository marketplace registered and listed | Passed | Passed |
| All three plugins discoverable | Passed | Passed |
| All three plugins installed and enabled | Passed | Passed |
| Installed portable manifests match source | Passed | Passed |
| Every committed plugin file matches its installed copy byte for byte; no extra files | Passed | Passed |
| Native skill component inventory | Installed files inspected | `plugin details` lists `hello`, `about`, and `audit-report` |
| All three plugins uninstalled; absent from installed list | Passed | Passed |
| Marketplace removed; absent from marketplace list | Passed | Passed |

The marketplace is `rickdiculousli-plugins`. The tested plugins are
`visual-audit`, `hello-world`, and `repository-info` (all `@rickdiculousli-plugins`,
version `0.1.0`). File comparison covers every file tracked by Git in each plugin
directory except generated host manifests, so `visual-audit`'s renderer scripts,
templates, and references are included. Both hosts installed identical skill content:

| Skill | SHA-256 |
| --- | --- |
| `audit-report` | `d014925c6443c961b72529866b868ad1ece1146b62b97322a2076027a193117b` |
| `hello` | `bf6ab583d5cd7ee791d8f3f551fc04c120b180bcd6e99effc4e52f3f3d6bd07d` |
| `about` | `764ab249ba09f27a645b7fe4b60ab60e33b7b569bc189d158f7e139a46ec1434` |

## Visual audit renderer

The renderer's 128 unit tests passed on Python 3.14.7 and 3.10.22 (via
`uv run --no-project --python 3.10`). Example, 300-step, and all-pass reports were
rendered and inspected in the T3 Code preview browser at 1280 px and 390 px wide, in light
and dark schemes, including filter buttons and anchor navigation into collapsed
groups. Behaviour with JavaScript disabled was checked structurally (filters exist only
when the script runs; anchors and disclosure are native HTML), not by disabling
JavaScript in a browser. The Impeccable design detector's contrast findings were
false positives from measuring dark-scheme colours on the light background; contrast
was computed per scheme instead.

## Reproduce

From the repository root, with Python 3.10+ and both CLIs on PATH:

```sh
python3 scripts/sync_marketplaces.py --check
python3 -m unittest discover -s tests -v
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```

The verifier exits nonzero on failure. Its optional JSON report records versions,
each command and exit code, native output, installation paths, skill hashes,
passed stages, and any primary or cleanup errors. Reports include absolute local
paths and are intended as local test evidence.

## Isolation and scope

The verifier creates new temporary directories, sets `CODEX_HOME` and
`CODEX_SQLITE_HOME` for Codex and `CLAUDE_CONFIG_DIR` for Claude Code, and runs
commands from a temporary working directory. It confirms empty state and checks
that marketplace metadata and installed content land in the temporary profile.
No credentials are copied. Test marketplaces and plugins are removed;
temporary profiles are deleted afterward. No permanent user installation is
requested by the verifier.

Uninstallation is checked using native installed-plugin lists. Available catalog
entries or host-retained cache directories do not count as installed plugins.

This verifies local CLI marketplaces, installation, skill packaging, and removal.
It does not claim graphical marketplace testing, model-driven execution of any
skill (including an agent producing a real audit report), or Git remote deployment. The repository had no configured remote
during verification. The external skill-creator validator needed unavailable
PyYAML; native Claude skill validation and installed-content checks were used
instead, without adding a dependency.

## Delegation host capabilities (step 0)

Date: 2026-10-09. `codex --version`: `codex-cli 0.162.1`. `claude --version`:
`2.1.296 (Claude Code)`. Evidence labels: `checked` (observed running),
`cited` (source or documentation reading), `asserted`.

### Codex: can a plugin ship agent definitions? No (`cited`)

Source: `openai/codex` at tag `rust-v0.162.1` (commit
`7a078f6bb4ce0dc2a81408b334ce52979d92c603`).

- `codex-rs/core-plugins/src/manifest.rs` lines 50-73: `RawPluginManifest` has
  `name`, `version`, `description`, `keywords`, `skills`, `mcp_servers`, `apps`,
  `hooks`, `interface` and `extensions`. There is no `agents` field.
- `codex-rs/plugin/src/manifest.rs` lines 19-25: `PluginManifestPaths` holds
  `skills`, `onboarding_skill`, `mcp_servers`, `apps` and `hooks` only.
- `codex-rs/core-plugins/src/agent_plugin_manifest.rs` lines 18-29: the
  Agent Plugins root manifest allows only `$schema`, `name`, `version`,
  `description`, `author`, `homepage`, `repository`, `license`, `keywords` and
  `extensions`; other fields are ignored with a warning.
- `codex-rs/agent-roles/src/loader.rs` lines 29-38 and 75-80: custom agent
  roles are read from each config layer's `[agents]` table and from
  `<config_folder>/agents/*.toml`, found recursively by
  `agent-roles/src/discovery.rs` (`collect_agent_role_files`, `.toml` only).
  Config layers are user and project config folders (`~/.codex`, `.codex`);
  the plugin loader does not contribute a layer.
- `agents/openai.yaml` is skill UI metadata: `ext/skills/src/loader/mod.rs`
  defines `SKILLS_METADATA_DIR = "agents"`, relative to a skill directory. It is
  not a subagent definition.
- Docs agree: [plugins](https://developers.openai.com/plugins/build/plugins)
  lists skills, MCP, apps, hooks and assets, and
  [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
  puts custom agents in `~/.codex/agents/` or `.codex/agents/` without any
  plugin mention.

Nothing other than skills, MCP, apps, hooks, interface metadata and assets is
loaded from a plugin.

### Codex: do spawn-time model and effort work? Yes (`checked`)

Each run: `codex exec --sandbox read-only --skip-git-repo-check "<prompt>"`
from a fresh `/tmp` directory, normal auth, no `-c` flags, no persistent config
changes. The parent ran `gpt-6.1-sol` at `medium` (the profile default).

Run A (`/tmp/deleg-step0-a`), prompt asked for model `gpt-6-luna`, effort `low`.
Parent `01a123ae-5669-70c2-9e88-d2e39182b603`, child
`01a123ae-7244-70f0-aed6-cf9fbbaa13e4`
(`~/.codex/sessions/2026/10/09/rollout-2026-10-09T19-39-57-...`).

- Parent `turn_context`: `"model": "gpt-6.1-sol"`, `"effort": "medium"`.
- Parent tool call: `"name": "spawn_agent"`, `"namespace": "collaboration"`,
  `"arguments"`: `{"task_name":"reply_ok","fork_turns":"none","model":"gpt-6-luna","reasoning_effort":"low","message":"<opaque>"}`.
- Child `session_meta`: `"parent_thread_id": "01a123ae-5669-70c2-9e88-d2e39182b603"`,
  `"source": {"subagent": {"thread_spawn": {"parent_thread_id": "01a123ae-5669-70c2-9e88-d2e39182b603", "depth": 1, "agent_path": "/root/reply_ok", "agent_nickname": "Aristotle", "agent_role": null}}}`.
- Child `turn_context`: `"model": "gpt-6-luna"`, `"effort": "low"`.

Run B (`/tmp/deleg-step0-b`), model `gpt-6.1-sol`, effort `low`. Parent
`01a123ae-ae92-7061-bb39-810f7f64638f`, child
`01a123ae-bedf-7ea1-86e4-4fba055203c3`.

- Parent `spawn_agent` arguments (message omitted):
  `{"task_name":"reply_ok","fork_turns":"none","model":"gpt-6.1-sol","reasoning_effort":"low"}`.
- Child `session_meta`: `"parent_thread_id": "01a123ae-ae92-7061-bb39-810f7f64638f"`,
  `"agent_path": "/root/reply_ok"`, `"agent_role": null`.
- Child `turn_context`: `"model": "gpt-6.1-sol"`, `"effort": "low"`.

Spawn parameter names, exact: `task_name`, `fork_turns`, `model`,
`reasoning_effort`, `message`. Related tools named in the developer prompt:
`followup_task`, `send_message`. In both runs the agent replied `ok` and the
child's recorded model and effort matched the request. The agent's `message`
field is stored encrypted in the rollout, so the child's task text was not
inspected. These runs show the explicit spawn value overriding the parent's
`medium` effort (Run A also its model); they do not test the `[agents]` defaults.

### Decision: `routes.codex = spawn`

Step 1 found no supported plugin path for agent definitions, and Step 2 shows
spawn-time model and effort take effect, so the Codex skill spawns its default
subagent with the tier's model and effort (`model` and `reasoning_effort`
arguments). Rick approved this route on 2026-10-09. The `same-model` fallback
is not needed on 0.162.1.

### Claude Code (`cited`; live check is Task 8)

The [subagent docs](https://code.claude.com/docs/en/sub-agents) say plugin
agents honour the `model` and `effort` frontmatter fields. `hooks`,
`mcpServers`, `permissionMode` and `initialPrompt` are ignored for plugin
agents. A per-invocation `model` overrides frontmatter, and
`CLAUDE_CODE_EFFORT_LEVEL` overrides effort. No Claude Code subagent was run
for this step.

## Format references

- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)
- [Codex profile environment variables](https://developers.openai.com/codex/environment-variables)
- [Claude Code marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code profile environment variables](https://code.claude.com/docs/en/env-vars)
