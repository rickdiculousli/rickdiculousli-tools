# rickdiculousli-tools

Rick Li's shared tools, packaged as plugins for Claude Code and Codex. Each plugin contains one
portable manifest and one set of skills. A small generator produces the host
compatibility manifests and marketplaces; consumers install directly from the
committed repository without a build step.

Clone this repository wherever you like and install only the plugins you need.
Paths resolve from the checkout or installed skill, and runtime data belongs to
the current user. Author and marketplace names are shared package identity.

| Plugin | Runtime requirements |
| --- | --- |
| `hello-world`, `repository-info` | Claude Code or Codex with plugin support |
| `visual-audit` | Supported host and Python 3.10+ |
| `long-horizon` | Supported host, Git, Python 3.10+; optional declared delegation/quota scripts |
| `delegation` | Supported host with subagents, Git, Python 3.10+, and repository-specific setup |
| `quota` | `uv`, Python 3.10+ (resolved by `uv`), network access, and your own Claude/Codex subscription login; Codex readings also need its CLI on PATH |
| `yt-transcript` | `uv`, Python 3.10+ (resolved by `uv`), `ffmpeg` on PATH, and internet access for videos, dependencies, and models |

Recorded live quota/transcript checks cover Apple Silicon macOS and Ubuntu x86_64.
Intel Mac Whisper dependency selection is covered by a metadata regression test;
actual Intel Mac execution has not been checked. Windows support remains unverified;
the first real Windows run will determine what needs adjustment. See
[verification scope](docs/verification.md). Shell examples below use POSIX syntax;
in PowerShell use `python` if `python3` is unavailable and pass `(Get-Location).Path`
instead of `"$PWD"` to the marketplace registration command. Quote paths with spaces.

The plugins have been installed, byte-compared, and uninstalled through the
real native marketplaces on Codex **0.162.1** and Claude Code **2.1.296**.
See [verification evidence and scope](docs/verification.md).

| Plugin | What it does |
| --- | --- |
| `visual-audit` | `audit-report` skill: renders what the agent did in a session as one self-contained HTML page for visual auditing |
| `hello-world` | Greeting stub for testing installation |
| `long-horizon` | Shared setup/resume/checkpoint skills and deterministic scoped acceptance across sessions |
| `repository-info` | Informational stub describing this layout |
| `quota` | `quota` skill: reads Claude and Codex subscription usage (windows, resets, weekly pace, projected unused); numbers only |
| `yt-transcript` | `yt-transcript` skill: timestamped YouTube transcript from captions, auto-captions or Whisper (MLX on Apple Silicon, faster-whisper elsewhere) |
| `delegation` | `setup` skill prepares a repo; `delegation` skill: the main session (judge) routes bulk work to `execute` and `routine` tier subagents and records validator evidence by git tree hash. |

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

## Delegation

The `delegation` skill makes the main session the judge: it routes bulk work to
`execute` and `routine` tier subagents and records validator results against the
git tree hash. Claude Code gets generated `delegation:execute` and
`delegation:routine` agents; Codex has no plugin agent definitions, so the skill
spawns its default subagent with the tier's model and effort.

Claude tiers use the `opus`, `sonnet`, and `haiku` family aliases, so the host
selects the corresponding model for your account/provider; see
[Claude model configuration](https://code.claude.com/docs/en/model-config).
Codex model preferences are in `plugins/delegation/tiers.json`; unavailable model
overrides fall back to the host's default subagent. A host without subagent tools
can use the other plugins; delegation requires that capability. Repository
validator commands must fit the host's shell (`/bin/sh` on POSIX, `cmd.exe` on
Windows), or invoke the intended shell explicitly. The overlay's `requires`
attribute can limit validators to specific platforms.

To set a repository up, open a session there and run `/delegation:setup` in Claude Code
(or ask Codex to use the `setup` skill from `delegation`). It surveys the repo, drafts the
overlay and pointer line for your approval, writes them, and runs every validator once
through the ledger. To do it by hand, add this line to that repository's `AGENTS.md`:

```text
Delegation: follow the delegation skill; this repo's overlay is .agents/delegation.md.
```

The overlay at `.agents/delegation.md` holds that repository's validators (with
optional `cheap`, `needs-human`, `timeout`, `lock` and `requires` attributes), locks that cap heavy
commands across every worktree (`check.py exec --lock`, `check.py locks`), tier
hints, findings sink and parallel limit. Its state, including each validator run's full
output, lives under `${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/delegation/`,
scoped by canonical repository and worktree identities. Scratch indexes/objects use
`${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/delegation/`. Check the overlay and the
evidence ledger with the bundled script. These paths exist only in this
checkout; in a consuming repository the skill resolves the script as
`<skill-dir>/scripts/check.py`:

```sh
python3 plugins/delegation/skills/delegation/scripts/check.py lint
python3 plugins/delegation/skills/delegation/scripts/check.py tree
python3 plugins/delegation/skills/delegation/scripts/check.py pending
python3 plugins/delegation/skills/delegation/scripts/check.py query --help
python3 plugins/delegation/skills/delegation/scripts/check.py brief --help
python3 plugins/delegation/skills/delegation/scripts/check.py locks
python3 plugins/delegation/skills/delegation/scripts/check.py exec --help
python3 plugins/delegation/skills/delegation/scripts/check.py kinds
python3 plugins/delegation/skills/delegation/scripts/check.py patterns
```

Since 0.8.0 the judge labels each delegation with a work kind
(`open --kind <label>`, or `--kind <label> --new-kind "<description>"` to register
one; an unknown label is refused with the closest existing ones). Labels and a
pattern log are shared by every worktree and session of a repository.
`check.py patterns` lists kinds used three or more times that have no role, plus
unlabeled briefs grouped by shape. The judge then adds a role or repository
script, or proposes it where you asked to approve; `kinds merge`, `kinds rename` and
`kinds mark <kind> proposed|approved|declined` keep labels and decisions tidy.
By default the judge adds such roles and scripts itself and tells you; an
overlay `## Authoring` section with `roles: ask` or `scripts: ask` makes it ask
first (setup asks which you want). Briefs also name a per-delegation scratch directory
outside the worktree for throwaway scripts. Pattern lines are kept 180 days, then
folded into per-kind counts; untouched scratch files are kept 30 days. See
[the patterns reference](plugins/delegation/skills/delegation/reference/patterns.md).

Optional overlay sections add script proposals (`name: command; what it
replaces`), host-side never-write restrictions, and reusable roles:

Delegation 0.7.2 uses `check.py paths --json` (or the text view) to resolve
`brief_directory`, `context_directory`, `log_directory`, the repository resource
locks and permanent root mutex. Quote returned paths. Context references in
briefs and `Extra inputs` use `state:context/<relative-path>`; roles name tracked
repository-relative sources. The checker
rejects traversal and symlink escapes. Recorded generated paths are state-relative
with `location: state`; caller brief paths may remain absolute.

On POSIX, for an existing `.delegation/` history, close its open work using the old checker
and stop every repository checker/validator session. Run `check.py state migrate`
to review counts, conflicts, unknown files, host restrictions and reference edits;
then `check.py state migrate --apply`. It preserves original event/log hashes and
writes a digest receipt, leaving legacy copies and old temporary locks untouched.
Update the reported overlay/helper references, then restart all sessions with the
new checker and one shared XDG root. Do not run old/new versions simultaneously.
Changed legacy files block dependent operations; migration never creates a PASS.
Logical input renames can make current fingerprints stale, requiring a fresh check.

`check.py state gc` previews local collection and `check.py state gc --apply`
applies it, even outside a checkout. `--if-due` limits applied sweeps to once per
168 hours; normal writes do this automatically. Confirmed deleted, unregistered
worktrees get seven days of recovery before removal. Existing unfinished work,
ledger-referenced bytes, declared role inputs, live locks and uncertain processes
are retained. Unreferenced briefs/context expire after 30 days. Hash scratch is
removed on exit; a weekly sweep removes interrupted attempts only when the owner
is confirmed gone. No background service runs. Legacy copies require explicit
review/removal. Durable knowledge and acceptance stay in tracked documents.
Both plugins honor explicit absolute XDG state/cache overrides on every platform.
Without overrides, Windows uses `%LOCALAPPDATA%\rickdiculousli-tools\<plugin>\state\`
and `%LOCALAPPDATA%\rickdiculousli-tools\<plugin>\cache\`; missing/invalid LOCALAPPDATA
uses the Python-resolved home `AppData\Local` directory. POSIX retains the home
`.local/state` and `.cache` defaults. Empty/relative XDG values select these
platform defaults. Legacy migration is POSIX-only; Windows starts fresh. Unwritable roots
fail with a diagnostic and never switch lock domains. Workspace sandboxes must
allow both configured external XDG roots; grant those paths through the host’s
permission configuration rather than changing roots for individual commands.

```text
## Roles
capture: tier=execute, runbook=.agents/delegation/runbooks/capture.md, max-uses=8, max-context-bytes=100000
## Locks
games: slots=6, wait=3600
```

The overlay stays at `.agents/delegation.md`; optional tracked runbook sources
and approved rote scripts default to `.agents/delegation/runbooks/` and
`.agents/delegation/scripts/`. `open` copies role sources into external context,
refuses changes while any open delegation pins those bytes, and refreshes after
all pins close. Edit tracked sources on final use. Legacy state references remain
supported with migration warnings. General tools may stay in their own location;
the judge adds scripts and roles per the overlay's `## Authoring` policy. See the
[layout and migration guide](plugins/delegation/skills/delegation/reference/overlay.md#repository-material-and-migration).

Wrap each native process with one foreground
`python3 "$DELEGATION_CHECKER" exec --lock games --timeout 300 -- <command>`.
Configure the checker path from an installed skill or any checkout and quote
paths with spaces. Slots apply across worktrees sharing the same XDG state root;
keep children in the foreground. Since 0.7.3, on POSIX, signalling `check.py`
(SIGTERM, SIGINT, SIGHUP) forwards to the wrapped process group, kills it after
a one-second grace, and releases the lock. Outer orchestration is optional, and validators
and general tools remain usable standalone through their existing commands.

Roles require at least one cap; prefer `max-uses`. Counts include the first brief
and all ancestor branches. Byte caps accumulate brief/context file sizes per use,
excluding outputs; they do not measure actual model context. Start with
`check.py open --delegation <id> --tier execute --role capture --brief <path>`; reuse a closed
prior brief with `open --delegation <new-id> --tier execute --continue <prior-id> --brief <new-path>`.
`--tier` remains required and must match the role. The tier stays the same and
each use records new brief/runbook hashes. The judge
maps delegation ids to host agent ids and uses the printed follow-up loader.

Peer roles can execute caller commands asynchronously while independent work
continues. The caller brief names the peer host id and caller delegation id, and
stays open until completion. Use `run ... --delegation <caller-id>` or
`exec --lock games --timeout 300 --delegation <caller-id> -- <command>` to attribute
evidence to the caller. `exec` records `validator=null`; its observations must be
cited or asserted rather than accepted as checked registered-validator results.
A lock covers the full foreground process lifetime. Never detach launches; one
command owns one slot, so multiple jobs need a slot per child or serialization.
Windows uses standard-library byte locks; macOS/Linux use `flock`. Host peer support is checked before
use, with judge relay as the fallback.

Setup proposes deterministic repository helpers but writes scripts only with
explicit approval. Later, the judge adds roles and scripts for repeated work
under the overlay's `## Authoring` policy (default `allowed`); where it says
`ask`, it proposes them and records unaccepted proposals in the findings/handoff
sink, falling back to the execution log. `needs-human` checks require user notification before work and
early while the user is present, without infinite retries. Existing
overlays remain valid. Brief footers prohibit commits unless explicitly allowed,
first-person committed text, and host changes named by a nonempty restrictions
section outside the worktree. These are agent instructions, not filesystem
enforcement.

Install and remove it like the other plugins:

```sh
claude plugin install delegation@rickdiculousli-tools
codex plugin add delegation@rickdiculousli-tools
claude plugin uninstall delegation@rickdiculousli-tools
codex plugin remove delegation@rickdiculousli-tools
```

Routing quality has not been evaluated; that is for a pilot.

## Quota and YouTube transcripts

Both are PEP 723 scripts run with `uv run --script`. `quota.py` has no dependencies;
`yt_transcript.py` resolves `yt-dlp` and the Whisper backend for the platform on
first run and needs `ffmpeg`. Apple Silicon uses MLX; Intel Macs and other systems
use faster-whisper on CPU. Run these commands from any checkout location:

```sh
uv run --script plugins/quota/skills/quota/scripts/quota.py --json
uv run --script plugins/yt-transcript/skills/yt-transcript/scripts/yt_transcript.py <url>
```

Quota readings are logged to `${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/quota/usage.jsonl`;
transcripts go to `${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/youtube/<id>/`.

Installed skills run their bundled scripts directly. Other scripts should accept
a configurable path to the installed script or to a checkout's
`plugins/<plugin>/skills/<skill>/scripts/<script>`; no `~/repos` layout is required.
Both data locations are resolved with the current user's home directory and can
be overridden with the XDG environment variables. Transcript output also accepts
`--out <dir>`.

Quota reads the current user's login, never the author's. Claude supports
`CLAUDE_CONFIG_DIR`, an explicit `QUOTA_CLAUDE_CREDENTIALS_FILE`, or
`CLAUDE_CODE_OAUTH_TOKEN`. On macOS the default profile uses Keychain; a custom
Keychain entry can be selected with `QUOTA_CLAUDE_KEYCHAIN_SERVICE`. Custom profiles
do not fall back to the default account. Codex's app server inherits `CODEX_HOME`.
These subscription interfaces are undocumented and may report a provider as
unknown; API-key-only accounts do not supply subscription quota.

## Install from this checkout

Run these commands from the repository root. They register this local checkout
and install the plugins in your normal user profile.

### Claude Code

```sh
claude plugin marketplace add "$PWD"
claude plugin install visual-audit@rickdiculousli-tools
claude plugin install hello-world@rickdiculousli-tools
claude plugin install repository-info@rickdiculousli-tools
claude plugin install delegation@rickdiculousli-tools
claude plugin install quota@rickdiculousli-tools
claude plugin install yt-transcript@rickdiculousli-tools
claude plugin list --available --json
claude plugin details visual-audit
```

In a new Claude Code session, invoke `/visual-audit:audit-report`,
`/hello-world:hello`, or `/repository-info:about`. Restart an existing session after changing plugins.

### Codex

```sh
codex plugin marketplace add "$PWD"
codex plugin add visual-audit@rickdiculousli-tools
codex plugin add hello-world@rickdiculousli-tools
codex plugin add repository-info@rickdiculousli-tools
codex plugin add delegation@rickdiculousli-tools
codex plugin add quota@rickdiculousli-tools
codex plugin add yt-transcript@rickdiculousli-tools
codex plugin list --marketplace rickdiculousli-tools --available --json
```

In a new Codex session, ask it to use the `audit-report` skill from
`visual-audit`, the `hello` skill from `hello-world`, or the `about` skill from
`repository-info`.

### Uninstall

```sh
claude plugin uninstall visual-audit@rickdiculousli-tools
claude plugin uninstall hello-world@rickdiculousli-tools
claude plugin uninstall repository-info@rickdiculousli-tools
claude plugin uninstall delegation@rickdiculousli-tools
claude plugin uninstall quota@rickdiculousli-tools
claude plugin uninstall yt-transcript@rickdiculousli-tools
claude plugin marketplace remove rickdiculousli-tools

codex plugin remove visual-audit@rickdiculousli-tools
codex plugin remove hello-world@rickdiculousli-tools
codex plugin remove repository-info@rickdiculousli-tools
codex plugin remove delegation@rickdiculousli-tools
codex plugin remove quota@rickdiculousli-tools
codex plugin remove yt-transcript@rickdiculousli-tools
codex plugin marketplace remove rickdiculousli-tools
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
folder; `quota` and `yt-transcript` ship their PEP 723 scripts the same way. `hello-world` and `repository-info` are stubs. The stubs and audit renderer work
without credentials or external services. Quota uses provider logins/services;
transcripts download from YouTube and model/package hosts. Delegation uses the
host's authenticated model service. The adapters share identity and content, while translating the hosts'
different marketplace source formats.

## Update installed plugins from a local checkout

When asked to pull and update this repository's plugins, use the existing
local-checkout marketplace in each host's normal user profile. Check for local
changes first, then fast-forward the checkout; do not overwrite uncommitted work.
Run these commands from the checkout, wherever it is located:

```sh
git status --short --branch
git pull --ff-only
python3 scripts/sync_marketplaces.py --check
claude plugin list --json
codex plugin list --marketplace rickdiculousli-tools --json
```

Compare the installed versions with `plugins/<name>/plugin.json` and refresh
outdated installed plugins. Keep the user's existing plugin selection and enabled
state. For example, to update delegation:

```sh
claude plugin marketplace update rickdiculousli-tools
claude plugin update delegation@rickdiculousli-tools --scope user
codex plugin add delegation@rickdiculousli-tools --json
```

Claude's `update` refreshes an existing installation; Codex's `add` also refreshes
an existing installation from the local source. Uninstall/reinstall is a fallback
if the installed copy still differs. Codex's `marketplace upgrade` is for Git
marketplaces and reports that a local marketplace is not configured as Git;
pull the checkout instead. Marketplace registration alone does not refresh an
installed cache. If a marketplace is missing, register this checkout with
`claude plugin marketplace add "$PWD"` or `codex plugin marketplace add "$PWD"`.

Verify the native installed lists again: each refreshed plugin must have the
source version and retain its enabled state. Check actual installed files too,
because matching version numbers alone do not prove the cache is current.
Claude's list reports `installPath`; Codex's `add --json` reports `installedPath`.
Use the repository's existing comparison helpers with the reported path:

```sh
# Replace these values with the plugin name and the native reported cache path.
PLUGIN_NAME=delegation
INSTALLED_PATH='/absolute/path/reported/by/the/host'
PYTHONDONTWRITEBYTECODE=1 python3 - "$PLUGIN_NAME" "$INSTALLED_PATH" <<'PY'
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / "scripts"))
from verify_lifecycle import compare_tree, tracked_files

plugin = Path("plugins") / sys.argv[1]
problems = compare_tree(tracked_files(root, plugin), root / plugin, Path(sys.argv[2]))
if problems:
    raise SystemExit("\n".join(problems))
print("Installed portable files match the checkout byte for byte.")
PY
```

Repeat the comparison for each installed plugin in both hosts. It checks missing,
changed and extra files, excluding generated host manifests and incidental
`__pycache__`/`.DS_Store` files. Record the checkout commit, host versions and
actual results when documenting an update. Restart Claude Code and start a new
Codex session to load the updated skills. These commands were verified on
Claude Code 2.1.296 and Codex 0.162.1 when updating delegation to 0.8.0.

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
# For a Codex-only run, add --hosts codex.
```

Commit the sources and generated files together. Edit root `plugin.json` and
`catalog.json`; regeneration replaces host manifests. Bump the plugin version
when releasing changed content. To refresh an installed plugin after edits,
regenerate and follow [the local update procedure](#update-installed-plugins-from-a-local-checkout).

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
# For a Codex-only run, add --hosts codex.
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

## Long-horizon

`long-horizon` 0.1.0 provides `long-horizon:setup`, `long-horizon:resume` and
`long-horizon:checkpoint` for bounded progress across sessions. Setup can create
or adopt goals, update policy, add a goal or wind down; it shows concrete drafts
and a selected-task dry run before applying them. Quick setup asks at most five
questions and accepts “you decide” defaults. See the
[cheat sheet](plugins/long-horizon/skills/setup/reference/cheatsheet.md),
[overlay format](plugins/long-horizon/skills/resume/reference/overlay.md) and
[observed pilot scope](docs/long-horizon-pilots.md).

Install through the already-registered marketplace:

```sh
claude plugin install long-horizon@rickdiculousli-tools
codex plugin add long-horizon@rickdiculousli-tools
```

Use `/long-horizon:setup`, `/long-horizon:resume` or `/long-horizon:checkpoint` in
Claude Code; ask Codex for those plugin-qualified skills. “Where are we?” is
read-only status; “continue” selects one eligible task or blocker resolution.
Readiness describes prepared inputs; it never supplies validator acceptance.
A newly done task needs evidence, a milestone needs its whole acceptance checks,
and goal completion requires the configured sign-off and a durable archive.

The same Python 3.10+ standard-library CLI ships on both hosts. From this checkout:

```sh
python3 plugins/long-horizon/skills/resume/scripts/lh.py status --brief
python3 plugins/long-horizon/skills/resume/scripts/lh.py lint
python3 plugins/long-horizon/skills/resume/scripts/lh.py paths --root "$PROJECT" --json
python3 plugins/long-horizon/skills/resume/scripts/lh.py state gc --json
```

Consumers declare `LONG_HORIZON_SCRIPT` or an explicit script path pointing at
an installed skill's resume/scripts/lh.py or any checkout's
plugins/long-horizon/skills/resume/scripts/lh.py. Quote paths with spaces; never
glob a versioned plugin cache. Setup/checkpoint resolve the sibling resume script. Long-horizon 0.2.0 adds
`state draft --root "$PROJECT" --json`: it returns an identity-bearing setup
`draft_directory` under the repository/worktree-scoped XDG cache. Renew recovered
drafts with `state draft --id <id>` before use. Weekly GC removes unused recognized
drafts after 30 days and applies the seven-day recovery window to deleted,
unregistered worktrees; active/uncertain owners, unknown files and symlinks protect
recovery bytes. Existing plugin-wide drafts remain for explicit review.


Long-horizon 0.3.0 supports Startup `readiness: "cache:readiness.json"`.
`paths --root "$PROJECT" --json` discovers `readiness_path` under the current
worktree cache’s `readiness/` directory, `state_directory`, `cache_directory`,
`readiness_directory`, `cache_identity_path` and `cache_identity`, without creating
files. Helpers publish the cache identity and report under the lifecycle lock;
see [readiness publication](plugins/long-horizon/skills/resume/reference/readiness.md).
Legacy readiness paths keep working with a lint warning. Readiness remains
unknown when missing/stale/for another checkout. Weekly GC recognises readiness
JSON and applies the deleted-worktree recovery window.

| Project | Composition |
| --- | --- |
| Goal spans sessions, solo work | long-horizon |
| Goal spans sessions, batches need workers/registered validators | long-horizon + delegation |
| Bulk task fits one session | delegation alone |
| Optional capacity-aware smaller batch | one opt-in quota read, never blocking |

One survey feeds both setups. Check names refer to registered validators rather
than duplicating their commands. Solo checkpoint prepares a scope snapshot, runs
an authorized check, records its actual outcome and reviews the proposed durable
JSON/trailer. Combined checkpoint records an exact-tree delegation result before
roadmap edits. Later docs-only changes may reuse scoped historical acceptance;
they do not invent a current-tree ledger result. See
[standalone and combined walkthroughs](plugins/long-horizon/skills/checkpoint/SKILL.md).

No validators or Git integration operations are launched by the CLI. Skills
perform only actually authorized operations. Commit, merge, push and host sync
have separate observed/verified closure steps; rejected push/sync preserves earlier
success and offers the exact remaining step. Remote containment is explicitly
qualified as a local remote-ref observation, not server-present-state proof.

Runtime state follows [XDG retention](plugins/long-horizon/skills/resume/reference/state.md):
one fixed root lock, repository/worktree SHA-256 keys, weekly opportunistic cleanup,
a seven-day confirmed-deleted-worktree recovery window, and 30-day unreferenced
snapshot/draft expiry. Existing worktrees retain unfinished work. Read-only
inspection creates no state. Approved wind-down clears only the displayed current
payload; durable Git evidence and other plugins survive. Manual `state gc` works
outside Git. No scheduler, hooks, background workers or consumer build are needed.
