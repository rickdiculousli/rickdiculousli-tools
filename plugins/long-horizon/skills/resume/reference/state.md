# State and recovery

Persistent operational records live under
`${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/long-horizon/`; worktree-scoped
setup drafts use `${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/long-horizon/`.
Python resolves home; empty/relative XDG values fall back to defaults. Every
process coordinating this plugin uses the same writable state root; failure is
reported rather than changing lock domain. A workspace sandbox must allow the
configured external XDG state/cache roots; use host permissions rather than
switching roots per invocation. The CLI rejects XDG roots inside this checkout, its Git directories or the installed plugin. No consumer runtime file goes in a
checkout, Git directory or installed plugin. Each plugin is self-contained.

Layout: permanent `state.lock`, `gc.json`, then SHA-256(canonical Git common dir)/
worktrees/SHA-256(canonical worktree)/identity.json, closure.json, evidence/*.json,
snapshots/*.json and trailers.txt. Identity records canonical paths, device/inode,
birth time where available, volume, created/last mutation and first missing time.
Recreated directories cannot inherit old state; mutation quarantines an old
identity generation with a unique retired suffix. Unknown/unavailable identities
are retained. Status reports resolved state path and creates nothing.

All writes use one fixed root POSIX flock or Windows msvcrt byte lock and atomic
replacement. Never unlink/replace state.lock. Do not hold it while running probes,
validators, startup or Git integration. Failed writes preserve prior JSON.

```sh
python3 "$LONG_HORIZON_SCRIPT" state gc --json
python3 "$LONG_HORIZON_SCRIPT" state gc --apply --json
python3 "$LONG_HORIZON_SCRIPT" state gc --apply --if-due --json
```

Preview creates no payload. Existing namespaces are inspected under the lifecycle mutex; an entirely absent namespace stays absent. Apply checks eligibility under the lock. Weekly sweep
runs at first mutation or explicit setup/resume/checkpoint after 168 hours; no
background process. Read-only status/lint/find/gate/closure verify do not collect.
A deleted worktree requires absent directory AND absent local Git registration.
If common dir is gone, recorded worktree/git directories must also be absent.
Unavailable volumes, permission errors, registered missing worktrees and mismatched
identity are retained with diagnostics. Never prune Git registration here.

Confirmed deletion starts an independent seven-day recovery window, then the
whole payload can expire including unfinished closure/pending evidence, which GC
lists. Cleanup is abandonment, never completion. Existing worktrees retain pending
records and referenced snapshots/unfinished closure regardless of age. Unreferenced
snapshots/drafts expire after 30 days without use; the next sweep removes them.
Cleanup confines recognized payloads, skips symlinks/unknown files and tolerates
partial failures. Committed evidence/goals/archives and live locks survive.

Recover explicitly during grace: inspect the reported old path, copy a reviewed
pending evidence/detail proposal into the current batch, or verify one explicitly
chosen old closure with `closure verify --state /absolute/old/closure.json`.
Never automatically import another worktree's state. Legacy checkout-local state
is reported for manual migration, never silently moved/deleted.

For approved wind-down, use the CLI's state clear command for exactly the current
identity payload after displaying its path; root lock/gc survive. Retain durable
files and delegation state. Manual GC works outside Git and is the cleanup route
when the plugin is no longer used. XDG cache drafts are regenerable. Create them with `state draft --root "$PROJECT" --json`; the returned directory and its generated identity record are scoped to the canonical repository/worktree. Renew a recovered draft with `state draft --id <id>` before reuse. Remove applied/cancelled drafts explicitly. Weekly GC expires recognized drafts after 30 days without writes/use, protects live or uncertain owners, and applies the seven-day recovery window to confirmed deleted/unregistered worktrees. Unknown legacy plugin-wide drafts are retained for explicit review. No plugin-wide usage history is maintained.

Explicit approved clear, after displaying/reviewing exactly this worktree path:

```sh
python3 "$LONG_HORIZON_SCRIPT" state clear --root "$PROJECT" --state-directory "$DISPLAYED_STATE_DIRECTORY" --json
```
