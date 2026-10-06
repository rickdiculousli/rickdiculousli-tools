# Audit report JSON reference

Unknown keys and module types are errors. The renderer reports every error with its
JSON path and writes no HTML until the report is valid.

## Top level

```json
{
  "version": 1,
  "title": "Add retry to the uploader",
  "goal": "Retry failed uploads up to three times",
  "outcome": "partial",
  "blockers": ["Integration test needs network access"],
  "next_steps": ["Run tests/test_upload_integration.py with network"],
  "context": {
    "repo": "uploader", "branch": "retry", "base_commit": "a1b2c3d", "head_commit": "e4f5a6b",
    "session_id": "1234", "host": "claude-code 2.1.290",
    "started": "2026-10-05T19:02:00-07:00", "ended": "2026-10-05T19:40:00-07:00"
  },
  "modules": []
}
```

| Field | Rule |
| --- | --- |
| `version` | Must be `1` |
| `title`, `goal` | Required non-empty strings |
| `outcome` | `pass`, `partial`, or `blocked` |
| `blockers` | Non-empty list of strings, required unless outcome is `pass` |
| `next_steps` | Optional list of strings |
| `context` | Optional; every listed key is an optional string |
| `modules` | Required list, rendered in order |

## Fields shared by every item

Every step, file, run, and claim accepts:

| Field | Rule |
| --- | --- |
| `source` | `observed` or `asserted` (default `asserted`) |
| `evidence` | String; required and non-empty when `source` is `observed`. Shown as an agent-quoted excerpt, truncated after 2,000 characters |

Every module accepts an optional `title`.

## `timeline`

```json
{"type": "timeline", "steps": [
  {"kind": "read", "label": "Read uploader.py", "phase": "Explore"},
  {"kind": "run", "label": "Run unit tests", "phase": "Verify", "status": "fail",
   "detail": "test_retry_backoff failed", "resolved": true,
   "source": "observed", "evidence": "FAILED tests/test_upload.py::test_retry_backoff"}
]}
```

| Field | Rule |
| --- | --- |
| `kind` | `read`, `search`, `edit`, `run`, `think`, or `other` |
| `label` | Required string |
| `status` | `ok` (default), `fail`, `warn`, or `retry` |
| `phase`, `detail` | Optional strings |
| `resolved` | Optional boolean, only on `fail` or `warn` steps a later action fixed |

## `files`

```json
{"type": "files", "files": [
  {"path": "src/uploader.py", "change": "modified", "added": 24, "removed": 3,
   "hunks": ["@@ -10,3 +10,8 @@\n-    send(data)\n+    for attempt in range(3):\n+        send(data)"]},
  {"path": "src/upload.py", "change": "renamed", "from": "src/send.py", "added": 0, "removed": 0},
  {"path": "assets/logo.png", "change": "added", "added": 0, "removed": 0, "binary": true}
]}
```

| Field | Rule |
| --- | --- |
| `path` | Required, unique across all files modules |
| `change` | `added`, `modified`, `deleted`, or `renamed` |
| `added`, `removed` | Required non-negative integers |
| `from` | Required when `change` is `renamed` |
| `hunks` | Optional list of unified diff strings (first 10 shown, 40 lines each) |
| `generated`, `binary` | Optional booleans |

## `runs`

```json
{"type": "runs", "runs": [
  {"command": "pytest tests/test_upload.py", "exit": 1, "expect_fail": true, "duration_ms": 840,
   "excerpt": "1 failed, 4 passed"},
  {"command": "pytest", "exit": 0, "duration_ms": 2100, "source": "observed", "evidence": "12 passed",
   "suites": [{"name": "unit", "passed": 12, "failed": 0, "skipped": 0}]}
]}
```

| Field | Rule |
| --- | --- |
| `command` | Required string |
| `exit` | Required integer |
| `expect_fail` | Optional boolean for runs meant to fail |
| `duration_ms` | Optional non-negative integer |
| `suites` | Optional list of `{name, passed, failed, skipped}` |
| `excerpt` | Optional output string (first 60 lines shown) |
| `resolved` | Optional boolean, only on a failed run (nonzero exit without `expect_fail`, or zero exit with it) |

## `claims`

```json
{"type": "claims", "claims": [
  {"claim": "Uploads retry three times", "status": "verified", "source": "observed",
   "evidence": "test_retry_three_times PASSED", "refs": {"runs": [2], "files": ["src/uploader.py"]}},
  {"claim": "Backoff is exponential", "status": "unverified", "refs": {"steps": [2]}}
]}
```

| Field | Rule |
| --- | --- |
| `claim` | Required string |
| `status` | `verified` (must be `observed`), `unverified`, or `refuted` |
| `refs` | Optional `{"steps": [n], "runs": [n], "files": [path]}`; numbers are 1-based across the whole report and must exist |

## `figure`

Every figure needs `kind` and `alt` (a sentence describing it), plus the data for its kind.

```json
{"type": "figure", "kind": "bar", "title": "Test time (s)", "alt": "Seconds per test suite",
 "bars": [{"label": "unit", "value": 2.1}, {"label": "integration", "value": 41, "status": "warn"}]}
```

```json
{"type": "figure", "kind": "tree", "alt": "Modules touched",
 "tree": {"label": "src", "children": [{"label": "uploader.py", "status": "warn"}]}}
```

```json
{"type": "figure", "kind": "flow", "alt": "Upload request path",
 "flow": {"nodes": [{"id": "a", "label": "client"}, {"id": "b", "label": "uploader", "status": "fail"}],
          "edges": [{"from": "a", "to": "b", "label": "send"}]}}
```

```json
{"type": "figure", "kind": "custom", "alt": "Retry timing diagram",
 "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 100 20\"><rect width=\"40\" height=\"20\"/></svg>"}
```

| Kind | Data |
| --- | --- |
| `bar` | `bars`: non-empty list of `{label, value ≥ 0, status?}` |
| `tree` | `tree`: `{label, status?, children?}` recursively |
| `flow` | `flow`: `nodes` `{id, label, status?}` with unique ids; `edges` `{from, to, label?}` naming existing nodes, no cycles |
| `custom` | `svg`: a string that must declare `xmlns="http://www.w3.org/2000/svg"`; embedded as an image, byte for byte |

Figure `status` values are `ok`, `fail`, `warn`, or `retry`.
