# Native lifecycle verification

2026-10-15: `delegation` and `long-horizon` are retired (moved to `retired/`, removed from the
marketplace; buildermesh replaces them). The rows and hashes below that name them are the record of
the last verification they were part of, not a current claim; the marketplace now ships five plugins.

2026-10-27: the five owned skills reshaped with skill-shaper: each description now says what the skill
does before when to use it, and the script skills' bodies drop general know-how (`quota`'s field glossary,
which its output already labels, and the path-quoting and interpreter notes). Versions: `hello-world`
0.1.1, `repository-info` 0.1.1, `quota` 0.1.3, `visual-audit` 0.1.1, `yt-transcript` 0.1.3.
`verify_lifecycle.py` passed on codex-cli 0.163.0 and Claude Code 2.1.311 on the Mac; the unit suite (165
tests) passed. Skill hashes: `hello` `8eb9eb71a093a3aabf3a342c62cc1e85d8fa94b9b0cb2c23b511d3e6de63bc9f`,
`about` `ba75f2fae4e237844f6be1e7c0d00442bcda1bd0f1a3f9078fc43d39d5d42315`, `quota`
`b110264610dbfbcc2dd52c170f9b94b1f3c59f72acebbdcda89d393894bf3845`, `audit-report`
`b8c2d20b21e03689f1a096155d16dab1fbc20f3a0c09e4489822ceff20d52144`, `yt-transcript`
`5e0f1982e7dcca16ce93a031d38cf29f591c9ce3c1df2d934bfd37d9555a4fdd`. Routing was compared in two fresh
agents given only the descriptions and 14 requests (7 that should load a skill, 7 near misses): old and new
routed alike except "Say hello", which only the old `hello` description claimed (`checked`). `quota.py`'s
output was read live to confirm it labels its fields (`checked`). No model has run the reshaped skills from
the installed plugin.

2026-10-27: `skill-shaper` 0.1.0 added (the marketplace ships seven plugins). `verify_lifecycle.py`
passed on codex-cli 0.163.0 and Claude Code 2.1.311 on the Mac: all seven plugins discovered,
installed, byte-compared against the source (including `skill-shaper`'s `UPSTREAM` and `update.sh`)
and uninstalled. The copied files: `SKILL.md` `94250efbea8a202795c97973852e5372b44f7fc1807f9ad4a652addef746037c`,
`references/placement.md` `c198b4f4f2b8d55f6c0ac5df91c29cdc33cafc695068763fe634d0a047fe8729`. `update.sh --check` exited 0 at the
pin, overment/skills `8c6ea24` (`checked`). No model has run this skill from the plugin yet.

2026-10-15: `method` 0.1.0 added (the marketplace ships six plugins). `verify_lifecycle.py` passed on
codex-cli 0.162.1 and Claude Code 2.1.300 on the Linux host: all six plugins discovered, installed,
byte-compared against the source (including `method`'s `UPSTREAM`, `update.sh` and the skills'
`agents/openai.yaml`) and uninstalled. Both hosts installed identical `method` skills: `grill-me`
`caaf8b8de1684f96e26b28f3c29189db5c89cce4b73e1c93d86164f66ef88637`, `grilling`
`befdff1e27a1dfe2a294d5871169ac1afe16d983911daa4f32627514a48c1e15`, `writing-plans`
`a6c67c1900064347c2a329990dd3c555657c51c3ec53b259a08aa01a2c26139a`. `update.sh --check` exited 0
at the pins; `--check --to obra/superpowers=v6.2.0` printed the `writing-plans` diff and exited 1;
`--to` that tag on a scratch copy copied it, rewrote the pin, and a following `--check` exited 0
(`checked`). A bad `--to` ref for one repo exits nonzero with every skill and `UPSTREAM` unchanged,
and a missing skill directory diffs as all new (`checked`). No model has run these skills from the plugin yet.

Baseline verified on October 10, 2026 (report timestamp 2026-10-11T01:27:25Z, UTC),
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

Date: 2026-10-10 (Mac) and 2026-10-11 UTC (Linux). Evidence: `checked`.

- `quota`: 5 unit tests, ported from an earlier private script, mock Claude's usage page and
  Codex's `account/rateLimits/read`; they pass on 3.14 and 3.10. Live
  `uv run --script plugins/quota/skills/quota/scripts/quota.py` printed both providers
  and exited 0 on the Mac (macOS, Apple Silicon) and on a Linux host (Ubuntu 26.04, x86_64),
  appending to `~/.local/state/rickdiculousli-tools/quota/usage.jsonl` on each.
- `yt-transcript`, on both boxes: `dQw4w9WgXcQ` with `--whisper never` wrote a
  transcript with engine `human captions`; `jNQXAC9IVRw` with `--whisper always`
  wrote a timestamped transcript with engine `mlx_whisper mlx-community/whisper-large-v3-turbo`
  on the Mac and `faster_whisper large-v3-turbo` on the Linux host (19 s wall, 1.7 GB peak RSS).
  The Linux run first failed in `av.open()` (`metadata_errors`) with PyAV 19.0.1 and
  faster-whisper 1.2.1, so the script pins `av<19` off macOS; 16, 17 and 18 decode.
  The Linux runs used a copy of the script in `/tmp` before the repository had a remote.

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

Performed 2026-10-10 with the owner's approval, near the end of the Codex quota. Each run:
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

## Delegation 0.6.0: role reuse and safety fields

Date: 2026-10-11. Final lifecycle report timestamp: 2026-10-11T16:30:46Z.
Evidence: `checked` unless otherwise stated.

- `python3 scripts/sync_marketplaces.py --check`: generated metadata current.
  Shared tier/coordination instructions were changed in `tiers.json` and regenerated,
  including `hosts.md`, tier instructions, agent definitions and host manifests.
- `python3 -m unittest discover -s tests -v`: 223 tests passed on Python 3.14.7.
- `UV_CACHE_DIR=/tmp/delegation-uv-cache uv run --offline --no-project --python 3.10 -m unittest discover -s tests -v`:
  the same 223 tests passed on Python 3.10.22. A first attempt with the default
  uv cache was sandbox-denied; the writable temporary cache resolved it.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  Codex 0.162.1 and Claude Code 2.1.296 passed all disposable-profile stages,
  including install, byte-for-byte source comparison, uninstall and marketplace
  removal. Delegation version 0.6.0 was installed; normal profiles were untouched.
- The new CLI regression cases cover optional overlay sections, malformed roles,
  count and supplied-byte reuse caps, ancestor continuation counters, missing/open
  prior delegations, unchanged tier, hashed briefs and runbooks, contained runbook
  paths, writer exclusion, default safety footers, host restriction injection,
  human markers, and caller-attributed command success/failure/timeout evidence.
  Unicode caps and command evidence instructions were reproduced failing before
  their review fixes. Existing cross-worktree lock tests still pass.
- Live peer probe in the T3 Code Codex harness: parent spawned `/root/peer_receiver`
  and `/root/peer_sender`. Sender called `collaboration.send_message` directly to
  receiver with `peer_request_20261011`; receiver replied directly with
  `peer_ack_20261011`, which sender observed. Both stop handbacks reached the judge.
  No parent relay or file writes occurred. This checks active sibling messaging;
  stopped-agent resumption and other Codex harnesses were not tested. The current
  tool contract says `send_message` does not start an idle turn; use judge
  `followup_task` for that case.
- Claude peer messaging is `cited` from a session report from a consuming repository:
  SendMessage accepts a supplied peer id, stopped peers resume, replies reach the
  sender, ids are absent from ListAgents, and the judge receives stop handbacks.
  This session did not repeat that Claude model test.

The byte cap counts accumulated supplied brief/context file bytes, including
repeated context reads; it excludes command output and does not measure model
context. Prefer a use-count cap. Host restrictions and human notifications are
agent instructions, not filesystem enforcement. A recorded command result has
`validator: null` and cannot establish registered-validator acceptance.

No end-to-end model-driven setup survey, reusable-role runbook refresh, or native
game permission-prompt workflow was run. Those remain suitable for a repository
pilot; the live model check above is limited to peer communication. No publication,
tag, push or normal-profile installation was performed.

## Delegation 0.6.1: Windows locking implementation (unverified)

Applied native Windows byte locking with `msvcrt.locking`, retaining POSIX
`fcntl.flock`, through a shared standard-library helper. Ledger readers now
serialize with appends; internal reads under an existing lock avoid nested
acquisition. Windows resource slots use separate holder-metadata files and the
system temporary directory. Nonblocking acquisition uses explicit retry loops
and the configured slot wait limit.

Tests, compilation checks, metadata consistency checks, lifecycle verification,
and live Windows execution were deliberately not run, as requested by the user.
Generated manifests and marketplace metadata were regenerated from their sources.
The earlier 0.6.0 passing results do not verify this change.

## Sharing and portability updates (2026-10-11)

Versions: `quota` 0.1.1, `yt-transcript` 0.1.1, `delegation` 0.6.2.
Checked on Apple Silicon macOS:

- `python3 scripts/sync_marketplaces.py --check`: passed.
- Full standard-library unit suite: 235 tests passed on Python 3.14.7 and
  Python 3.10.22 (`UV_CACHE_DIR=/tmp/portability-uv-cache uv run --offline
  --no-project --python 3.10 -m unittest discover -s tests -v`).
- Native lifecycle verifier: passed on Codex 0.162.1 and Claude Code 2.1.296,
  using disposable profiles for all six plugins, including byte comparison,
  uninstall, and marketplace cleanup. No cleanup errors. Report:
  `/tmp/plugin-verification.json`. Normal profiles were untouched.
- Quota PEP 723 invocation via `uv run --offline --script .../quota.py --help`:
  passed without provider requests.
- Both scripts' `--help` commands ran directly under Python 3.10.22, without
  provider requests, video downloads, or Whisper dependency imports.
- Regression cases demonstrated failures before fixes: custom Claude profile
  ignored, explicit credential file bypassed, OAuth environment token ignored,
  selected Keychain failure falling back to the default account, invalid UTF-8
  credentials raising an uncaught error, Intel Mac selecting no Whisper backend,
  family aliases rejected by the marketplace generator, and UTC `Z` reset
  timestamps rejected by Python 3.10's date parser. These cases now pass.

The dependency-selection test evaluates the script's metadata for Apple Silicon,
Intel macOS, and Linux x86_64/aarch64. It does not install those dependencies or
run Whisper on those platforms. Both scripts now request Python 3.10+; transcript
dependency resolution and transcription on that minimum interpreter were not run.
The earlier live Mac/Ubuntu observations remain historical evidence, not live
checks of these new versions. No live quota reads, remote installation, or
model-driven skill/delegation execution was performed for this update.

Windows was deliberately not verified, at the user's request. The first real
Windows run will determine any remaining host-specific issues. Passing macOS
tests also exercise the current POSIX delegation implementation; they do not
verify the Windows locking branch added in 0.6.1. No Intel Mac execution was run.

## Normal-profile rollout (2026-10-11)

At the user's explicit request, portability commit `778f56c` was pushed to
`origin/main` and applied to the local Apple Silicon Mac and a Linux host (Ubuntu x86_64).
Both machines used Claude Code 2.1.296 and Codex 0.162.1 with their existing
local-checkout marketplaces and normal user profiles. The clean the Linux host checkout
was fast-forwarded to the pushed commit.

Claude's native plugin update command refreshed the three changed plugins;
Codex's native remove/add commands refreshed their caches. On both hosts on both
machines, the final plugin lists showed `delegation` 0.6.2, `quota` 0.1.1, and
`yt-transcript` 0.1.1 enabled. All tracked portable files matched the checkout
byte for byte: 19 for delegation and 3 each for quota and yt-transcript, excluding
generated host manifests. Unrelated plugins were left alone. The local suite of
235 tests passed again before committing. Existing model sessions were not
restarted; new sessions are needed to load refreshed plugin content. No live
provider reads, transcription, model-driven execution, or Windows checks were
performed during this rollout.

## Long-horizon 0.1.0 (2026-10-11)

Checked on Linux x86_64 with Python 3.14.4 and Python 3.10.22. Published content
adds long-horizon 0.1.0 and updates delegation composition guidance to 0.6.3;
quota remains 0.1.1.

- `python3 scripts/sync_marketplaces.py --check`: passed.
- `python3 -m unittest discover -s tests -v`: 297 tests passed on Python 3.14.4.
- `uv run --no-project --python 3.10 -m unittest discover -s tests -v`:
  297 tests passed on Python 3.10.22.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  passed at 2026-10-11T21:27:20Z on Codex 0.162.1 and Claude Code 2.1.296.
  All seven plugins installed into disposable profiles, matched their portable
  sources, exposed expected inventory, uninstalled, and removed their marketplace.
  Both hosts reported no cleanup errors. Normal profiles were untouched.
- The installed-copy test ran CLI evidence preparation from a plugin path with
  spaces without writing bytecode, locks or runtime state into that installation.
- Disposable Git repositories, linked worktrees and local bare remotes exercised
  durable evidence recovery, archive gates, rejected push/retry and sync recovery.
  Real POSIX process contention and mocked POSIX/Windows locking paths passed.
- [Behavioral pilots](long-horizon-pilots.md): 30 final host/scenario cells passed
  manual inspection across 35 actual model runs, plus one corrected fixture
  preflight failure. [Curated results](long-horizon-pilot-results.json) retain all
  attempts, content/trace hashes and the corrected initially misleading passes.

Native Windows contention/atomic replacement, GUI behavior, live quota savings
and real hosted remote closure remain untested. Local fixture remote observations
are not proof of current server state. Adoption in a consuming repository was not applied; it remains
a separately authorized consuming-repository follow-on.


## XDG follow-up: delegation 0.7.0 and long-horizon 0.2.0 (2026-10-11–12)

Checked on Linux x86_64. Host validation was Codex only, as requested; normal
plugin profiles and consuming-repository state were untouched.

- Generated metadata check passed. Sources, both generated host manifests and
  marketplace versions were regenerated with `scripts/sync_marketplaces.py`.
- Full standard-library suite: **334 tests passed** on Python **3.14.4** and
  **3.10.22**. Commands: `python3 -m unittest discover -s tests -v` and
  `uv run --offline --no-project --python 3.10 -m unittest discover -s tests -v`.
- `python3 scripts/verify_lifecycle.py --hosts codex --report /tmp/plugin-verification.json`
  passed at **2026-10-12T00:53:28.343436+00:00**, with **Codex 0.162.1**. All seven plugins
  were discovered, installed into a disposable profile, compared byte for byte,
  uninstalled, and their marketplace removed without cleanup errors. Installed
  delegation exercised path discovery, an XDG brief, native resource locking,
  stable validator PASS, unchanged acceptance tree and close. Installed
  long-horizon prepared evidence and created a scoped identity-bearing cache
  draft. All fixture XDG paths were outside checkouts and installed plugins.
- Disposable Git repositories and linked worktrees cover path normalization,
  default/custom/empty/relative XDG values, unwritable roots without fallback,
  root/slot inode preservation, real POSIX holder/waiter/crash contention, PID
  reuse and unknown owners, collection during active work, injected-clock weekly
  cadence and seven-/30-day retention, stale Git registrations, recreated paths,
  context confinement and pins, unchanged real Git indexes/object databases,
  and hash stability while bookkeeping changes.
- Migration tests cover preview, byte-identical historical events/log lookup,
  receipts and identical no-op, busy old/new locks and other worktrees, open-work
  refusal, changed legacy sources, destination conflicts, and interrupted staging
  recovery/refusal. Unknown legacy/staging files remain for review. Migration
  never rewrites old tree hashes, result outcomes or evidence hashes.
- Six actual Codex model runs used temporary profiles and Git fixtures, observed
  model **gpt-6.1-sol**. The three final scenario outcomes were reviewed: new
  linked-worktree setup used `state draft`, preserved source/test bytes and ran no
  validators; reconstruction recovered committed scoped acceptance without old
  state and left milestone/goal acceptance open; composition preserved registered
  evidence through an owned commit and deletion of the disposable XDG ledger.
  The corrected composition run additionally proves a working empty current-tree
  query and refusal specifically for the missing registered result. No workers,
  normal-profile changes or network Git integration ran in these pilots.
  [Curated pilot records](xdg-pilot-results.json) retain report/trace/source-content
  hashes, the two intermediate runs, and one rejected repeat despite its original
  automated PASS: changing the identity implementation mid-run blocked cleanup.
  The runner assertions were strengthened, regression-tested and the scenario
  rerun successfully with stable source. Pilot content hashes identify pre-commit
  builds; they do not claim every run observed every subsequent helper change.
- Native Codex `:workspace` sandbox checks used disposable profiles/repos/XDG
  homes. Configured XDG roots under `/tmp` worked. Roots outside `/tmp` under the
  disposable home-cache fixture were denied, exiting 2 with the actionable shared
  XDG-root diagnostic. Hosts must grant both external XDG roots write permission;
  no per-command root substitution or checkout/temporary fallback is provided.

Explicit legacy migration requires a coordinated stop/restart of all repository
checker sessions with one shared XDG root. Native locks and Linux process probes
refuse detected activity; no implementation can prove an arbitrary old binary
will never be launched again. Historical files remain for explicit review.
Linux identities use `statx` creation time where supported to prevent rapid inode
reuse; older identity records may require explicit recovery rather than silently
inheriting local bookkeeping. Long-horizon preserves durable Git evidence and
quarantines old generations on mutation. Filesystems without creation identity
provide only device/inode checks.

Native Windows/macOS execution, Claude lifecycle/model behavior for these new
versions, GUI behavior and hosted remote closure were **not tested**. Mocked
Windows locking cases are unit evidence only. No normal-profile upgrade, legacy
user-state migration, release tag or hosted PR was performed.


## Windows native defaults: delegation 0.7.1 and long-horizon 0.2.1 (2026-10-12)

Both plugins now honor absolute XDG overrides and otherwise default on Windows
to `%LOCALAPPDATA%/rickdiculousli-tools/<plugin>/state/` and the sibling `cache/`.
Missing/empty/relative LOCALAPPDATA uses Python's home `AppData/Local` directory.
POSIX defaults are unchanged. There are no existing Windows users/installations;
no Windows migration is shipped. Delegation migration is POSIX-only, with no
Windows legacy temporary-lock location. Contributor guidance, the addendum,
README and shared skill references describe the native defaults.

Checked on Linux x86_64:

- The six new platform-selection regressions failed before implementation for
  the expected missing Windows defaults/migration restriction, then passed.
  Cases cover both plugins, separate state/cache roots, explicit XDG precedence,
  empty/relative XDG values, missing/invalid LOCALAPPDATA, spaces, read-only path
  resolution, unchanged POSIX defaults and refusal of Windows migration.
- **340 tests passed** on Python **3.14.4** and **3.10.22**, using the full unittest
  suite and `uv run --offline --no-project --python 3.10` respectively.
- `python3 scripts/sync_marketplaces.py --check`: passed after regeneration.
- `python3 scripts/verify_lifecycle.py --hosts codex --report /tmp/localappdata-plugin-verification.json`:
  passed at **2026-10-12T01:07:12.761529+00:00**, on **Codex 0.162.1**, including all seven
  disposable-profile plugin installs, source comparisons, installed state-script
  checks, uninstall and marketplace removal. No cleanup errors; normal profiles
  were untouched.
- A fresh-context Codex reference check first recovered the old home-directory
  defaults from the unchanged docs. After correction, rereading the same shared
  references recovered exact LocalAppData paths, override precedence and no
  Windows migration. This checks reference interpretation, not Windows runtime.

Platform branches were simulated on Linux. No native Windows/macOS execution,
Claude lifecycle, or additional full setup/continuation model pilot was performed
for this update. Earlier pilot results remain historical evidence.

## Long-horizon readiness cache correction — 0.3.0 (2026-10-11)

Startup supports `readiness: "cache:readiness.json"`, resolved under the keyed
worktree cache's `readiness/` directory, separate from drafts. Read-only
`lh.py paths --root PATH --json` returns state/cache/readiness paths and cache
identity metadata without creating files. Producers persist that identity under
the shared lifecycle lock; cache reads reject missing/malformed/mismatched
identity. Legacy readiness paths remain usable with a warning from lint.

Verification on this Mac:

- `python3 scripts/sync_marketplaces.py --check`: passed; source version and
  generated Claude marketplace/host manifests are 0.3.0. Catalog identity/order
  and the Codex marketplace shape did not need changes.
- `TMPDIR=/private/tmp python3 -m unittest discover -s tests -v`: **348 tests
  passed**. Final log: `/tmp/long-horizon-tests-final.log`. Eight readiness tests
  cover resolution, worktree isolation, no-creation discovery, traversal,
  symlink/Windows-normalisation escapes, missing/stale/checkout/identity handling,
  legacy lint, readiness-only GC grace, unknown protection and mocked Windows
  LocalAppData/explicit XDG resolution. These are not native Windows results.
- The first run with macOS's default `/var/folders/...` TMPDIR failed 12
  assertions because existing fixtures compared noncanonical `/var` paths with
  canonical `/private/var` paths. All failures were reproduced on unchanged base
  commit `9ddf9ba`: delegation state's `test_migration_open_and_busy_legacy_lock_refused`
  and `test_xdg_default_empty_relative_and_custom`; long-horizon overlay's
  `test_linked_worktree_and_subdirectory`; Windows defaults'
  `test_empty_relative_xdg_values_use_windows_defaults` (two subcases),
  `test_explicit_xdg_overrides_still_win_on_windows`,
  `test_missing_invalid_localappdata_uses_home_appdata_local` (three subcases),
  `test_posix_defaults_ignore_localappdata` (two subcases), and
  `test_windows_native_defaults_for_both_plugins`. Baseline logs:
  `/tmp/lh-baseline-tests.log`, `/tmp/lh-baseline-other.log`,
  `/tmp/lh-baseline-overlay.log`. Canonical TMPDIR avoids this existing fixture
  issue; no unrelated test or delegation production code was changed.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  passed on **Codex 0.162.1** and **Claude Code 2.1.296** using disposable profiles;
  source comparison, install, inventory, runtime checks, uninstall and marketplace
  cleanup passed, with no cleanup errors.
- Independent review identified cache identity reuse on readiness reads; this
  was fixed and verified with a failing-then-passing regression. Follow-up review
  found no blocking issues.

No consuming repository was changed. No GUI or model execution check is claimed.
Normal-profile installation results are recorded separately below after release.

### Requested normal-profile installation — Mac and Linux

Implementation commit `62eb357` was installed through the native plugin commands.
Both machines use local-checkout `rickdiculousli-tools` marketplaces. the Linux host's clean
checkout was fast-forwarded from `9ddf9ba` using a Git bundle transferred over
SSH; no push, remote fetch from origin, or consuming-repository migration occurred.

| Machine | Host CLI | Installed long-horizon | Enabled | Source comparison |
| --- | --- | --- | --- | --- |
| Mac | Claude Code 2.1.296 | 0.3.0 | yes | all 31 files match |
| Mac | Codex 0.162.1 | 0.3.0 | yes | all 31 files match |
| Linux | Claude Code 2.1.296 | 0.3.0 | yes | all 31 files match |
| Linux | Codex 0.162.1 | 0.3.0 | yes | all 31 files match |

On each machine, `claude plugin marketplace update rickdiculousli-tools` and
`claude plugin install long-horizon@rickdiculousli-tools` were run. Since the
plugin was already installed from a local folder, install reported in-place
loading and recommended update; `claude plugin update long-horizon@rickdiculousli-tools`
then recorded 0.2.1 → 0.3.0. `codex plugin add long-horizon@rickdiculousli-tools --json`
installed 0.3.0 on both machines. Codex marketplace upgrade on the Mac reported
that the local marketplace is not configured as a Git marketplace; no Git
snapshot refresh is required for local sources.

Installed `lh.py paths --help` passed on every host. Cache copies are under each
user's `.claude/plugins/cache/rickdiculousli-tools/long-horizon/0.3.0` and
`.codex/plugins/cache/rickdiculousli-tools/long-horizon/0.3.0`. Claude additionally
loads the declared local source folder. Restart/reload Claude plugins and start
a new Codex session to consume updated skill instructions. Installation and CLI
verification do not claim that running model sessions reloaded their skills.

## Delegation repository material — 0.7.2 (2026-10-11)

The overlay remains `.agents/delegation.md`. Optional tracked role sources and
approved rote scripts default to `.agents/delegation/runbooks/` and
`.agents/delegation/scripts/`. `open --role` and continuations validate tracked
sources and materialize them atomically into external context. Any open brief's
context pin, including equivalent paths and in-state symlinks, prevents changed
bytes from replacing its runbook. Final-use refresh edits the authorized tracked
source; subsequent use rematerializes after all pins close. Legacy state-only
roles remain supported. Layout warnings are nonfatal, so general tools can stay
in their existing location and remain independent of the checker.

The supported lock interface is the existing public `exec --lock NAME
--timeout SECONDS -- CMD` CLI, with one foreground wrapper per native process,
declared `slots=N`, and one shared XDG state root across repository worktrees.
Private `delegation_check` modules are not an import API. Migration instructions
cover moving reviewed material, updating overlay paths, removing startup copying
and private imports, and rerunning validators; no consuming repository was edited.

Verification on this Apple Silicon Mac:

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed.
  Source and generated host manifests/Claude marketplace declare 0.7.2.
- `TMPDIR=/private/tmp python3 -m unittest discover -s tests -v`: **362 tests
  passed**, 90.893 seconds. Log: `/private/tmp/delegation-full-tests-final.log`.
  Canonical TMPDIR avoids the previously documented macOS fixture path issue.
  The 25 role tests cover tracked-source copying/sharing/refresh, pinning by
  non-role briefs and path/symlink aliases, first and refreshed brief loads,
  unsafe/untracked sources, literal Git pathspecs, symlink destinations, context
  Extra-input fingerprints, legacy roles, and nonfatal layout warnings including
  quoted scripts, bare scripts and `uv run --script`. Added regressions were
  observed failing before their fixes. Existing real-process tests cover shared
  locks across worktrees, multiple slots, waiting, exit codes and timeouts.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  passed at **2026-10-12T02:40:36.104413+00:00**, on **Codex 0.162.1** and
  **Claude Code 2.1.296**. All seven plugins were installed in disposable
  profiles, compared to sources, inspected, uninstalled, and their marketplace
  removed without cleanup errors. Normal profiles were untouched by these tests.
- Independent review found brief context alias handling; failing-then-passing
  regressions verified the corrections for normalized paths and in-state
  symlinks. Fresh-context comparison of old and new skill instructions recovered
  the intended script home, checker-owned copying, tracked-source final refresh,
  optional standalone tools, and six separate foreground lock wrappers.

No native Windows, GUI, or sustained host role/model execution pilot was
performed for this update. Installation results are recorded below separately.

### Requested delegation reinstall — Mac and Linux

Release commit `c5a4d33` was installed through native plugin commands in both
machines' normal user profiles. Their existing local-checkout marketplaces were
updated; delegation alone was uninstalled and reinstalled with Claude's
`--scope user`, and removed/re-added with Codex. the Linux host's clean plugin checkout was
fast-forwarded from `20fe98e` through a Git bundle transferred over SSH. No push,
origin fetch, or consuming-repository migration occurred.

| Machine | Host CLI | Delegation | Enabled | Portable source comparison |
| --- | --- | --- | --- | --- |
| Mac | Claude Code 2.1.296 | 0.7.2 | yes | all 20 files match |
| Mac | Codex 0.162.1 | 0.7.2 | yes | all 20 files match |
| Linux | Claude Code 2.1.296 | 0.7.2 | yes | all 20 files match |
| Linux | Codex 0.162.1 | 0.7.2 | yes | all 20 files match |

Installed `check.py open --help` and `exec --help` passed on all four copies.
On the Linux host, `sync_marketplaces.py --check` passed and all **25 role tests passed**
in 9.424 seconds under native Linux. Install logs are
`/private/tmp/delegation-mac-install.log` and the Linux host's
`/tmp/delegation-linux-install.log`; Linux role-test log:
`/tmp/delegation-roles-linux.log`.

Cache copies are in each user's `.claude/plugins/cache/rickdiculousli-tools/delegation/0.7.2`
and `.codex/plugins/cache/rickdiculousli-tools/delegation/0.7.2`. Claude also loads
the declared local source folder. Reload Claude plugins and start a new Codex
session to consume the updated instructions; the reinstall does not establish
that running model sessions reloaded skills.

### Delegation 0.7.3 — exec/run signal forwarding

`execute` (used by `exec` and `run`) now forwards SIGTERM, SIGINT and SIGHUP on
POSIX to the wrapped command's process group, kills the group after a one-second
grace, and exits with 128 + signal, releasing the held lock. This lets an
orchestrator (game capture) cancel or time out a game wrapped in
`exec --lock games` without orphaning it in its separate session.

- Two new `test_delegation_run` tests (a child that exits on SIGTERM and one that
  ignores it) failed against 0.7.2 and pass with 0.7.3; all 25 run tests pass.
- Full suite on the Mac: 364 tests, 12 failures, the same 12 as the unchanged
  tree (`/var` vs `/private/var` temp-path comparisons in Windows-default, XDG
  and linked-worktree tests); none involve this change.
- `sync_marketplaces.py --check` current; `verify_lifecycle.py` PASS for
  codex-cli 0.162.1 and Claude Code 2.1.296 in disposable profiles.

### Requested push and delegation 0.7.3 reinstall — Mac and Linux

All five pending commits through `1fb03f7` were pushed to `origin/main`; the Linux host's
clean checkout was fast-forwarded from the remote. Delegation was uninstalled
and reinstalled through Claude Code (`--scope user`) and Codex native commands
in both machines' normal profiles after refreshing the local marketplace.

- Mac and Linux, both Claude Code 2.1.296 and Codex 0.162.1: delegation **0.7.3**,
  long-horizon **0.3.0**, quota **0.1.1**, yt-transcript **0.1.1** are enabled.
  Every tracked portable plugin file in all 16 installed copies matches its
  checkout byte for byte. Delegation was the only outdated installed plugin.
- Fresh Mac checks: generated metadata current; all **25 delegation run tests**
  passed. Native isolated lifecycle verification passed on both hosts; evidence
  is `/private/tmp/plugins-prepush-verification.json`.
- Fresh full Linux suite on the Linux host: **364 tests passed** in 59.325 seconds;
  log `/tmp/plugins-release-tests.log`. This avoids the previously documented
  Mac temporary-path comparison failures.

Restart Claude Code and start a new Codex session to load the updated skills.
Existing running model sessions were not tested for hot reloading.

## Delegation 0.8.0 — work labels, pattern log and scratch (2026-10-12)

`open --kind <label>` (with `--new-kind "<description>"` to register) labels each
delegation in a repository-wide registry (`<state>/<repo-key>/kinds.json`); every
open and close is appended to `<repo-key>/patterns.jsonl`, shared by all worktrees.
Unknown labels are refused before opening, with the closest existing labels.
Each brief is fingerprinted by tier, writes, input/write path shapes and named
validators; a shape match under another label prints a note. `kinds` lists,
merges, renames and marks labels; `patterns` reports candidates (three or more
uses, no role, no decision) and unlabeled shapes. The optional overlay
`## Authoring` section (`roles|scripts: ask|allowed`, both defaulting to
`allowed`) is linted and printed by `patterns`; setup asks whether to restrict
either to `ask`. Briefs name a per-delegation scratch directory under the worktree
cache, and both tier instructions now allow writing scratch and prefer a
throwaway script to repeated hand edits. Collection folds pattern lines older
than 180 days into per-kind archived counts and removes scratch files untouched
for 30 days. The skill gained "Labels and patterns" and "Growing roles and
scripts" procedures: by default add a role or script for repeated work and
report it (or propose first where `## Authoring` says `ask`), without rerunning
setup.

Verification on Linux (Ubuntu, Python 3.14.4):

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  source and generated manifests and the Claude marketplace declare 0.8.0.
- `python3 -m unittest discover -s tests`: **379 tests passed** in 67.3 seconds,
  including 15 new `test_delegation_patterns` tests (refusal before opening,
  registration and reuse, label rules, sharing across a linked worktree, shape
  notes, merge/rename aliasing, candidates/marks/roles, unlabeled shapes, role
  and continuation kinds, `--since` and retention folding, scratch in briefs and
  its expiry, tier instructions, `## Authoring` parsing and lint).
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  PASS at **2026-10-12T17:10:34.236472+00:00** on **codex-cli 0.162.1** and
  **Claude Code 2.1.296**, in disposable profiles. New files had to be staged
  first: the installed-copy comparison uses tracked files.

No host model session was run against the new procedures, and no normal-profile
reinstall was performed.

### Requested push and delegation 0.8.0 reinstall — Linux only

Commit `430e70e` was pushed to `origin/main`. On the Linux host, the local-checkout
marketplace was refreshed and delegation was uninstalled and reinstalled in the
normal user profiles: Claude Code with `--scope user`, Codex with
`plugin remove`/`plugin add` (Codex's `marketplace upgrade` reports a local
folder marketplace as not Git-backed, which is expected).

| Machine | Host CLI | Delegation | Portable source comparison |
| --- | --- | --- | --- |
| Linux | Claude Code 2.1.296 | 0.8.0 | all 24 files match |
| Linux | Codex 0.162.1 | 0.8.0 | all 24 files match |

Installed `check.py open --help` (showing `--kind` and `--new-kind`),
`kinds --help` and `patterns --help` ran from both copies. The Mac was not
touched; its owner is updating it separately. Restart Claude Code and start a
new Codex session to load the updated skills.

### Long-horizon 0.4.0 and delegation 0.9.0 — session feedback

Changes from a long-horizon/delegation session's feedback. Long-horizon: lint
warns about `Done when` without a colon and milestones with tasks but no criteria
(naming the task a trailing criterion attached to), and `lint --fix` repairs both;
the gate treats whitespace, `.,;:` and that move as formatting, not a criteria
change, and check tokens no longer swallow trailing punctuation. Status lists
uncommitted pending evidence (`pending_evidence`, `pending: true` on acceptance)
and the handoff's `lines`/`budget`. `evidence record --write-proposed` writes the
record's own detail file; `--trailers-file` appends and deduplicates.
`evidence rerecord <id>` carries an unchanged observation onto revised criteria
and removes a superseded pending proposal. `closure manifest --base <commit>`
builds the batch manifest and ID. Reviewed observations require
`--reviewer-kind human|agent`; agents review only checks declaring
`"reviewer": "any"`. The gate's pending-delegation finding names each open
delegation and its exact `close` command. Delegation: `check.py run <name>
--judge` records a `judge-*` delegation that opens and closes with the run; the
validator attribute `paths=<glob>|<glob>` feeds the new `check.py suggest`.

Verification on macOS (Darwin 25.5.0, Python 3.14.7):

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  manifests declare long-horizon 0.4.0 and delegation 0.9.0.
- `python3 -m unittest discover -s tests`: 396 tests ran in 124.2 seconds;
  384 passed and 12 failed. All 12 also fail on an export of the preceding
  commit on this Mac: they compare macOS temporary paths (`/private/var/...`
  versus `/var/...`) in `test_delegation_state`, `test_long_horizon_overlay`
  and `test_windows_state_defaults`. The 17 new tests (`test_delegation_judge`,
  `test_long_horizon_feedback`, one in `test_long_horizon_delegation`) pass.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  PASS at **2026-10-12T18:15:38.044248+00:00** on **codex-cli 0.162.1** and
  **Claude Code 2.1.296**, in disposable profiles, with new files staged.

No host model session was run against the new procedures, and no normal-profile
reinstall was performed.

## 2026-10-12: delegation 0.9.1, test isolation and parallel runner

`tree_hash` copied the real index with `shutil.copyfile`, which gives the copy a
fresh mtime. Git treats an entry as possibly changed only when its mtime is not older
than the index's, so a same-size edit made in the same second as the last index write
was hashed as unchanged once that second had passed. A probe that forces this timing
missed the edit 6 of 6 times with `copyfile` and 0 of 6 with `shutil.copy2`, which
keeps the mtime; delegation 0.9.1 uses `copy2`, with a regression test.

Tests: the shared support modules point `tempfile` at the resolved temp root, fixing
the 12 macOS `/var` vs `/private/var` failures recorded above.
`test_exec_holds_lock_and_passes_exit_code` holds its lock until the test releases it
instead of for `sleep 1`, which a loaded machine could outlast, and
`test_existing_profile_refused_without_invoking_cli` no longer needs `claude` on PATH.
`scripts/run_tests.py` runs the suite in parallel, one process per available CPU and
up to 8 tests per process.

Verification on macOS (Darwin 25.5.0, Python 3.14.7):

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  manifests declare delegation 0.9.1.
- `python3 scripts/run_tests.py`: 397 tests passed in 44.7 seconds (6 jobs);
  with `-j 16 --chunk 2` under heavier contention, passed in 55.6 seconds.
  Serial `python3 -m unittest discover -s tests`: passed.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  PASS at **2026-10-12T19:14:10.538612+00:00** on **codex-cli 0.162.1** and **Claude Code 2.1.296**, in
  disposable profiles.

## 2026-10-12: delegation 0.10.0 and long-horizon 0.5.0, migrate skills

Each plugin gains a `migrate` skill, designed in
[the migrate skills spec](superpowers/specs/2026-10-12-migrate-skills-design.md).
Lint knows only the current contract and reports layout drift; overlays carry
`## Version`, and `check.py lint` / `lh.py status` warn `version-mismatch` when its
major.minor is older than the installed plugin or missing. Pre-XDG handling is
removed: delegation's `state migrate`, the `.delegation/` ledger guard, migration
receipts and `.delegation/context/` references, and long-horizon's `legacy-state`
finding. `state:context/` role runbooks, readiness paths without `cache:` and
milestones without `# Goal:` are no longer read and lint reports them; the
long-horizon `## Schema` heading is ignored and reported.

Verification on Linux 7.0.0-38-generic, Python 3.14.4:

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  manifests declare delegation 0.10.0 and long-horizon 0.5.0.
- `python3 scripts/run_tests.py`: 407 tests passed in 14.3 seconds. Serial
  `python3 -m unittest discover -s tests`: 407 passed in 79.2 seconds. New
  `test_delegation_contract` and `test_long_horizon_contract` cover version
  status, layout findings and installed-version discovery.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  PASS at **2026-10-12T21:09:46.253353+00:00** on **codex-cli 0.162.1** and
  **Claude Code 2.1.296**, in disposable profiles, with new files marked
  intent-to-add.

No host model session ran either migrate skill, no consuming repository was
migrated, and no normal-profile reinstall was performed.

## Public-release scrub — delegation 0.10.1, quota 0.1.2, yt-transcript 0.1.2

Date: 2026-10-12. Evidence: `checked`.

Before the repository goes public, references to the owner's private
repositories, machines and directories were made generic: script docstrings no
longer cite private source repositories, the Codex app-server client name is
`rickdiculousli-tools-quota`, the delegation worked example is `game-decomp`,
and verification notes name hosts by platform. Behaviour is unchanged.

Verification on macOS 26.5.2 (Apple Silicon), Python 3.14.7:

- `python3 scripts/sync_marketplaces.py --check`: passed.
- `python3 scripts/run_tests.py`: 407 tests passed in 43.7 seconds.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  PASS at **2026-10-12T22:08:13.429482+00:00** on **codex-cli 0.162.1** and **Claude Code 2.1.296**, in
  disposable profiles.

## Closure manifests and wrapped criteria — long-horizon 0.5.1

Date: 2026-10-12. Evidence: `checked`.

Two bugs found while using the plugin in a consuming repository are fixed:

- `closure manifest` wrote `manifest-<batch>.json` into the worktree's
  `snapshots/` directory, and `evidence prepare` then failed with
  `KeyError: 'attempt'` while scanning it. Manifests are now written to a sibling
  `manifests/<batch>.json`. The snapshot scan only reads records named by their
  own SHA-256 ID that contain an attempt. Manifests and closure archives that older
  versions left under `snapshots/` are therefore ignored instead of crashing, and
  are not moved: the 30-day expiry for unreferenced snapshots still collects them.
  `closure record --manifest` takes the path the manifest command reports, so old
  and new locations both work. `state gc` and `state clear` accept the
  `manifests/` directory and expire unreferenced manifests after 30 days.
- `lint --fix` moved only the first line of a wrapped trailing `Done when`
  criterion. A criterion is now a paragraph: the `Done when` line plus the
  non-blank lines directly after it, up to a blank line, heading, task or
  metadata key line. The fix moves the paragraph intact, with its blank-line
  separator, and the gate's formatting-only check compares the full paragraph.
  Continuation lines are now part of the criterion text. Evidence recorded
  against a wrapped criterion whose later lines used to be ignored may show stale
  once, and needs `evidence rerecord`.

Verification on Linux 7.0.0-38-generic, Python 3.14.4:

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  manifests declare long-horizon 0.5.1.
- `python3 scripts/run_tests.py`: 410 tests passed in 14.6 seconds. The new tests
  in `test_long_horizon_feedback` cover `evidence prepare` after a completed
  closure batch, including legacy files under `snapshots/`; one-, two- and
  three-line criteria moves; and a policy change on a continuation line. Each
  new test failed against the 0.5.0 code.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  PASS at **2026-10-12T22:28:45.601116+00:00** on **codex-cli 0.162.1** and **Claude Code 2.1.296**, in
  disposable profiles.

No consuming repository's state was changed or re-recorded.

## Line-ending conversion — long-horizon 0.5.2

Date: 2026-10-12. Evidence: `checked`.

With Git eol conversion (`core.autocrlf=true`, common on Windows), checkouts hold
CRLF files while commits store LF blobs. Two hashes compared the wrong forms:

- Scope snapshots hashed raw worktree bytes with `git hash-object --stdin`, so CRLF
  and LF checkouts of one commit had different scopes and evidence went stale
  across machines. Regular files are now hashed with `--path`, which applies the
  checkout's eol and clean rules. Where no conversion applies the object IDs are
  unchanged. Repositories that do normalize (for example `* text=auto` with
  CRLF files in the worktree) see pending evidence go stale once.
- The `closure record` commit step compared worktree-byte manifest digests with
  the stored blob, so it always rejected eol-converted files. It now also accepts
  the blob in checked-out form (`git cat-file --filters`). Manifest and batch IDs
  are unchanged, and different contents still fail.

Delegation was checked and needs no change: its tree hash uses `git add -A` and
`write-tree`, which already normalize. Goals, handoff and overlay parsing, and
`lint --fix`, were checked with LF, CRLF, CR-only and no final newline.

Verification on Linux 7.0.0-38-generic, Python 3.14.4:

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  manifests declare long-horizon 0.5.2.
- `python3 scripts/run_tests.py`: 412 tests passed in 14.4 seconds. The new
  `test_scope_is_the_same_for_crlf_and_lf_checkouts` and
  `test_commit_step_accepts_eol_converted_checkout` use `core.autocrlf=true` and
  failed against 0.5.1.
- `python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json`:
  PASS at **2026-10-12T22:33:15.063802+00:00** on **codex-cli 0.162.1** and
  **Claude Code 2.1.296**, in disposable profiles.

Not run on a Windows host; eol conversion was exercised through Git on Linux.

## Lanes support — delegation 0.11.0

Date: 2026-10-13. Evidence: `checked`.

Delegation gains what a parallel-lane run needs, with overlays that lack the new
sections behaving as before:

- `## Locks` accepts one `provider: "<command>"` line and a `ttl=` lock
  attribute. With a provider, `run` (validators with `lock=`) and `exec --lock`
  hold a lease through the provider's `acquire <name> --ttl N` / `renew <key>
  --ttl N` / `release <key>` subcommands instead of a native slot; the ledger
  result records it under `lease`. The contract (exit codes, stdout, polling,
  renewal period, holder environment) is in the overlay reference. A lock
  named `provider` is now a lint problem.
- `suggest --with-dependents` adds the validators of units that depend on a
  changed unit, from a `## Deps` map or a `command:` printing JSON.
- `## Rules` lines are injected into every brief; tier instructions name them.
- `open --lane <name>` tags the open event, `pending --json`, the brief header
  and the pattern log; `patterns`/`kinds --json` list `lanes` per kind only
  when some open carried one.

Verification on Linux 7.0.0-38-generic, Python 3.14.4:

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  manifests declare delegation 0.11.0.
- `python3 scripts/run_tests.py`: 438 tests passed. The new
  `test_delegation_lanes` (26 tests) drives the lease path against
  `tests/fake_lease_provider.py`, a directory-backed provider implementing the
  documented contract, covering acquisition, renewal, a lost lease, busy
  polling, provider errors, `exec` and judge runs, dependents (overlay map and
  command, transitive), rules injection, lane tags, and unchanged output for
  overlays and opens without the new features.
- `python3 scripts/verify_lifecycle.py --report
  ~/.cache/rickdiculousli-tools-scratch/delegation/plugin-verification.json`:
  PASS on **codex-cli 0.162.1** and **Claude Code 2.1.296**, in disposable
  profiles.
- One adversarial review by a fresh-context model session found: `lanes` added
  to every `patterns --json` entry (now only when non-empty), a lock named
  `provider` silently hijacked (now a lint problem), non-`DelegationError`
  exceptions escaping the renew thread (now `OSError` is a provider error), a
  wall-clock timing assertion (now polls the provider log), and the missing
  verification entry; plus holder identity for the provider, renew timeouts,
  the brief footer's slot count under a provider, literal pathspecs for
  dependents and contract wording, all applied.

No real lease provider exists yet; the Go `lane lease` command is to be written
against the documented contract. No model-driven session exercised the new
sections, and Windows was not run.

## The lanes contract — long-horizon 0.6.0

Date: 2026-10-13. Evidence: `checked` unless marked.

Long-horizon can run one goal as parallel lanes. The overlay's optional `## Lanes`
section turns it on only when `config` names a lanes TOML; a `## Lanes` heading
without `config`, or no section at all, changes nothing. Goals gain `Lane:` and
`After:` task metadata and the goal's `Parallel: lanes, <who>, YYYY-MM-DD`
approval. `status --lane <name> --json` selects the lane's first open task whose
dependencies are done, walking the active goal's unfinished milestones in order;
without `--lane` a lanes-mode status is the judge view (`mode: judge`) with a
`lanes` object (per-lane open/eligible/blocked/done and the critical path). New
findings: `lanes-config-missing`, `lanes-config-invalid`, `lane-missing`,
`lane-unknown`, `after-missing`, `after-cycle`, `parallel-approval-missing`,
`lanes-config-changed`, `mac-task-on-non-native-lane`, `lane-file-missing`,
`lane-file-template`, `handoff-lanes-line`, `handoff-lane-link`.

Evidence: `committed` reads every message in one `git log -z` call and caches each
trailer-carrying commit's validated records in a repository-wide index under the
XDG cache (`<repo-key>/evidence/<commit>.json`), written only under lanes mode or
by `--commit-in`; weekly `state gc` prunes entries whose commit object is gone and
applies the seven-day window to an index whose repository is gone. `evidence
record --commit-in <dir>` commits exactly the detail file with its trailer in a
checkout of the same repository through a private index file, moving only that
checkout's HEAD by compare-and-swap; the pending copy is cleaned when `<dir>` is
the `--root` worktree. The lanes TOML is read with `tomllib` on 3.11+ and a
stdlib subset parser (`toml_subset.py`) on 3.10; its tests compare both.

Verification on Linux 7.0.0-38-generic:

- `python3 scripts/sync_marketplaces.py --check` and `git diff --check`: passed;
  manifests declare long-horizon 0.6.0.
- `python3 scripts/run_tests.py` (Python 3.14.4): 468 tests passed, after rebasing onto delegation 0.11.0. The new
  `tests/test_long_horizon_lanes.py` (24 tests: overlay section, no-change
  without `config` including wrapped criteria, repeated trailers and
  `log.showSignature`, lane selection, judge view, every finding, config fallback
  parsing, scaffold, `--commit-in` from a landing worktree and in the `--root`
  worktree with staged unrelated work, index tamper/stale safety, GC) and
  `tests/test_long_horizon_toml.py` (6 tests) are included.
- `uv run --no-project --python 3.10 python -m unittest discover -s tests`:
  468 tests passed, one skipped (the tomllib comparison, absent on 3.10, so
  `load_text` took the fallback path).
- `python3 scripts/verify_lifecycle.py --report
  ~/.cache/rickdiculousli-tools-scratch/long-horizon/plugin-verification.json`:
  PASS at **2026-10-13T17:38:28.349389+00:00** on **codex-cli 0.162.1** and
  **Claude Code 2.1.296**, in disposable profiles.

An adversarial review of the diff found and the change fixed: a stray commit from a
smoke test; `--commit-in` committing a record whose `--log` file was absent from
the commit (now a persistent route is required and the dangling commit is validated
before HEAD moves); `git log` output mixed with `log.showSignature` text (now
`--no-show-signature`); `Lane:`/`After:`/`Parallel:` ending wrapped criteria on
every node (now only on the node kind they belong to); repeated trailers reported
as corrupt (now skipped as before); TOML dates serialising differently per reader
(now rejected by both); invalid commits cached forever (now never cached); and
day-granular `lanes-config-changed` (now relative to the commit that recorded the
`Parallel:` line). Accepted as additive: selected tasks in JSON gain `lane`,
`after` and `lane_line` fields.

Not performed: no model session has run a lanes-mode `resume`, `checkpoint`,
`setup` scaffold or `migrate` yet; the pipeline daemon that calls `status --lane`
and `--commit-in` is not part of this repository. Not run on Windows or macOS.

## Lanes purely opt-in — long-horizon 0.6.1 and delegation 0.11.1

Date: 2026-10-13. Evidence: `checked` unless marked.

For a repository that uses none of the lanes features, nothing about lanes,
lease providers, dependents or project rules reaches its files or the text its
agent reads every session. `long-horizon:migrate` no longer adds a `## Lanes`
stub: an absent section already means lanes are off, an existing comment-only
heading is left alone, and a repository whose only finding is `version-mismatch`
gets exactly the `## Version` tag. Every SKILL.md of both plugins (resume,
checkpoint, setup, migrate; delegation, setup) carries at most one conditional
pointer to the lanes reference or to the overlay reference's new "Parallel runs"
section, which absorbed the lane-session, lander, setup-scaffolding, `--lane`,
`--with-dependents`, `## Deps`, `## Rules` and lease text; the always-read
long-horizon references (overlay grammar, goals format, evidence, cheatsheet) are
down to a one-line pointer each. Setup skills offer those sections only when the
user asks for parallel or cross-machine runs or the repo already has them. The
tier instruction "Obey its Rules" stays. One code leak was found and fixed:
`status`/`lint --json` task objects carried `lane: null` and `after: []` outside
lanes mode; they are now omitted.

Golden tests pin the lanes-free surface. `tests/test_long_horizon_baseline.py`
and `tests/test_delegation_baseline.py` build one deterministic fixture
repository per plugin (fixed content, author and commit dates, isolated XDG
roots), run `status`/`lint`/`gate`/`closure verify` and `lint`/`suggest`/`open`/
`brief`/`run`/`query`/`kinds`/`patterns`/`locks`/`paths`/`pending`/`tree`/`close`
in text and JSON, normalize only run-specific bytes (temp base, checkout path,
XDG keys, timestamps, durations, host names, the installed version inside the
version finding) and compare byte for byte with goldens generated from the
0.5.2 and 0.10.1 code (`--regenerate <plugins-root>` on commit b31b433).
`tests/test_long_horizon_contract.py` adds the lanes-free migration test: only
warning findings, an empty `lint --fix` diff, and after tagging `## Version` an
overlay equal to the original plus that section, with no `## Lanes`.

Verification on Linux 7.0.0-38-generic, run through delegation (sonnet execute
tier wrote the tests, haiku routine tier ran the checks; results asserted by the
tier and re-run by the judge):

- `python3 scripts/sync_marketplaces.py --check`: passed; manifests declare
  long-horizon 0.6.1 and delegation 0.11.1.
- `python3 scripts/run_tests.py`: 471 tests passed, before and after the review
  fixes below.
- `python3 scripts/verify_lifecycle.py --report
  ~/.cache/rickdiculousli-tools-scratch/plugin-verification-0.6.1.json`:
  PASS at **2026-10-13T18:42:55Z** on **codex-cli 0.162.1** and **Claude Code
  2.1.296**, in disposable profiles; both hosts observed long-horizon 0.6.1 and
  delegation 0.11.1.

An adversarial review by a fresh-context subagent on the most capable model
(reading every SKILL.md and every unconditionally referenced file as a novice's
agent would, and running the CLIs against lanes-free fixtures) found nine
items, all fixed: the delegation overlay reference's heading table and parsing
rules still carried the full `provider:`/`ttl`, `## Deps` and `## Rules` detail
outside "Parallel runs" (moved there, the table now has one "Parallel runs"
pointer row); `state.md` kept a seven-line evidence-index paragraph (now one
line, the detail lives in the lanes reference); the README said migrate carried
a lanes pointer (it carries none); the verification draft had a placeholder;
the migrate skill named `## Lanes` three times (tightened to one sentence); the
evidence reference pointer introduced the "lander" role (removed); the return
format and patterns references each kept an unconditional `## Rules`/`--lane`
clause (deleted); and the setup cheatsheet still advertised a lanes row
(deleted). It found the six SKILL.md files, the interview and templates, the
tier instructions and every lanes-free CLI output clean. After the fixes the
three checks were rerun (`plugin-verification-0.6.1-final.json`, lifecycle PASS
on the same host versions): the only failure was the new migration test's
expected string, stale after the migrate wording was tightened; it was updated
and `scripts/run_tests.py` passed again (471 tests) along with
`sync_marketplaces.py --check` and `git diff --check`.

## Lifecycle verifier scratch root (2026-10-13)

`scripts/verify_lifecycle.py` created its disposable profiles with
`tempfile.TemporaryDirectory()`, so under the system temp directory. On a Linux
host whose `/tmp` is a small per-user tmpfs that fails under load, and Codex
warns that it refuses helper binaries there. The profiles now go under
`${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/verification/` (empty or
relative `XDG_CACHE_HOME` counts as unset; Windows uses `LOCALAPPDATA`), or
under `--scratch <dir>`. The documented `--report` path moved there too. Not a
plugin content change, so no version bump.

On the Linux host (Ubuntu 26.04, Python 3.14): `sync_marketplaces.py --check`
current; `scripts/run_tests.py` 476 tests OK (5 new in `ScratchRootTests`);
`verify_lifecycle.py --report ~/.cache/rickdiculousli-tools/verification/plugin-verification.json`
PASS on codex-cli 0.162.1 and Claude Code 2.1.296, with no
`/tmp/rickdiculousli-plugin-verification-*` directory created and no Codex
helper-binary warning; the profiles were removed afterwards.

## Goal closure without the end stall — long-horizon 0.7.0 and delegation 0.11.2

Date: 2026-10-14 (UTC). Evidence: `checked` unless marked.

Case study: a consuming repository closed a nine-milestone goal under 0.6.1 and
0.11.1. Its gaps (no goal criteria, an archive the gate rejected) surfaced only
after the user said "sign off" and took several more question rounds. The
archive could never validate: four milestones closed before Checks existed, one
was proved in prose, and four more cited valid records in the goals file's
`task=<id>` form, which the gate did not read. The JSON fence was written by
hand. Recording a second validator from the same judge run failed because the
first record's detail file changed the checker tree, as did a review-note edit.
`--result 1` was rejected, `evidence prepare --json` printed about 200 KB, and an
inline review note was refused without saying what was expected.

What changed is in the README's 0.7.0 and 0.11.2 notes. `check.py` and its tree
hash are unchanged. Long-horizon now matches a registered result's tree to the
snapshot's tree instead of the current tree. Record still requires the check's
scope to be unchanged since prepare, so the claim keeps exact-tree proof for
its scope.

Replay on a disposable clone of the consuming repository with isolated XDG roots
(the repository itself was not modified):

- At the sign-off commit, `archive check` lists five gaps at once: milestones
  1, 2, 6 and 7 have no named checks, and 8 cites no recorded PASS. Before this
  change the gate stopped at the first gap.
- Adding a six-line `legacy_acceptance` block makes the archive validate.
  `archive check` is clean, `gate --base HEAD~1` passes on the sign-off commit,
  and lint is clean. A seven-line alternative also passes: legacy acceptance for
  1, 2, 6 and 7 only, plus the record ID `archive prepare` found for milestone 8.
  That record was in history but missing from the hand-written archive.
- At the commit where the goal entered awaiting-signoff, `status` warns
  `goal-criteria-missing` and `milestone-proof-missing` for 1, 2, 6 and 7. Its
  `signoff` object lists the goal-criteria proposal, legacy acceptance and
  sign-off together, and Needs you asks for them in one line.

Tests: `tests/test_long_horizon_completion.py` is an invented fixture of the
same shape. It covers pre-Checks milestones with commit citations, a recorded
check cited as `task=<id>`, Checks added after the only run, and a goal without
criteria until sign-off. The tests check the early warnings, the single
pre-check, prepare/fill/refresh, gate and `archive check` with legacy
acceptance, each way legacy acceptance can be malformed, a hand-written archive
fixed by one block, and that legacy acceptance cannot cover a milestone
completed in the gated batch. `tests/test_long_horizon_delegation.py` uses the
real checker for two judge runs, then `prepare A B`, a written record and a
review-doc edit, then the second record. It also covers `--result 1` with the
candidate list, a late snapshot's guidance, the in-scope PASS block, and
rerecord of a delegated record after a criteria edit.
`tests/test_long_horizon_evidence.py` covers compact/`--full`/multi prepare and
`--review-text`.

Verification on macOS (Darwin 25.5.0):

- `python3 scripts/sync_marketplaces.py --check`: passed. The manifests declare
  long-horizon 0.7.0 and delegation 0.11.2.
- `python3 scripts/run_tests.py`: 487 tests passed (476 before plus 11 new). The
  0.5.2/0.10.1 golden baselines are unchanged.
- `python3 scripts/verify_lifecycle.py --report
  ~/.cache/rickdiculousli-tools/verification/plugin-verification.json`: PASS at
  **2026-10-14T01:09:53Z** on **codex-cli 0.162.1** and **Claude Code
  2.1.296**, in disposable profiles. Both hosts observed long-horizon 0.7.0 and
  delegation 0.11.2. A first run failed on both hosts only because the new
  module was not yet tracked, since the verifier compares against `git
  ls-files`. It passed once committed.

Not performed: no model session has run the updated resume/checkpoint/migrate
skills, and the consuming repository's real archive was not edited.
