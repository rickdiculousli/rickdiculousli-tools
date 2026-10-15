# Readiness version 1

```json
{"version":1,"checkout":"/absolute/current/worktree","generated_at":"2026-10-11T12:00:00Z","levels":{"fixtures":{"ready":true,"strength":"sha256","detail":"12 files"},"native":{"ready":false,"strength":"exists","detail":"app missing"}},"missing":[{"input":"reference app","needed_for":["native"],"recover":"tools/CAPTURE.md#app"}]}
```

`checkout` and `generated_at` are optional. Supplied checkout must match actual
worktree. Supplied timestamp is aware ISO-8601 and at most 24 hours old. Level
ready is boolean; strength is exists, size, sha256 or probed. Missing/malformed/
stale/wrong-checkout report makes required preparation unknown and offers
regeneration. Named levels map from all-of task tags; untagged/any tasks remain
usable without a helper. Ready proves preparation only. It supplies no validator
PASS, acceptance exception or permission to integrate.

Helpers and human input recovery belong to the consuming repository. Resume runs
only an actually authorized declared helper then re-reads status. CLI inspections
never run startup or quota. Quota is optional, once per resume, and informational.

Configure Startup with `readiness: "cache:readiness.json"`. The logical `cache:`
prefix resolves under `<cache_directory>/readiness/`, separate from setup drafts.
Nested relative `.json` paths are allowed; empty components, `..`, absolute or
Windows drive paths, backslashes, colons, NULs, trailing dots/spaces in components
and symlinks within the plugin cache are rejected. These rules also prevent
Windows path normalisation and alternate-stream escapes.
Any value without `cache:` is not read: status reports it as a `layout-outdated`
error and treats readiness as unknown.

The consumer helper discovers its destination without creating anything:

```sh
python3 "$LONG_HORIZON_SCRIPT" paths --root "$PROJECT" --json
```

Successful JSON has the normal `version: 1`, `command: "paths"`, `ok: true`,
`findings: []` envelope, plus `state_directory`, `cache_directory`,
`readiness_directory`, `readiness_path`, `cache_identity_path` and
`cache_identity`. Paths are absolute. `readiness_path` is null when unconfigured.
State/cache directories use the existing repository/worktree SHA-256 keys and
XDG/Windows defaults. Draft overlay discovery still uses the actual worktree’s
cache, never the draft directory. Discovery does not read goals or run startup.

Before writing, the helper must persist `cache_identity` at `cache_identity_path`
if absent, then atomically replace its JSON at `readiness_path`, creating parents
as needed. Retain an existing matching identity unchanged. Discovery rejects
mismatched identities; recover explicitly rather than overwrite them. Coordinate
producer writes with the permanent long-horizon state-root `state.lock` (POSIX
flock or Windows byte lock), re-run discovery under that lock, and keep the
transaction short. The root is `state_directory`’s third parent; never replace or
unlink its lock. This prevents weekly collection from racing helper publication.
No persistent state payload is needed for readiness-only use. The identity record
lets GC recognise readiness-only caches and enforce deleted-worktree recovery.

Missing readiness or missing/malformed/mismatched cache identity remains unknown
with a recovery instruction.
A report older than 24 hours stops being usable; this does not automatically delete the report. Weekly
GC retains existing worktrees’ readiness caches, and removes recognised JSON
readiness payloads after confirmed deletion and the seven-day recovery window.
Unknown files, missing identities and symlinks protect the cache from deletion.
