# State and recovery

On Windows, defaults are `%LOCALAPPDATA%/rickdiculousli-tools/long-horizon/state/`
and `%LOCALAPPDATA%/rickdiculousli-tools/long-horizon/cache/`. Explicit absolute
`XDG_STATE_HOME`/`XDG_CACHE_HOME` overrides win on every platform and keep the
`rickdiculousli-tools/long-horizon/` namespace directly below the override.
POSIX defaults remain `~/.local/state` and `~/.cache`. If LOCALAPPDATA is absent,
empty or relative, Python resolves `Path.home() / 'AppData' / 'Local'`. Empty or
relative XDG values select platform defaults. Every
process coordinating this plugin uses the same writable state root; failure is
reported rather than changing lock domain. A workspace sandbox must allow the
configured external XDG state/cache roots; use host permissions rather than
switching roots per invocation. The CLI rejects XDG roots inside this checkout, its Git directories or the installed plugin. No consumer runtime file goes in a
checkout, Git directory or installed plugin. Each plugin is self-contained.

Layout: permanent `state.lock`, `gc.json`, then SHA-256(canonical Git common dir)/
worktrees/SHA-256(canonical worktree)/identity.json, closure.json, evidence/*.json,
snapshots/*.json, manifests/*.json and trailers.txt. Snapshots hold only check
snapshots; closure manifests live in manifests/. Manifests and closure archives
that older versions left in snapshots/ are ignored by evidence prepare and expire
like other snapshots. Identity records canonical paths, device/inode,
birth time where available, volume, created/last mutation and first missing time.
Recreated directories cannot inherit old state; mutation quarantines an old
identity generation with a unique retired suffix. Unknown/unavailable identities
are retained. Status reports resolved state path and creates nothing.

Under lanes mode, and with `evidence record --commit-in`, the evidence index adds
a repository-scoped `<cache>/rickdiculousli-tools/long-horizon/<repo-key>/evidence/`
directory with `<commit>.json` per trailer-carrying commit and an `identity.json`
recording the Git common directory; see [lanes](lanes.md). It is a regenerable
cache, so deleting it loses nothing. Weekly `state gc` removes an entry whose
commit object no longer exists, and the whole index follows the seven-day recovery
window once the repository's Git directory is gone.

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
snapshots/manifests/drafts expire after 30 days without use; the next sweep removes them.
Cleanup confines recognized payloads, skips symlinks/unknown files and tolerates
partial failures. Committed evidence/goals/archives and live locks survive.

Recover explicitly during grace: inspect the reported old path, copy a reviewed
pending evidence/detail proposal into the current batch, or verify one explicitly
chosen old closure with `closure verify --state /absolute/old/closure.json`.
Never automatically import another worktree's state. A checkout-local
`.long-horizon/` directory is not part of the layout; lint reports it as
`layout-unexpected` for deletion after approval.

For approved wind-down, use the CLI's state clear command for exactly the current
identity payload after displaying its path; root lock/gc survive. Retain durable
files and delegation state. Manual GC works outside Git and is the cleanup route
when the plugin is no longer used. XDG cache drafts are regenerable. Create them with `state draft --root "$PROJECT" --json`; the returned directory and its generated identity record are scoped to the canonical repository/worktree. Renew a recovered draft with `state draft --id <id>` before reuse. Remove applied/cancelled drafts explicitly. Weekly GC expires recognized drafts after 30 days without writes/use, protects live or uncertain owners, and applies the seven-day recovery window to confirmed deleted/unregistered worktrees. Unknown legacy plugin-wide drafts are retained for explicit review. No plugin-wide usage history is maintained.

Explicit approved clear, after displaying/reviewing exactly this worktree path:

```sh
python3 "$LONG_HORIZON_SCRIPT" state clear --root "$PROJECT" --state-directory "$DISPLAYED_STATE_DIRECTORY" --json
```

Readiness reports are regenerable cache data. `cache:readiness.json` resolves to
`<worktree-cache>/readiness/readiness.json`; `paths --root PATH --json` discovers
this and the state/cache paths without creating files or acquiring the lock.
The startup helper publishes the returned cache identity alongside its report
under the shared lifecycle lock; see [readiness](readiness.md). Weekly GC recognises
JSON files in `readiness/` as well as drafts, preserves unknown files and applies
the same confirmed-deleted-worktree seven-day recovery window to readiness-only
caches. Existing readiness reports become unusable after 24 hours, but remain
until regenerated or their worktree cache is eligible for cleanup.
