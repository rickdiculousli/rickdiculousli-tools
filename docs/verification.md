# Native lifecycle verification

Last verified on October 10, 2026 (report timestamp 2026-10-11T01:27:25Z, UTC),
using the real locally installed CLIs, with a fresh temporary configuration
profile for each host. Evidence labels: `checked` (observed running), `cited`
(source or documentation reading), `asserted`.

| Check | Codex 0.162.1 | Claude Code 2.1.296 |
| --- | --- | --- |
| Generated metadata matches portable sources | Passed | Passed |
| Native manifest and skill validation | Discovery/install accepted manifests | `claude plugin validate` passed |
| Empty isolated profile confirmed | Passed | Passed |
| Repository marketplace registered and listed | Passed | Passed |
| All six plugins discoverable | Passed | Passed |
| All six plugins installed and enabled | Passed | Passed |
| Installed portable manifests match source | Passed | Passed |
| Every committed plugin file matches its installed copy byte for byte; no extra files | Passed | Passed |
| Native component inventory | Installed files inspected | `plugin details` lists each plugin's skills and, for `delegation`, agents `execute` and `routine` |
| All six plugins uninstalled; absent from installed list | Passed | Passed |
| Marketplace removed; absent from marketplace list | Passed | Passed |

All results above are `checked`. The unit suite (210 tests) passed on Python 3.14
and on 3.10 (`uv run --no-project --python 3.10 -m unittest discover -s tests`).

The marketplace is `rickdiculousli-tools`. The tested plugins are
`visual-audit`, `hello-world`, `repository-info`, `delegation`, `quota` and
`yt-transcript` (all `@rickdiculousli-tools`, `delegation` at version `0.5.0`, the others at `0.1.0`). File comparison covers every file tracked by Git in each plugin
directory except generated host manifests, so the bundled `quota.py` and `yt_transcript.py`, `visual-audit`'s renderer scripts,
templates, and references are included. Both hosts installed identical skill content:

| Skill | SHA-256 |
| --- | --- |
| `audit-report` | `d014925c6443c961b72529866b868ad1ece1146b62b97322a2076027a193117b` |
| `hello` | `bf6ab583d5cd7ee791d8f3f551fc04c120b180bcd6e99effc4e52f3f3d6bd07d` |
| `about` | `764ab249ba09f27a645b7fe4b60ab60e33b7b569bc189d158f7e139a46ec1434` |
| `delegation` | `4699be37857b43c68df06e61110147fa373e30ba54c0b1f008ce3dd9b7874ec0` |
| `setup` (delegation) | `e8bed6693c3e9252548e016ca7a30a23645df62bd64bd88e28c68ef07dea2990` |
| `quota` | `dcd9ed6fa96ca51c21c45ecfb3c5af6c857da31f0795f6bb550fb01ffa7c2a05` |
| `yt-transcript` | `6c9d671ae62b4deca2a924573bd2e10bcd0d0c05c9cbc6810dc2f71a0417c7a6` |

All seven hashes (each skill's `SKILL.md`) match the 2026-10-11T02:45Z lifecycle report
(`/tmp/plugin-verification.json`), re-run after delegation 0.5.0: the `requires=<platform>`
validator attribute (`run` refuses other hosts with exit 2 and no ledger entry; the brief
footer names validators this host can't run), and a `host` record (platform, machine,
node) on every result. Both hosts' installed files matched the source. Earlier, in 0.4.0: validator attributes `cheap`, `timeout=<seconds>`
and `lock=<name>`; `## Locks` with slots, a wait limit and the
`DELEGATION_LOCK_<NAME>` override (flock on slot files under `/tmp`, keyed by
git's common directory, shared by every worktree), holder details,
`check.py exec --lock` and `check.py locks`; full validator output kept in `.delegation/logs/<id>/<n>.log`
and printed on failure, the cheap-first order in the brief footer, and the tier
rule allowing builds, focused tests and diagnostics as `[asserted]`. Earlier, in
0.3.0: the shared-context rule, the `Settled` brief
field, read-bound tier instructions, `check.py brief` (appending the fixed brief
parts and checking brief and context hashes) with the one-line task `open`
prints, `brief --with-instructions` (so Codex and the Claude fallback pass one line
too), and the stderr note from an empty `query`. These are covered by the unit
suite (210 tests). Neither the `setup` skill nor the 0.3.0, 0.4.0 and 0.5.0 changes
have been exercised by a model yet.

## Quota and YouTube transcript scripts

Date: 2026-10-10 (Mac) and 2026-10-11 UTC (linux). Evidence: `checked`.

- `quota`: 5 unit tests, ported from coordinator, mock Claude's usage page and
  Codex's `account/rateLimits/read`; they pass on 3.14 and 3.10. Live
  `uv run --script plugins/quota/skills/quota/scripts/quota.py` printed both providers
  and exited 0 on the Mac (macOS, Apple Silicon) and on linux (Ubuntu 26.04, x86_64),
  appending to `~/.local/state/rickdiculousli-tools/quota/usage.jsonl` on each.
- `yt-transcript`, on both boxes: `dQw4w9WgXcQ` with `--whisper never` wrote a
  transcript with engine `human captions`; `jNQXAC9IVRw` with `--whisper always`
  wrote a timestamped transcript with engine `mlx_whisper mlx-community/whisper-large-v3-turbo`
  on the Mac and `faster_whisper large-v3-turbo` on linux (19 s wall, 1.7 GB peak RSS).
  The linux run first failed in `av.open()` (`metadata_errors`) with PyAV 19.0.1 and
  faster-whisper 1.2.1, so the script pins `av<19` off macOS; 16, 17 and 18 decode.
  The linux runs used a copy of the script in `/tmp` before the repository had a remote.

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
uv run --no-project --python 3.10 -m unittest discover -s tests -v
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
It does not claim graphical marketplace testing, routing quality of `delegation` (that is for a pilot), model-driven execution of any
skill (including an agent producing a real audit report; the one-agent check below
is the only model run), or Git remote deployment. The repository had no configured remote
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

### Claude Code (`cited`; live result under Task 8)

The [subagent docs](https://code.claude.com/docs/en/sub-agents) say plugin
agents honour the `model` and `effort` frontmatter fields. `hooks`,
`mcpServers`, `permissionMode` and `initialPrompt` are ignored for plugin
agents. A per-invocation `model` overrides frontmatter, and
`CLAUDE_CODE_EFFORT_LEVEL` overrides effort. No Claude Code subagent was run
for this step.

## Delegation live checks (Task 8)

Date: 2026-10-10.

### (a) Claude: model of `delegation:routine` (`checked`)

Command, from the repository root, normal auth, no installs or config writes:
`claude --plugin-dir plugins/delegation -p "Use the delegation:routine agent to run 'echo ok' and report back its output in one line."`
(`--plugin-dir` exists in 2.1.296). The agent replied `ok`. The subagent
transcript `~/.claude/projects/<repo>/e7ca5816-8d08-413c-bd3c-a5b12e101be0/subagents/agent-afdd51028a4b4be8d.jsonl`
has `agent-afdd51028a4b4be8d.meta.json` with `"agentType":"delegation:routine"`.
Its assistant messages carry `"model":"claude-haiku-5-5"` (3 of 3).

Effort: the transcript lines carry a session-level `"effort":"medium"` with
`"advisorModel":"claude-opus-5-5"`, but that field is not tied to the agent's
frontmatter, so the subagent's own effort is not observable; documented
behaviour (`cited`) applies. The agent also could not write the brief file or run
`check.py` in that headless run, so no ledger entry was made.

### Codex sandbox check (`checked`)

Date: 2026-10-10. `codex-cli 0.162.1`. No model call. Codex's `:workspace` sandbox
makes `.agents/` read-only, so the state directory is `.delegation/`; the overlay
stays at `.agents/delegation.md` (read only). In a disposable git repo under `/tmp`
(one committed file, one untracked file, overlay `## Validators\nok: true`), each
subcommand ran as
`codex sandbox -P :workspace -C <repo> -- python3 -I <repo-checkout>/plugins/delegation/skills/delegation/scripts/check.py <subcommand>`:
`tree`, `open --delegation d1 --tier routine --brief .delegation/briefs/d1.md`,
`run ok --delegation d1`, `query --delegation d1 --tree current --json`,
`pending --json` and `close --delegation d1 --outcome done`. All exited 0
(`run` printed `d1#1 PASS exit=0`). The brief file itself was written outside the
sandbox. The temporary repo was removed afterwards.

Re-run 2026-10-10 for delegation 0.3.0, same method: `open` (recording a
`.delegation/context/` hash), `brief`, `brief --with-instructions`, `run`,
`query` and `close` exited 0 inside the sandbox; `brief` exited 2 after the
context file changed.

Re-run 2026-10-10 for delegation 0.4.0, same method, with overlay
`ok [cheap]: true` and `heavy [lock=mem, timeout=30]: echo heavy; exit 1`:
`lint`, `open`, `run ok`, `brief` and `close` exited 0; `run heavy` exited 1,
printed the log path, and the ledger recorded `lock: mem`, `timeout_s: 30.0` and
the log file with the full output. A first attempt with the lock under
`.git/delegation-locks` exited 2 (`Operation not permitted`: the sandbox keeps
`.git` read-only), which is why locks live under `/tmp`.

Then, with `## Locks` (`mem: slots=1, wait=5`), `lint`, `locks`, `open`,
`run heavy`, `exec --lock mem --timeout 5 -- echo via-exec` and `close` exited 0
inside the sandbox. Across the boundary: while a sandboxed
`exec --lock mem -- sleep 2` held the slot, an unsandboxed `check.py locks`
showed it as held by that delegation, and an unsandboxed `exec --lock mem`
printed the holder, waited about a second, then ran.

### (b) Codex: effort when `reasoning_effort` is omitted (`checked`)

Performed 2026-10-10 with Rick's approval, near the end of the Codex quota. Each run:
`codex exec --sandbox read-only --skip-git-repo-check -m gpt-6-luna -c model_reasoning_effort=high "<prompt>"`
from a fresh `/tmp` directory (the `-c` override applies to that run only). The
parent ran at `high` so that an inherited effort would be distinguishable from the
model default. No `[agents]` defaults are set in the profile.

- Run 1: `spawn_agent` with `task_name` `routine-probe` was rejected:
  `agent_name must use only lowercase letters, digits, and underscores`. No child
  started (6,125 tokens).
- Run 2: `spawn_agent` arguments
  `{"task_name":"routine_probe","fork_turns":"none","model":"gpt-6-luna"}` (no
  `reasoning_effort`). Parent `turn_context`: `"model": "gpt-6-luna"`, `"effort": "high"`.
  Child (`parent_thread_id` `01a123ce-db7c-7a40-9df8-346c2f7a182a`) `turn_context`:
  `"model": "gpt-6-luna"`, `"effort": "medium"`. The child replied `ok` (3,066 tokens).

So an omitted `reasoning_effort` gives the model's default (`medium` for
`gpt-6-luna`), not the parent's effort; `tiers.json` stays as is. `task_name` must be
lowercase letters, digits and underscores; the generated `hosts.md` says so.

## Format references

- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)
- [Codex profile environment variables](https://developers.openai.com/codex/environment-variables)
- [Claude Code marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code profile environment variables](https://code.claude.com/docs/en/env-vars)
