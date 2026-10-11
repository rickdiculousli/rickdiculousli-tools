---
name: quota
description: Use when you need to know how much of the Claude or Codex subscription is used or left, before starting large or background work, when deciding which provider has room, or when the user asks about usage, limits, resets or leftover quota.
---

# Quota

Read both subscriptions' usage with the bundled script. Each read costs no tokens:
Claude is read from the page Claude Code's `/usage` screen reads, with the login
Claude Code already keeps; Codex from `account/rateLimits/read` on its own app
server (`codex app-server`). Both are undocumented, so a read can fail; the script
then reports that provider as unknown with the reason.

```sh
uv run --script <skill-dir>/scripts/quota.py                    # both, human-readable
uv run --script <skill-dir>/scripts/quota.py --provider codex   # claude | codex | all
uv run --script <skill-dir>/scripts/quota.py --json             # for agents
```

`<skill-dir>` is the directory containing this SKILL.md. Quote the resolved script
path when it contains spaces. From another script, accept the script path as a
configuration value; use the installed skill path or any checkout's
`plugins/quota/skills/quota/scripts/quota.py`. Do not assume a username, clone
location, or versioned plugin cache path.

The script requires Python 3.10+; `uv` resolves a suitable interpreter. It uses
your own subscription login. Claude credential selection is, in order:
`QUOTA_CLAUDE_CREDENTIALS_FILE`, `CLAUDE_CODE_OAUTH_TOKEN`, then the selected
profile. `CLAUDE_CONFIG_DIR` selects a profile's `.credentials.json`; otherwise
macOS uses the default Keychain service and falls back to `~/.claude/.credentials.json`.
For a custom macOS Keychain entry, set `QUOTA_CLAUDE_KEYCHAIN_SERVICE` to its exact
service name. A custom profile never silently falls back to the default account.
Codex inherits `CODEX_HOME` and other host environment settings through its app
server. API-key-only accounts do not provide these subscription readings.

## Reading it

For each provider:

- **5-hour and weekly windows**: percent used and time to each reset.
- **Weekly pace**: points per hour across the weekly window so far, and the
  projected percent at the reset. Windows younger than 12 hours have no pace.
- **Projected unused at reset**: points that will expire unused at the current pace.
- **Overflow billed**: whether usage past 100% costs money (extra usage or credits).
  If it does, treat 100% as a hard stop.
- **Banked resets** (Codex): reset credits available and when they expire.

The script reports numbers only. It never decides whether to run work; you do,
from the numbers and what the user asked. It exits 2 only when no provider could be
read. Every reading is appended to
`${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/quota/usage.jsonl`.
