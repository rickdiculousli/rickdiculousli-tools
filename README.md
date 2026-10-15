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
| `quota` | `uv`, Python 3.10+ (resolved by `uv`), network access, and your own Claude/Codex subscription login; Codex readings also need its CLI on PATH |
| `yt-transcript` | `uv`, Python 3.10+ (resolved by `uv`), `ffmpeg` on PATH, and internet access for videos, dependencies, and models |
| `method` | Supported host; `update.sh` needs `bash`, `git`, `diff` and access to GitHub |

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
| `repository-info` | Informational stub describing this layout |
| `quota` | `quota` skill: reads Claude and Codex subscription usage (windows, resets, weekly pace, projected unused); numbers only |
| `yt-transcript` | `yt-transcript` skill: timestamped YouTube transcript from captions, auto-captions or Whisper (MLX on Apple Silicon, faster-whisper elsewhere) |
| `method` | `grill-me` and `grilling` (a relentless interview to stress-test a plan) and `writing-plans` (an implementation plan from a spec), copied verbatim from upstream |

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

## Method skills

`method` carries three skills unchanged from their upstreams: `grill-me` and `grilling` from
[mattpocock/skills](https://github.com/mattpocock/skills) and `writing-plans` from
[obra/superpowers](https://github.com/obra/superpowers). `writing-plans` still names other
superpowers skills for running a plan; they are not part of this plugin. In Claude Code they are
`/method:grill-me`, `/method:grilling` and `/method:writing-plans`.

`plugins/method/UPSTREAM` pins the commit each upstream was copied at. `update.sh` fetches each
upstream shallow into a temp dir, at its pin or at the ref `--to` names, prints the diff per skill,
copies the skill directories over, records the new commits in `UPSTREAM` and reminds you to bump
the version when a skill changed. `--check` prints the diffs and changes nothing; it exits 1 when a
skill differs from upstream. For a repo fetched at its pin, both modes say when its default
branch has moved past the pin.

```sh
plugins/method/update.sh --check                                   # the copy against the pins
plugins/method/update.sh --check --to obra/superpowers=HEAD        # against upstream's latest
plugins/method/update.sh --to obra/superpowers=HEAD --to mattpocock/skills=HEAD
```

## Install from this checkout

Run these commands from the repository root. They register this local checkout
and install the plugins in your normal user profile.

### Claude Code

```sh
claude plugin marketplace add "$PWD"
claude plugin install visual-audit@rickdiculousli-tools
claude plugin install hello-world@rickdiculousli-tools
claude plugin install repository-info@rickdiculousli-tools
claude plugin install quota@rickdiculousli-tools
claude plugin install quota@rickdiculousli-tools
claude plugin install yt-transcript@rickdiculousli-tools
claude plugin install method@rickdiculousli-tools
claude plugin list --available --json
claude plugin details visual-audit
```

In a new Claude Code session, invoke `/visual-audit:audit-report`,
`/hello-world:hello`, `/repository-info:about`, or `/method:grill-me`. Restart an existing session after changing plugins.

### Codex

```sh
codex plugin marketplace add "$PWD"
codex plugin add visual-audit@rickdiculousli-tools
codex plugin add hello-world@rickdiculousli-tools
codex plugin add repository-info@rickdiculousli-tools
codex plugin add quota@rickdiculousli-tools
codex plugin add quota@rickdiculousli-tools
codex plugin add yt-transcript@rickdiculousli-tools
codex plugin add method@rickdiculousli-tools
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
claude plugin uninstall quota@rickdiculousli-tools
claude plugin uninstall quota@rickdiculousli-tools
claude plugin uninstall yt-transcript@rickdiculousli-tools
claude plugin uninstall method@rickdiculousli-tools
claude plugin marketplace remove rickdiculousli-tools

codex plugin remove visual-audit@rickdiculousli-tools
codex plugin remove hello-world@rickdiculousli-tools
codex plugin remove repository-info@rickdiculousli-tools
codex plugin remove quota@rickdiculousli-tools
codex plugin remove quota@rickdiculousli-tools
codex plugin remove yt-transcript@rickdiculousli-tools
codex plugin remove method@rickdiculousli-tools
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
  tiers.json                          # optional: subagent tiers
  agents/<tier>.md                    # generated from tiers.json (Claude Code)
.claude-plugin/marketplace.json       # generated Claude marketplace
.agents/plugins/marketplace.json      # generated Codex marketplace
scripts/sync_marketplaces.py          # deterministic metadata generation
scripts/verify_lifecycle.py           # real CLI integration checks
tests/                               # generator, verifier, and renderer tests
```

`visual-audit` ships its renderer, templates, and references inside its skill
folder; `quota` and `yt-transcript` ship their PEP 723 scripts the same way, and `method` its
`UPSTREAM` pins and `update.sh` at the plugin root. `hello-world` and `repository-info` are stubs. The stubs and audit renderer work
without credentials or external services. Quota uses provider logins/services;
transcripts download from YouTube and model/package hosts. The adapters share identity and content, while translating the hosts'
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
state. For example, to update quota:

```sh
claude plugin marketplace update rickdiculousli-tools
claude plugin update quota@rickdiculousli-tools --scope user
codex plugin add quota@rickdiculousli-tools --json
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
PLUGIN_NAME=quota
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
python3 scripts/run_tests.py   # parallel; python3 -m unittest discover -s tests -v runs it serially
python3 scripts/verify_lifecycle.py --report "${XDG_CACHE_HOME:-$HOME/.cache}/rickdiculousli-tools/verification/plugin-verification.json"
# For a Codex-only run, add --hosts codex.
```

Commit the sources and generated files together. Edit root `plugin.json` and
`catalog.json`; regeneration replaces host manifests. Bump the plugin version
when releasing changed content. To refresh an installed plugin after edits,
regenerate and follow [the local update procedure](#update-installed-plugins-from-a-local-checkout).

New plugins are included automatically in lifecycle verification. Future MCP
servers, hooks, or host-specific components need explicit adapter support and
host verification.

A plugin with a `tiers.json` (none of the shipped plugins today; the retired `delegation` was one) also gets generated
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
python3 scripts/verify_lifecycle.py --report "${XDG_CACHE_HOME:-$HOME/.cache}/rickdiculousli-tools/verification/plugin-verification.json"
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

## Retired

`delegation` and `long-horizon` were retired on 2026-10-15 and live under `retired/` with their
tests, fixtures and pilot notes; they are not in the marketplace and cannot be installed from it.
[buildermesh](https://github.com/rickdiculousli/buildermesh) replaces both: a lead thread owns one
spec, delegates to executors and routines over a NATS mesh, and results are recorded by git tree
hash (the idea `delegation` kept in its ledger). A goal that spanned sessions is now a long spec in
the same place as any other.

## License

[MIT](LICENSE).
