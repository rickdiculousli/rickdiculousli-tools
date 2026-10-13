# Lanes

Lanes let one active goal run as parallel streams of work. Each lane is a named
slice of the roadmap with its own worktree, owned paths and validators.
Lanes mode is optional and off by default; a repository without it sees no
change in behaviour or lint output.

## Roles

- **Lane session**: runs `status --lane <name> --json` (a pipeline's `lane next`
  does this), works only its selected task, in its own worktree, on its owned
  paths. Its durable handoff is its lane file.
- **Judge**: a session without a lane. `status` reports `mode: judge` and selects
  no task. The judge reads the `lanes` object, assigns or reassigns `Lane:`
  within its authority, closes milestones with evidence and edits the handoff.
- **Lander**: with `landing: "lander"`, the one role that runs the overlay's
  `## Integration` steps. Sessions submit their branch tip; the lander
  validates, records evidence with `--commit-in` and fast-forwards the target.

## Sessions

Resume under lanes mode: a session without a lane is the judge (`selection.mode`
is `judge`). It selects no task; it reads the `lanes` object (critical path,
per-lane eligible and blocked), assigns or reassigns `Lane:` within its
authority, closes milestones with evidence and edits the handoff. A lane session
runs `status --lane "$LANE" --json` and works only its selected task, in its own
worktree, on its owned paths.

Checkpoint under lanes mode with `landing: "lander"`: a lane session records
evidence and edits its lane file and goals as usual but does not run
`## Integration` steps. It submits its branch tip to the lander, which validates,
records evidence with `evidence record --commit-in <dir>` (below) and
fast-forwards the target. `closure record` steps are the lander's.

## Setup

When the user wants the active goal run as parallel lanes, `long-horizon:setup`
drafts the lane plan (lane name, owned globs, validators, host), then
`lanes.toml` (via `python3 -c` calling `long_horizon.lanes.scaffold(plan)` from
the resume scripts directory, or by hand from the example below), the `## Lanes`
section with `config`, the goal's `Parallel:` line, `Lane:` metadata, a lane
file per lane from a small template (`# Lane <name>`, `## Status`, `## Next`,
`## Asks`) and the handoff `Lanes:` line and links. It writes them only after
actual approval of the lane plan, as part of the reviewed draft. Migrate never
adds a `## Lanes` section: an absent section means lanes are off.

## Overlay: `## Lanes`

An optional section of `.agents/long-horizon.md`; keys are `key: <JSON value>`
as in the other sections (see [overlay](overlay.md)).

| Key | Values |
| --- | --- |
| `config` | string path to the lanes TOML, such as `.agents/lanes.toml`. **Lanes mode is on only when this key is set.** A `## Lanes` heading without `config` changes nothing |
| `assignment` | `"goals"` (default, the only value): `Lane:` metadata in goals is canonical |
| `task-completion` | `"lane"` (default), `"judge"` or `"user"`: who ticks tasks |
| `milestone-completion` | `"judge"` (default) or `"user"`: who closes milestones |
| `landing` | `"lander"` (default) or `"session"`: with `"lander"`, `## Integration` steps belong to the lander and sessions submit landings instead of committing, merging or pushing |
| `lane-files` | string directory, default `docs/lanes`: each lane has `<lane-files>/<lane>.md` with `## Status`, `## Next` and `## Asks` |

```markdown
## Lanes
config: ".agents/lanes.toml"
assignment: "goals"
task-completion: "lane"
milestone-completion: "judge"
landing: "lander"
```

## lanes.toml

Read with `tomllib` on Python 3.11+. On 3.10 a built-in subset parser
(`long_horizon/toml_subset.py`) handles comments, bare, quoted and dotted keys,
`[a.b]` tables, basic and literal strings, integers, simple floats, booleans and
nested, multi-line arrays. Inline tables, arrays of tables, multi-line strings
and dates are rejected with `lanes-config-invalid` naming the line; on 3.11+ a
date or time anywhere in the file is rejected too, so both readers agree.

long-horizon reads `[lanes.<name>]` tables (required, at least one) with an
optional `host` string (default `"any"`), `owns` string array and `validators`
string array, and an optional `[run]` table that status passes through. Other
tables (`[shared]`, `[gate]`, `[deps]`, `[rules]`) belong to the pipeline daemon
and are ignored. A lane name is a letter or digit followed by letters, digits,
`_` or `-` (at most 64 characters); `unassigned` is reserved.

```toml
[run]
project = "example"
stop_at = 92

[lanes.core]
owns = ["crates/app-core/**"]
validators = ["core-tests"]
host = "any"

[lanes.ui]
owns = ["crates/app-ui/**"]
validators = ["ui-tests"]

[lanes.native]
owns = ["probes/**"]
host = "native"
```

`long_horizon.lanes.scaffold(plan)` renders this file from a lane plan (name,
owned globs, validators, host); writing it by hand from the example is equivalent.

## Goals metadata

Details of the grammar are in [goals](goals-format.md).

- Task `Lane: <name>` (or `Lane: unassigned`) on the line after the task,
  indented or not. Required for every open task in an unfinished milestone of the
  active goal.
- Task `After: <task-id>[, <task-id>...]`: dependencies; they must name existing
  tasks and form no cycle.
- Goal `Parallel: lanes, <who>, YYYY-MM-DD`: the structured approval of running
  the goal as lanes; required. A lanes config committed or modified after that
  approval (committed after the commit that recorded the `Parallel:` line, or
  modified in the worktree) needs re-approval.

Outside lanes mode these lines parse and are ignored without findings.

```markdown
# Goal: Example — current
ID: ex
Parallel: lanes, user, 2026-10-13
Done when: validator:unit
## 1. Build — current
Done when: validator:unit
- [ ] [1.1] Core parser. (any)
  Lane: core
- [ ] [1.2] UI wiring. (any)
  Lane: ui
  After: 1.1
```

## Selection: `status --lane <name> --json`

`--lane` works only under lanes mode: without it the command exits 2
`invalid-environment`, and an unknown lane name exits 2 naming the declared lanes.
`selection` carries `lane` and a `mode`:

| Mode | Meaning |
| --- | --- |
| `selected` | `task` is the first open task with `Lane: <name>` whose `After:` tasks are all done, walking the active goal's unfinished milestones in roadmap order (not only the first), after handoff blockers and capability/readiness tags. `milestone`, `milestone_title` and `progress` describe that task's milestone. `blocked` lists the lane's earlier open tasks that were skipped, each with `reasons` (for example "Waits for 1.1 (open, lane core).") |
| `all-blocked` | the lane has open tasks and none is eligible; `blocked` lists them with reasons |
| `lane-done` | the lane has no open task; the judge may reassign |
| `dormant`, `manual`, `no-active-goal`, `awaiting-signoff` | the shared early modes, unchanged |
| `judge` | no `--lane` under lanes mode; `task` is null and the same early modes apply |

Every lanes-mode `status` and `lint` output also has a top-level `lanes` object:

| Field | Content |
| --- | --- |
| `config` | the configured path |
| `names` | sorted lane names |
| `hosts` | `{lane: host}` |
| `run` | the `[run]` table |
| `policy` | the `## Lanes` keys |
| `done`, `open`, `eligible` | task id lists over the active goal's unfinished milestones |
| `blocked` | `[{task, lane, reasons}]` |
| `critical_path` | the longest chain of open tasks through `After:` edges, earliest first; empty on a cycle |
| `per_lane` | `{name: {open, eligible, blocked, done}}`, including an `unassigned` bucket |

Text status prints a `Lanes:` line in the judge view and `(lane <name>)` after
Next. Exit codes are unchanged: 1 when any error finding is present, with
selection still reported.

## Lint findings

Reported by `status` and `lint`, only under lanes mode.

| Code | Severity | Meaning |
| --- | --- | --- |
| `lanes-config-missing` | error | the `config` file does not exist |
| `lanes-config-invalid` | error | TOML does not parse, has no `[lanes.<name>]` table or has a bad host |
| `lane-missing` | error | an open task in an unfinished milestone of the active goal has no `Lane:` |
| `lane-unknown` | error | `Lane:` names a lane the config does not declare and that is not `unassigned` |
| `after-missing` | error | `After:` names a task id that does not exist or is not a task |
| `after-cycle` | error | `After:` edges form a cycle; the message lists it |
| `parallel-approval-missing` | error | the active goal lacks `Parallel: lanes, <who>, YYYY-MM-DD` |
| `lanes-config-changed` | error | the tracked lanes config has uncommitted changes, or commits after the commit that last changed the `Parallel:` line |
| `mac-task-on-non-native-lane` | error | a task's capability tag equals a declared lane host other than `any` (such as `native`) but its lane runs on another host |
| `lane-file-missing` | warning | `<lane-files>/<lane>.md` does not exist for a declared lane |
| `lane-file-template` | warning | the lane file lacks `## Status`, `## Next` or `## Asks` |
| `handoff-lanes-line` | warning | the handoff lacks a `Lanes: <n> lanes, run <id>` line matching the lane count |
| `handoff-lane-link` | warning | the handoff `## Context` has no link to a lane's file |

## Handoff

The format is unchanged. Under lanes mode it should carry a
`Lanes: <n> lanes, run <id>` line near `Next:` and, in `## Context`, a Markdown
link to each lane file (for the lane `core`, a link whose target is `lanes/core.md`). The handoff is the judge's;
each lane's durable handoff is its lane file.

## Evidence and the lander

A repository-wide evidence index under the XDG cache caches each
trailer-carrying commit's validated records, shared by every worktree, so a
worktree that has rebased onto landed evidence reads it without revalidating
history (resolution itself still follows reachable history). The index is
written only under lanes mode and by `--commit-in`. It lives at
`<cache>/rickdiculousli-tools/long-horizon/<repo-key>/evidence/` with
`<commit>.json` per trailer-carrying commit and an `identity.json` recording the
Git common directory. It is a regenerable cache, so deleting it loses nothing.
Weekly `state gc` (see [state](state.md)) removes an entry whose commit object no
longer exists, and the whole index follows the seven-day recovery window once the
repository's Git directory is gone.

`evidence record ... --commit-in <dir>` is for the lander. After recording, it
commits exactly the record's detail file, with the `Accepted-Check:` or
`Accepted-Exception:` trailer as the message (`Evidence: <check> <outcome>`), in
checkout `<dir>`, which must belong to the same repository as `--root`. The
record must use a persistent `--log` route (`regenerate:` or http(s)) and be an
observed or delegated check, since only the detail file is committed; the
dangling commit is validated as history would read it before HEAD moves. It uses a
private index file, so staged work in that checkout is untouched, and never
amends, pushes or moves a ref other than that checkout's HEAD (compare-and-swap
from the HEAD it read). Output gains
`committed: {commit, committed_in, already_committed}`. When `<dir>` is the
`--root` worktree, the pending XDG copy is cleaned (`committed.cleanup`) and
`pending` is false. A record already carried by that checkout's history returns
`already_committed: true` and makes no commit. This is the one place `lh.py`
commits, under the lander's standing authorization; sessions keep the reviewed
commit flow. A retried `record` after cleanup needs a fresh `evidence prepare`.
