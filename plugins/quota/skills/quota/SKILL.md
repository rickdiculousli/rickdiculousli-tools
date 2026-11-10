---
name: quota
description: Reads how much of the Claude and Codex subscriptions is used and left, with reset times and weekly pace. Use before large or background work, when choosing a provider, or when the user asks about usage or limits.
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

`<skill-dir>` is the directory containing this SKILL.md. A script that calls this
one takes its path as a setting (the installed skill or any checkout's
`plugins/quota/skills/quota/scripts/quota.py`), never a hardcoded clone or plugin-cache path.

It uses your own subscription login. Claude credential selection is, in order:
`QUOTA_CLAUDE_CREDENTIALS_FILE`, `CLAUDE_CODE_OAUTH_TOKEN`, then the selected
profile. `CLAUDE_CONFIG_DIR` selects a profile's `.credentials.json`; otherwise
macOS uses the default Keychain service and falls back to `~/.claude/.credentials.json`.
For a custom macOS Keychain entry, set `QUOTA_CLAUDE_KEYCHAIN_SERVICE` to its exact
service name. A custom profile never silently falls back to the default account.
Codex inherits `CODEX_HOME` and other host environment settings through its app
server. API-key-only accounts do not provide these subscription readings.

## Reading it

The output labels its own fields. A plan with no 5-hour window, such as Claude's Ultra
(its login's tier reads `max_20x`), shows `none` in text and `null` in `--json`. Weekly pace and its projections are empty (`?` in
text, `null` in `--json`) while the weekly window is younger than 12 hours.

Claude can also have scoped weekly limits: one model's own allowance (such as Opus,
Sonnet or another named model) inside the weekly window, which can run out while the
weekly window still has room. Each shows as its own line under Claude, named for its
model or surface, and in `--json` under `scoped` (`name`, `percent`, `resets_at`,
`binding`, pace and projection). The one marked `← binding` (`"binding": true`) is the
limit that runs out first: read work for that model against it, not against the weekly
window. A scoped limit gets a pace only when it resets with the weekly window.

When overflow is billed (extra usage or credits), treat 100%
as a hard stop. The script reports numbers only. It never decides whether to run work; you do,
from the numbers and what the user asked. It exits 2 only when no provider could be
read. Every reading is appended to
`${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/quota/usage.jsonl`.
