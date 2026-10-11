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
