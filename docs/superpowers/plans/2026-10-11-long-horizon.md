# Long-horizon implementation plan

**Status:** ready for implementation. This is a plan, not an installed plugin or a
claim of completed validation. All design decisions needed for v1 are resolved
below; project-specific interview answers remain inputs to consuming-repository
setup, not unanswered implementation questions.

**Goal:** ship `long-horizon` 0.1.0 with shared setup, resume and checkpoint skills,
a deterministic Python CLI, durable acceptance, repeatable setup and honest batch
closure on Claude Code and Codex.

**Spec:** [Long-horizon design](../specs/2026-10-11-long-horizon-design.md).

**Implementation:** Python 3.10+ standard library, Git and Markdown. Implement the
numbered tasks in order, using focused disposable-repository tests. No worker
agents, host hooks, scheduler, network client, runtime dependency or consumer
build is required. Existing repository instructions govern execution; this plan
introduces no worktree, model or approval requirement of its own.

## Resolved contracts and design clarifications

These decisions complete the specification. Fold these clarifications into its
relevant sections during Task 1 so implementation has one consistent contract.

### 1. Layout, versions and compatibility

Use the spec's plugin layout, plus a small `long_horizon` package next to
`resume/scripts/lh.py`. The entry point only imports `long_horizon.cli.main`.
Modules are `model`, `overlay`, `goals`, `git`, `state`, `readiness`, `handoff`,
`scope`, `delegation`, `evidence`, `gate`, `closure`, `lint` and `cli`; combine
small modules if doing so keeps responsibilities clear. Everything ships inside
`plugins/long-horizon/`. Setup/checkpoint locate the entry point relative to
their installed skill directory (`../resume/scripts/lh.py`), quoting paths.
Consumers may declare `LONG_HORIZON_SCRIPT` or a script path; never search a
versioned cache or assume this checkout. Names are plugin-qualified in guidance
so `long-horizon:setup` cannot be confused with `delegation:setup`.

Append `plugins/long-horizon` to `catalog.json`, preserving existing order.
Initial version is `0.1.0`. Generate both manifests and marketplaces through the
existing generator; it needs no new host adapter. Change delegation's composition
guidance only, with its current version bumped from `0.6.2` to `0.6.3` if still
current at implementation time. Re-read that version before editing. Quota
content remains unchanged. Both hosts receive the same files.

### 2. Runtime state follows the repository's XDG rule

The spec's worktree-local `.long-horizon/closure.json` conflicts with contributor
guidance requiring plugin state under XDG. Use:

```text
${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/long-horizon/
  <sha256(canonical-git-common-dir)>/<sha256(canonical-worktree-root)>/
    closure.json
    evidence/<content-id>.json
    snapshots/<content-id>.json
    trailers.txt
    state.lock
```

Those files belong to one worktree and contain no live agent mappings. No cache
is needed initially. `status --json` exposes the resolved state directory and
`closure verify` accepts `--state PATH` for importing a specifically chosen
closure record. Do not discover/import another worktree's state automatically.
Replace `.long-horizon/` instructions in the spec/templates with this contract;
do not add a repository ignore rule for a directory we do not create. Legacy
`.long-horizon/` state may be reported with a migration instruction, but never
silently moved or deleted. Wind-down clears only this plugin's resolved worktree
state after showing its path; durable files and delegation state survive.

Readers never create state. Writers use an exclusive lock, atomic replacement
in the same directory and restrictive file modes where supported. Use the same
stdlib locking pattern as delegation's `file_lock.py`: `fcntl.flock` on POSIX
and `msvcrt.locking` on Windows, locking one fixed byte at offset zero with a
nonblocking attempt and a bounded retry loop. Always unlock and close the same
handle, including on exceptions; distinguish contention from other I/O errors.
Bundle the small lock helper inside long-horizon rather than importing an
installed delegation package. POSIX and Windows support state writes; report
an unsupported-lock diagnostic only when neither backend is available. Failed
writes leave the old record valid.
No consumer state is written beside installed scripts.

### 3. Overlay grammar and defaults

Keep a human-readable Markdown overlay; no YAML parser. An optional
`## Schema` contains `1`. Under the spec's named headings, each nonblank line is
`key: <JSON value>` with an optional leading `- `. Paths and commands are JSON
strings, maps/arrays are JSON values, booleans are JSON booleans. Normalize
heading case, CRLF and surrounding whitespace, preserve value case, reject
duplicate headings/keys and wrong value types. A title and blank lines are
allowed; comments are full lines starting `<!--` and ending `-->`. Unknown keys
or headings are errors with a suggested spelling. Missing optional sections use
defaults, so the quick setup can be this small:

```markdown
# Long-horizon
## Goals and ownership
path: "docs/goals.md"
## Integration
steps: ["validate", "commit", "merge", "push"]
target: "main"
remote: "origin"
authorization: "User approved standing batch closure on 2026-10-11."
```

That integration example is written only after approval. With no recorded
integration section, commit/merge/push/sync remain unauthorized. Omitted state
means `active`; omitted sign-off means `user`. Other defaults: handoff
`docs/handoff.md`, archive `docs/goals-archive`, handoff budget 80 lines, one task
or one blocker resolution per batch, quota off, readiness absent, no capability
requirements for `any`, agent task refinement/completion and milestone completion,
user milestone order/scope/criteria and goal sign-off. Non-code defaults are the
actual configured goals, handoff, findings and archive paths, not every Markdown
file. Evidence policy, overlays and activation instructions are not implicitly
excluded from acceptance-policy freshness.

Reference documentation defines every key and type. Ownership keys separate
`milestone-policy`, `task-refinement`, `task-completion`, `milestone-completion`
and `goal-signoff`. Integration defines `steps`, `target`, `remote`, optional
`sync`, `stop-conditions` and an authorization description. Evidence defines
`checks`, each with `scope`, `inputs`, `domain`, `allowed-skips` and optional
`validator`; input definitions contain an authorized cheap read-only command,
a timeout and recovery route. Delegation and quota script paths may be literal
or named environment variables; an explicitly configured missing value is a
finding, never a reason to guess a cache path. Startup's command and permitted
effects are descriptive authorization for the skill, not a command `status`
executes. Allow external context/recovery links, but managed goals/handoff/archive
paths must stay inside the current checkout, including through symlinks.

### 4. Goals grammar, manual fallback and ownership

Parse only headings and task lines outside fenced code. Support the spec's
explicit `# Goal:` headings and a single implicit goal for legacy roadmaps.
Milestones are numbered level-2 headings; `## Parked` is never a milestone.
Retain original text/line locations for diagnostics and surgical edits. Marker
customization is an explicit mapping in `Goals format`; regex injection is not
supported. Terminal siblings are done, shelved or dropped; a later goal can
therefore be current after shelving an earlier one. Milestones only use
current/done/open. IDs are unique across the goals file; missing task IDs use
`<milestone-number>-<first-12-sha256-of-normalized-task-text>` with a warning and
collision detection. Capability tags are comma-separated trailing parentheses;
all listed tags and all mapped levels must be satisfied. Unknown tags are
ineligible with a fix, never treated as `any`.

Add parseable `Checks: ["validator:unit", "observation:review"]` after `Done when`
when prose contains requirements not already expressed as named check tokens.
All named tokens in `Done when` are also required; `Checks` cannot weaken them.
Free-text acceptance without a named check is displayed but cannot auto-pass a
gate. Setup asks for check annotations without rewording adopted criteria.
Completion citations are adjacent `Evidence: <task-id>=<evidence-id-or-commit>`
lines; multiple references are comma-separated. A commit citation must resolve to
an ancestor of HEAD or the proposed batch commit and have an inspectable change;
it is task evidence, not an automatic milestone PASS.

An unparseable roadmap produces a warning, `selection.mode=manual`, and no
automatic selection. It must not strand independent work. A gate needing that
roadmap fails with the exact annotation needed; a malformed overlay or parsed
inconsistent hierarchy is an error. Current markers are optional; when absent,
selection infers the first incomplete eligible hierarchy. Two current markers,
duplicate IDs, checked milestones with open tasks and out-of-order completion
are errors. An archived done goal may have no inline children only when its
record validates the completed milestone summary and evidence.

Selection overrides let agents do requested work immediately and log `Override:`.
They do not silently permit false acceptance or change ownership. Off-milestone
work can record evidence while the later milestone stays open. Authorized scope,
order or criteria changes have an adjacent `Policy-Approval:` entry identifying
who approved what; `gate --base` reports them and checks the overlay's ownership
setting. Text cannot authenticate a person: skills must obtain actual user
approval when reserved to the user. Lint/gate verify the record exists and is
consistent, not the user's identity. Sign-offs and exceptions have the same limit.

### 5. Readiness and preparation stay distinct from acceptance

Readiness JSON follows the spec's version-1 format; accept `exists`, `size`,
`sha256` and `probed` strengths. Add optional `checkout` and `generated_at` fields;
when checkout is supplied it must match this worktree. Missing/malformed reports
make required capabilities unknown, with recovery instructions. `ready: true`
satisfies only its named preparation level, never a validator. Map tags to named
levels, independent of machine nicknames. With no helper/report, untagged/`any`
tasks remain selectable; tags requiring readiness do not.

`lh.py` never launches startup or quota. Resume runs an authorized helper, then
calls status again. It makes at most one quota call when enabled and a declared
script is available. A missing plugin or failed quota read is informational and
uses the default batch; it never blocks. Default batching stays one task/blocker
resolution; low remaining usage shrinks work, higher usage alone does not expand
it beyond recorded policy. Readiness generation and human recovery remain
consuming-repository responsibilities.

### 6. Evidence lifecycle closes the pre-commit gap

A gate must inspect acceptance before committing, and an evidence ID cannot
contain the hash of the commit carrying it. Add `evidence prepare <check>` to
capture a content-addressed before-snapshot; it does not run the check. The skill
runs the authorized validator/command, then invokes `evidence record <check>
--snapshot <id>` with its outcome and provenance. Record recomputes the scope,
policy and external inputs, refuses PASS if they changed, and emits a canonical
trailer plus a pending immutable evidence document. Record does not commit,
stage, amend or create a second validator ledger. Snapshot/record are
idempotent for identical content; an existing ID with conflicting content is an
error. Pending records carry no live agent IDs.

Each canonical record includes check name, outcome, scope digest, acceptance
policy digest, all input digests, domain, claim class, observed command or
validator name, delegation result ID/tree when applicable, log recovery route
and result/log digest. Its ID is SHA-256 of canonical sorted-key JSON, excluding
the carrying commit, presentation timestamp and derived detail-file location.
The record does not hash its own ID or a path containing that ID. Log routes
must be independent of the evidence ID; copied logs may be named by their own
log-content digest. Trailers retain the spec's
fields and add `id`, `policy`, `claim` and `detail`:

```text
Accepted-Check: id=<sha256> name=unit outcome=PASS scope=<sha256> policy=<sha256> inputs=none domain=unit-v1 ledger=none claim=observed detail=docs/evidence/<id>.json log=docs/evidence/<id>.log
```

Use `shlex` quoting for trailer values, including paths with spaces. Repeated
fields or malformed values fail parsing. Detail records are durable tracked
JSON (default `docs/evidence/<id>.json`, configurable), with compact logs or a
specific persistent retrieval/regeneration route. The record command outputs
these files for review and writes only its XDG pending copy; the checkpoint
skill writes the proposed durable files. Exclude this configured evidence sink
from default code scope to avoid self-invalidation, but include acceptance
policy in the separate policy digest. No scratch log path alone qualifies.

`gate` and `evidence find` read reachable commit trailers plus explicit pending
records for this batch. Commit message assembly uses `--trailers-file` (output
from record) and `git commit --file <message>`; no amend or automatic empty
commit. After committing, checkpoint resolves each pending ID in that exact
commit before removing the pending copy. An interrupted cleanup is harmless:
deduplicate by ID. A fresh clone needs only committed trailers/detail records.
If a task/goal changes its status without code edits, its normal documentation
commit can carry trailers. Pending acceptance is reported as pending, never
already committed.

An allowed skip is only acceptable within its declared domain/condition; it
never becomes PASS. An explicit accepted exception is separately recorded:
`Accepted-Exception: id=<id> check=<name> target=<goal-or-milestone-id>
reason=<quoted-text> by=<user> policy=<digest>`. Require a reason, target and
matching criteria revision. It covers only that check/target, is listed in the
completion record, and cannot waive sign-off or authorize remote operations.
Non-delegation results are observations, not forged `checked` results. Human
judgment uses `observation:<name>` and an explicit dated reviewer record.

### 7. Scope and inputs are deterministic without changing Git

Enumerate tracked files plus untracked non-ignored files with NUL-delimited Git
commands. Include deletions, executable mode, symlink target and submodule commit;
refuse fresh evidence for a dirty/unavailable submodule unless its contents are
explicitly modeled as inputs. Hash the canonical sorted path/mode/blob-ID list
with SHA-256. Blob IDs use Git's object format and `hash-object --stdin` without
`-w`; neither the real index nor object database changes. A tracked deletion is
a missing entry in the current snapshot, so deletion changes the digest.
Unreadable files and unresolved index conflicts fail closed.

Use Git pathspec matching for includes/excludes, with repository-relative paths;
never shell globbing. Default scope is everything except declared non-code and
evidence-sink paths. Scope policy changes, required checks, domains, allowed
skips, input definitions and the referenced validator policy change a separate
canonical policy digest even if code scope stays identical. Documentation edits
outside those policy definitions do not invalidate an expensive check.

The per-check policy digest includes its normalized required criteria text and
check list, but excludes checkboxes, current/done markers, sign-off dates, task
refinement text and archive-link presentation. Moving unchanged accepted
criteria into the archive preserves that digest. Changing criteria, domain or
input definitions does not. Checkpoint status edits therefore do not make their
own evidence stale. Closing a goal preserves the historical evidence accepted
at each milestone; only the goal's own required checks must be fresh again,
unless its criteria explicitly require revalidating earlier milestones.

External input commands return one lowercase SHA-256 token; reject failures,
timeouts, extra output and undeclared inputs. They are executed only with
`--probe-inputs` on prepare/record/find/gate under existing authorization.
Default status/lint perform no probes and show external freshness as unknown.
Before/after probes are required for externally dependent PASS. Empty inputs
are `none`; required inputs cannot be omitted. Snapshot output cached in XDG is
not proof of current external state. Every unknown/stale/missing distinction
appears in text and JSON with a recovery command.

### 8. Delegation adapter uses the actual 0.6.2 interface

The current checker supplies `tree`, `lint`, `pending --json`, and `query
--delegation <id> --tree current --json`. `tree` and `lint` are text output;
do not assume nonexistent JSON flags or a global query. Call them through an
argv list using `sys.executable <configured-check.py> --root <root> ...`.
Import no code from its installation and copy no ledger implementation.
`evidence record --delegation <id> --result <result-id>` queries that delegation
and requires the named registered validator, stable true, ok true, exit 0,
no timeout and the checker-provided current tree. The prepare snapshot carries
the checker tree too. Preserve the result/log hash and host/domain limits.
An arbitrary `check.py exec` observation has no registered validator name and
cannot satisfy `validator:<name>`.

Immediately turn the stable current result into scoped durable evidence before
checkpoint changes the goals/handoff. Later docs-only edits can reuse that
durable scoped acceptance, clearly labeled historical provenance; they are not
a new current-tree delegation PASS. Current claims explicitly requesting a
checked delegation result still use the checker's exact-tree query. A missing
ledger does not erase verifiable committed scoped acceptance, and it cannot
recreate a current checked result. Wrong/malformed/unavailable checker output
is a finding. Pending workers block checkpoint closure until delegation hands
them back; the plugin never closes or resets them itself.

### 9. Closure is a resumable record, not an automation engine

`closure record --batch <id> --step <name> ...` is an added local bookkeeping
command. It records policy fingerprint, branch/remote, exact batch commit,
intended ordered steps and separately observed outcomes, with version 1.
`closure verify` never commits, merges, fetches, pushes or syncs. Skills perform
only authorized operations, update records after observing their outcomes and
use the verifier before a retry. A batch ID derives from its evidence IDs and
changed-path/content-digest manifest; retries reuse it. A changed policy/target or different
batch needs an explicit new record, not overwriting successful prior steps.

Committed means the exact batch commit exists and is reachable from the local
batch history; record its changed paths and check they include the intended
owned changes. Merged means it is an ancestor of the configured local target
branch, whether by fast-forward or merge commit. Squash integration requires a
new explicit integrated-commit mapping and review of the mapped content; never
infer equivalence from a commit message. Pushed means the integrated commit is
contained in the configured remote-tracking target ref, qualified **as of the
local remote-ref observation**. Report the last observed ref OID and observation
time; Git alone cannot establish the server's present state or last fetch time.
Missing/stale refs are unknown, not successful remote closure. A successful push
with its recorded result is distinct from this local ancestry verification.
Host sync is an observed claim and stays unverified by Git.

The skill preserves unrelated dirty files, stages only owned paths and does
not switch branches/worktrees, rewrite history or force a merge/push. If the
target checkout is dirty/unavailable, merging is a remaining operation with a
precise remedy. Retry from the first unfinished step; already merged commits
and identical records are no-ops. Post-commit push/sync results live in XDG and
chat, avoiding a recursive follow-up commit to claim the previous push. Another
host can reconstruct committed/merged/ref facts; unfinished sync or unsaved
local closure cannot be invented. Setup's closure choice supplies standing
authorization only for the named operations and stop conditions.

### 10. Goal lifecycle and mechanical repair

Archive names use UTC date and a normalized goal slug; existing records for the
same goal are updated rather than duplicated. Distinct same-slug goals add their
stable goal-ID suffix. Add `ID:` to explicit goal metadata during approved setup;
legacy implicit goals derive an ID from heading content with a warning. Records
have a version-1 JSON metadata fence plus readable outcome, per-milestone
criteria/evidence/exceptions, limitations, refuted approaches and follow-ups.
A record in progress does not prove completion. Gate checks all expected
milestones and the goal's own criteria against it before archival compression.
Default sign-off keeps the goal current and selects no new goal work when all
milestones are done; brief lists **Needs you: sign off**. After actual approval,
add `Signed-off: <who>, <UTC-date>`, mark done and retain the ID/sign-off/archive
link. The archive metadata preserves children removed from the roadmap.

Shelving/dropping requires actual user instruction, a reason and a record of
where work stopped; it claims no completion. Unshelving reopens preserved work,
not a fresh survey. Wind-down/add-goal/update are repeatable surgical changes:
one pointer, one import, one overlay, no duplicate archive/parked entries.
Replace or remove the handoff only as approved. Never remove unrelated sections
from `AGENTS.md`/`CLAUDE.md` or delegation. Setup discovers overlays on default
and other local branches/worktrees without fetching; prefer current checkout,
then default branch, then a unique other version. Multiple different candidates
become one explicit choice in the draft; never silently choose an arbitrary log
entry. Already-approved identical setup is a no-op, not another interview loop.

`lint --fix` prints a diff; `--fix --apply` is the explicit approval to apply
only unambiguous mechanical changes. Missing markers/IDs/headings can be added;
conflicting current markers, ownership changes and destructive edits require
manual repair. Never repair accepted task text/criteria or infer missing PASS.
Check the input file digest before application, preserve line endings and
unrelated prose, and make a second run produce an empty diff.

## Public CLI and result contract

Every subcommand supports `--root`, `--overlay` and `--json` in the documented
position after the subcommand. Paths resolve from the Git worktree root, except
an explicit draft overlay's managed relative paths resolve from that draft's
base directory with `--draft-root`. This lets setup put its entire draft in an
XDG draft directory and dry-run it without writing the repository. Git identity
always comes from the actual checkout. `--goals` and `--handoff` can override
only those input paths for a dry-run. Never treat a draft as active policy.

Commands:

```text
lh.py lint [--fix [--apply]]
lh.py status [--brief]
lh.py evidence prepare <check> [--probe-inputs]
lh.py evidence record <check> --snapshot <id> --outcome <outcome> ...
lh.py evidence find [<check>] [--probe-inputs]
lh.py gate [--base REV] [--probe-inputs] [--pending <id> ...]
lh.py closure record --batch <id> --step <step> ...
lh.py closure verify [--state PATH]
```

Additional argument contracts:

- `evidence prepare` accepts `--attempt <identifier>`, defaulting to a generated
  identifier it prints for reuse. Preparing with that same identifier and
  unchanged scope/inputs reuses the snapshot; changed contents under that
  identifier are an error. A genuinely new validator execution gets a new
  attempt. Record includes that attempt in its canonical content, distinguishing
  a new run from a repeated invocation to save an existing result.
- `evidence record` accepts `--outcome PASS|FAIL|SKIP|UNSTABLE`, `--domain`,
  `--log <recovery-route>`, `--detail <tracked-path>`, `--probe-inputs` and
  `--trailers-file <output-path>`. Domain/detail default to overlay settings;
  log is required. Solo provenance requires `--command <observed-command>` and
  `--exit <integer>`; PASS requires exit 0. Delegated provenance instead requires
  `--delegation <id> --result <id>` and derives command/exit from checker output.
  Human observations instead use `--reviewer <name> --review-note <tracked-path>`;
  the skill confirms the actual review. These three provenance modes are
  mutually exclusive. External checks require `--probe-inputs` on both prepare
  and record. Explicit trailer-file output is atomic and idempotent; no write
  to Git's commit message or index occurs.
- Accepted exceptions use `evidence record <check> --exception --target <id>
  --reason <text> --by <user>`, after actual user acceptance. This mode emits
  an exception trailer/detail instead of PASS and needs no validator snapshot;
  it fingerprints the target's current criteria and carries no check result.
- `closure record` accepts `--step validate|commit|merge|push|sync`,
  `--outcome success|failed|pending`, `--commit <oid>`, optional
  `--integrated-commit <oid>`, `--observation <text>` and
  `--manifest <reviewed-paths-and-digests.json>`. The first record requires the
  manifest and derives target/remote/steps from approved policy. Success for a
  Git step requires its relevant OID; sync requires an observation. Verify
  derives Git facts again rather than trusting success strings. Validation
  references accepted evidence IDs in the manifest rather than running checks.
- `gate --pending <id>` repeats for each explicitly included pending check or
  exception; it never silently accepts every worktree scratch record.

The archive metadata fence has `version`, `goal_id`, `status`, `outcome`,
`milestones` (ordered IDs, criteria, evidence IDs and exceptions), `goal_checks`,
`signoff`, `limitations`, `refuted` and `followups`. Shelved/dropped records also
retain their original roadmap section and `reason`, so resumption can restore
it without synthesizing tasks. The batch manifest has `version`, `base`,
`paths` (relative path, content digest or deletion), and `evidence_ids`.

JSON uses `version: 1`, `command`, `ok`, `findings` with severity/code/path/line/
message/remedy, and command-specific structured data. Exit 0 means successful
inspection/no blocking findings, even with warnings, no eligible task, no active
goal or no evidence. Exit 1 means blocking consistency/gate/freshness findings
or unverified required closure. Exit 2 means invalid usage/environment. Missing
evidence is data in `find`, but a required missing item fails `gate`. All
exceptions become concise diagnostics; no traceback for normal user errors.
`--json` prints only JSON to stdout; stderr is for invocation/environment errors.
Text is compact, with commands/sentences that fix every finding.

`gate --base` defaults to HEAD, comparing the working proposed goals to the
committed version. CI/integration passes the explicit pre-batch base so already
committed changes are checked. On an unborn branch use an empty base and treat
adopted completion as needing explicit existing evidence/limitations; setup
must not manufacture retrospective PASS. Gate checks newly completed tasks,
milestones and goals, completion records and owned policy changes, not every
legacy checkbox on every invocation. Criteria edits invalidate evidence via
policy digest. Existing false structural claims are still lint errors.

## Implementation tasks

### Task 1: Freeze formats, fixtures and plan clarifications

**Files:** modify the design spec; create
`plugins/long-horizon/skills/resume/reference/{overlay,goals-format,readiness}.md`,
`plugins/long-horizon/skills/checkpoint/reference/evidence.md`,
`tests/long_horizon_support.py` and `tests/fixtures/long_horizon/`.

- [ ] Fold the ten resolved contracts above into the spec. Keep the original
  purpose/boundaries and label changes as planning clarifications, not execution.
- [ ] Document full overlay keys/types/defaults and an actual quick/full example,
  grammar, JSON outputs, archive metadata, readiness and trailer formats. Provide
  examples with spaces, explicit/implicit goals and terminal/awaiting-signoff states.
- [ ] Build fixture helpers for disposable Git repos, local bare remotes, linked
  worktrees, XDG directories, draft directories and a controllable stub checker.
  Set local Git identity; never use normal user profiles or network remotes.
- [ ] Encode golden expected selection/freshness/gate/closure outputs from the
  spec. Check fixture expectations against the resolved contracts before code.

**Done when:** every ambiguous implementation choice in the spec points to a
concrete format or policy here; fixtures cover both normal and recovery flows.

### Task 2: Entry point, Git discovery, state and overlay

**Files:** `resume/scripts/lh.py`, `resume/scripts/long_horizon/{__init__,model,
cli,git,state,overlay}.py`; `tests/test_long_horizon_overlay.py`,
`tests/test_long_horizon_state.py`.

- [ ] Implement frozen data models, typed findings and CLI error handling.
- [ ] Discover main/linked worktrees, branch, dirty paths, common dir and default
  branch. Prefer configured target, local remote HEAD, then an unambiguous
  main/master branch; ambiguity asks for configuration, with no network request.
  Handle detached HEAD, unborn repos, paths with spaces and subdirectories.
- [ ] Implement XDG resolution, portable POSIX/Windows locks, atomic records
  and read-only discovery. Close temporary replacement-file handles before
  `os.replace` so atomic writes also work on Windows.
- [ ] Parse overlays/defaults and validate path confinement and literal/env
  script resolution. Report referenced files missing; optional nonexistent
  readiness/archive outputs have warnings/recovery rather than setup dead ends.
- [ ] Add draft-root/path overrides and a valid no-overlay status response.

**Validate:** `python3 -m unittest discover -s tests -p 'test_long_horizon_overlay.py' -v`
and the corresponding state test file. Verify real index/branch/unrelated bytes
are unchanged; simultaneous writes serialize, and interrupted writes recover.
Exercise both lock backend branches with mocks for acquisition, contention,
timeout, unexpected I/O errors and exception-safe release. Run actual Windows
process-contention/atomic-replacement checks when a Windows runner is available;
record them as untested if unavailable, without disabling Windows writes or
presenting mocked coverage as native Windows validation.

**Done when:** a minimal/default or full overlay is deterministic and bad policy
cannot authorize dependent actions; inspection creates no runtime state.

### Task 3: Goals, readiness, selection and brief status

**Files:** modules `goals.py`, `readiness.py`; tests
`test_long_horizon_goals.py`, `test_long_horizon_status.py`.

- [ ] Parse hierarchy/markers/IDs/criteria/context/parked/evidence/sign-off/archive
  metadata with line locations and tolerant prose preservation.
- [ ] Enforce consistency, including completed archive summaries and terminal
  earlier goals. Distinguish unparseable-manual from parsed-inconsistent.
- [ ] Parse readiness and select the first eligible unblocked task in the first
  incomplete milestone of the first active goal, without skipping milestones.
- [ ] Implement awaiting-signoff, dormant, no-active-goal and all-blocked states.
- [ ] Emit full status and brief goal/milestone/task progress and **Needs you**:
  pending decisions, sign-off, human-only steps, missing inputs, unfinished closure.
  Output only the current section/context links; do not print the full history.

**Validate:** focused goals/status suites: multiple goals, inherited implicit goal,
missing IDs, duplicate IDs, fenced examples, unknown/all-of tags, stale report,
blocked-first/all-blocked, archived goals, shelved/dropped, no overlay/dormant.

**Done when:** golden selections match in main and linked worktrees and read-only
status never runs startup/tests/quota or mutates goals.

### Task 4: Handoff parsing, staleness, pointer lint and repair

**Files:** `handoff.py`, `lint.py`; tests `test_long_horizon_handoff.py`,
`test_long_horizon_lint.py`.

- [ ] Parse Blockers by task ID/reason/recovery/date, pending decisions, parked
  ideas, overrides and durable context links. Unknown task references warn.
- [ ] Compute staleness from the last handoff commit, relevant later commits,
  goals changes and current dirty handoff. An uncommitted/missing handoff is
  explicitly new/missing, not deceptively current. Non-code-only unrelated
  commits do not create a stale-code finding.
- [ ] Check pointer reachability from AGENTS and CLAUDE, including `@AGENTS.md`
  and bounded recursive relative imports; detect missing imports/cycles.
  Require pointers only for an active installed setup; dormant and explicit
  draft checks do not fail because their activation has not been written.
- [ ] Enforce no credential-shaped values or live agent IDs in the handoff with
  narrow documented patterns; allow durable delegation result IDs. Diagnostics
  redact matches and do not repeat sensitive strings.
- [ ] Implement warning budgets/template gaps and diff-only mechanical repair.
  Approved apply checks original digests and is idempotent.

**Validate:** focused suites for merge histories, dirty handoff, pointer cycles,
80-line budget, error/warning exit codes, redaction, CRLF and second-run no-op.

**Done when:** lint distinguishes convenience warnings from unsafe selection or
acceptance errors, and repairs preserve unrelated content.

### Task 5: Scope snapshots and durable solo evidence

**Files:** `scope.py`, `evidence.py`; tests `test_long_horizon_scope.py`,
`test_long_horizon_evidence.py`.

- [ ] Implement Git pathspec matching and content/mode/deletion snapshots without
  temporary real-index writes. Fingerprint acceptance policy separately.
- [ ] Implement authorized bounded input probes and unverifiable freshness.
- [ ] Implement prepare/record/find, pending immutable records and canonical
  trailers/detail proposals, strict parsing and ID deduplication.
- [ ] Preserve observed FAIL/SKIP/unstable/domain-limited results without treating
  them as PASS. Validate persistent log/detail recovery routes.
- [ ] Search reachable history rather than unrelated branches for trailers;
  newest FAIL at an identical check/scope/domain/policy supersedes an older PASS.
  Use ancestry order, not author dates; incomparable conflicting branch results
  are a finding requiring a new reviewed run. Re-recording an old attempt's
  PASS does not supersede a later failure: order each ID by its original
  introduction, ignoring duplicate later carrying commits.
  Never pick an older PASS to conceal a later failure. Historical evidence for
  a different scope remains historical, not accepted for this checkout.

**Validate:** docs-only reuse; code/mode/deletion/untracked changes; ignored inputs;
policy/scope/domain changes; failing/missing/changed/undeclared input commands;
unstable before/after snapshots; paths with spaces and symlinks; pending gate
input; interrupted record/commit/cleanup; fresh-clone evidence recovery; no
changes to real index/object DB or ignored state affecting scope.

**Done when:** fresh acceptance survives loss of XDG state, while missing or
changed proof cannot be fresh. Re-recording identical evidence is a no-op.

### Task 6: Delegation composition adapter

**Files:** `delegation.py`; tests `test_long_horizon_delegation.py`.

- [ ] Implement configured checker calls, timeouts, text tree/lint and JSON
  pending/query decoding. Commands contain argv paths, not shell interpolation.
- [ ] Validate exact-tree registered results at record time, without running
  validators, creating a ledger or importing checker internals.
- [ ] Reuse committed scoped evidence as historical provenance after non-code
  edits, keeping current exact-tree checked claims distinct.
- [ ] Handle pending workers, corrupt output, missing checker/environment paths
  and absent delegation explicitly. Solo use needs no checker at all.

**Validate:** controllable stub tests plus one disposable integration test using
this checkout's actual `check.py` to record a tiny registered validator. Verify
failed/skipped/unstable/wrong-validator/wrong-tree results never pass; a lost
ledger preserves durable acceptance but supplies no current checked result.

**Done when:** the adapter works with the existing public CLI and has no second
ledger, tree hash or agent lifecycle implementation.

### Task 7: Close gate and lifecycle records

**Files:** `gate.py`; tests `test_long_horizon_gate.py`,
`test_long_horizon_lifecycle.py`.

- [ ] Compare proposed goals with HEAD or explicit base and check newly completed
  tasks, milestones, goals, ownership changes and each required check/domain.
- [ ] Resolve pending and committed references, policy-scoped explicit accepted
  exceptions and allowed skips. Missing free-text proof fails with repair choices.
- [ ] Validate milestone whole-call requirements, completion records, summaries,
  goal evidence/sign-off and archival compression without losing obligations.
- [ ] Model milestone progression, coarse next-milestone refinement, parked
  triage, waiting sign-off, rejection/reopening, shelve/drop/unshelve and dormant
  reactivation. File edits remain skill operations, not automatic gate mutations.

**Validate:** gate rejects task-only evidence closing an integration milestone,
missing goal proof, user sign-off absence, forged/unresolvable archive summaries,
criterion changes, wrong-target exceptions and unauthorized policy edits. Check
HEAD/pre-batch bases and a goals-only acceptance commit; rerunning passes without
creating duplicate archive records or re-closing prior milestones.

**Done when:** every false-completion path in the spec is a deterministic failure
with concrete run-check/task-only/user-exception remedies.

### Task 8: Closure bookkeeping and recovery

**Files:** `closure.py`; tests `test_long_horizon_closure.py`.

- [ ] Implement record/verify and make status show unfinished steps.
- [ ] Check batch commit ownership/content, target ancestry and remote-ref
  containment independently; preserve push/sync observations separately.
- [ ] Preserve ordered successful steps on failure, reject conflicting batch
  identities and offer the next exact authorized operation.
- [ ] Support fast-forward/merge, explicit squash mappings, stale/missing refs,
  detached/unborn branches, changed policy and unavailable/dirty target worktree.

**Validate:** disposable bare remotes and two worktrees; commit then merge then
local push, deliberately rejected push, sync failure, retry after success,
interrupted recording, repeated verify, missing remote refs and imported state.
All actual Git operations are performed by test fixtures, never by `lh.py`.

**Done when:** commit/merge/push/sync claims cannot collapse into one success flag,
and a retry does not repeat already completed integration.

### Task 9: Shared skills, interview and templates

**Files:** `setup/SKILL.md`, setup references `interview.md`,
`goals-template.md`, `handoff-template.md`, `cheatsheet.md`;
`resume/SKILL.md`, `checkpoint/SKILL.md`; existing format references.

- [ ] Write quick/full setup with plain-language concepts, at most about five
  quick questions, “you decide” defaults, one read-only survey and all modes:
  new/adopt/update/add-goal/wind-down. Reuse established answers and policy.
- [ ] Show owned-file drafts, dry-run status, selected task, sample session,
  closure recommendation/alternatives, pointer locations, missing inputs and
  optional delegation suggestion together. Approval is the final step before
  applying those concrete drafts. An already authorized identical rerun is a no-op.
- [ ] Preserve existing roadmap text/order/evidence, unrelated dirty work,
  branch overlays and host policy. No tools installed or startup run implicitly.
- [ ] Write resume flow: status, staleness reconciliation, authorized startup,
  readiness/status, blockers/selection, optional single quota read, three-line
  brief and work. “Where are we?” is status only; overrides/off-goal/park/pause
  do what the spec says without additional ceremony.
- [ ] Write checkpoint flow: delegation pending, prepare/check/record/reuse,
  proportional acceptance, owned goal/handoff edits, gate/lint, lifecycle record,
  authorized closure/recovery, concise result and fresh-session recommendation.
  Include standalone and combined concrete command walkthroughs.
- [ ] Cover one-line small-batch handoffs, durable findings during work,
  shared-section regeneration after merge conflict, milestone-boundary parked
  triage/refinement, sign-off rejection and retention during wind-down.

**Validate:** run every documented CLI example against fixtures; manually walk
all skill branches against actual JSON/text outputs. Check relative resource
links and installed sibling script paths; do not mistake textual review for
model execution. Skills never hardcode a username/cache/version or silently
invoke commands from an overlay without authorization.

**Done when:** a new user can say continue/where are we/park/pause/sign off/shelve,
and every flow has a concrete next action and accurate acceptance boundary.

### Task 10: Packaging, documentation and composition

**Files:** new plugin `plugin.json`; `catalog.json`; generated manifests and
marketplaces; `README.md`; delegation skill/setup composition references and
`plugins/delegation/plugin.json`; `tests/test_sync_marketplaces.py` as needed.

- [ ] Add long-horizon identity 0.1.0 and generate metadata. Keep all source and
  generated changes together; no manual generated edits.
- [ ] Document install/use commands, script override, quick setup, cheat sheet,
  composition table, standalone/combined session and state/closure semantics.
- [ ] Add the same composition guidance to delegation, reuse survey notes and
  validator names without commands, and bump its release version appropriately.
- [ ] Assert all three skills/resources/scripts are installed identically by
  both hosts. Extend lifecycle inventory expectations only where needed; current
  catalog-driven discovery should pick up the seventh plugin automatically.

**Validate:** generator rerun produces no additional diff. Run the required
packaging checks below with new files tracked/staged before lifecycle verification
(the verifier compares `git ls-files`; an untracked module would escape that
comparison). Stage only owned files; staging is not a claim of committing them.

**Done when:** both disposable profiles discover/install/remove the complete
portable content, with actual versions/results recorded rather than assumed.

### Task 11: Behavioral pilots and release evidence

**Files:** `tests/fixtures/long_horizon/pilots/`,
`docs/long-horizon-pilots.md`, `docs/verification.md`.

- [ ] Create copyright-free tiny projects: vague aim in linked worktree, existing
  roadmap in main with unrelated dirty files, existing branch overlay, blocked
  capabilities, scoped validator with external input, and local bare remote.
  Create stable prompts, starting trees, expected actions and output inspection
  criteria; keep generated transcripts/logs in XDG unless deliberately curated
  for durable documentation. Use disposable host profiles and explicit pilot
  credentials/settings, never normal plugin configuration.
- [ ] Run model-driven setup/resume/checkpoint on **both supported hosts** and
  inspect actual tool calls and final files. Installation/unit tests cannot
  establish interview quality, command use or honest claims by a model.
- [ ] Cover every scenario in the matrix below; combine scenarios in one pilot
  when the starting state and assertions remain explicit. Quota uses a stub for
  deterministic call counting; a live read is optional, separately labeled.
- [ ] Record host/Python/plugin versions, commit/tree, prompts, scenario results,
  actions, evidence locations and failures. Fix failures and rerun only affected
  scenarios, then required packaging checks after final content changes.
- [ ] If a host/model is unavailable, label those scenarios untested and leave
  the v1 behavioral release gate open. Do not substitute a source citation,
  CLI installation result or an assertion that it should work.

**Done when:** observed pilots on both hosts demonstrate setup, selection,
honest acceptance and useful continuation; all required cases have observed
results or a plainly documented release blocker. No token savings claim.

### Task 12: Final review and release handoff

- [ ] Re-read the spec/plan coverage matrix, CLI examples, reference links and
  README against the final implementation; remove inconsistent old state paths.
- [ ] Run all required checks, record actual verification, and inspect the final
  diff for hardcoded paths, generated drift, credentials and unowned edits.
- [ ] Commit owned source/generated/docs changes together and integrate only
  under the implementation session's authorization. Report exact commit/closure
  and any release blockers; do not claim an unperformed push or host pilot.
- [ ] Leave game-decomp adoption as a separately authorized consuming-repo change.
  Its concrete checklist is adopt existing goals/handoff, preserve ownership and
  host policy, add readiness output to `tools/resume.py`, replace cache globbing
  with a declared checker path, move standing policy out of handoff, dry-run
  selection, approve, lint/status and verify authorized startup/evidence.

**Done when:** the plugin satisfies packaging/unit/behavioral acceptance and the
handoff identifies remaining consuming-repository work without applying it here.

## Verification commands and scope

Use focused tests during implementation, then the contributor-required checks
after packaging changes and after final released-content changes:

```sh
python3 scripts/sync_marketplaces.py --check
python3 -m unittest discover -s tests -v
uv run --no-project --python 3.10 -m unittest discover -s tests -v
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```

The Python-3.10 run verifies the promised compatibility separately from the
system Python. Lifecycle uses the verifier's disposable profiles. Record actual
versions and observed results in `docs/verification.md`; model pilots have their
own scenario evidence. Do not expand testing repeatedly once it passes without
new changes or an unresolved failure. No GUI test is needed for this CLI/skill
plugin, and none is claimed. Local bare-remote tests verify Git mechanics, not
remote hosting or real user sync.

## Spec coverage and pilot matrix

`U` means deterministic unit/integration fixture coverage. `C` and `D` mean
observed Claude Code and Codex model pilots, respectively; these are requirements,
not results. Record actual pass/fail/untested in the pilot report.

| Spec aspect / required scenario | Implementation task | Required proof |
| --- | --- | --- |
| Packaging, identical content, 0.1.0, stdlib, declared paths | 1, 2, 10 | U + lifecycle both hosts |
| Vague aim setup from linked worktree | 3, 9, 11 | U, C, D |
| Adopt roadmap in main with unrelated dirty files | 2, 9, 11 | U, C, D |
| Existing overlay on another branch | 2, 9, 11 | U, C, D |
| Fresh checkout selects without full history | 3, 9, 11 | U, C, D |
| Bounded later-stage acceptance preserves order | 3, 7, 11 | U, C, D |
| Missing native inputs, fixtures available | 3, 9, 11 | U, C, D |
| First blocked / all blocked; offers concrete choices | 3, 4, 9, 11 | U, C, D |
| Stale handoff / dirty tree reconciliation | 4, 9, 11 | U, C, D |
| Failed/skipped/stale/changed external acceptance | 5, 6, 7, 11 | U, C, D |
| Fresh evidence after docs-only edit | 5, 6, 11 | U, C, D |
| Solo and delegated batches, no duplicate ledger | 6, 9, 11 | U, C, D |
| New worktree/provider reconstructs durable context | 2, 5, 9, 11 | U, C, D |
| Push or sync fails after commit; precise retry | 8, 9, 11 | U, C, D |
| Explicit pause and user scope override | 4, 7, 9, 11 | U, C, D |
| Closure choice recommends merge/push, honors alternative | 8, 9, 11 | U, C, D |
| Successful batch closes, recommends fresh session | 8, 9, 11 | U, C, D |
| Milestone complete; next coarse tasks refine by ownership | 7, 9, 11 | U, C, D |
| Last milestone, completion record, sign-off and archive | 7, 9, 11 | U, C, D |
| All goals complete; approved partial wind-down | 2, 7, 9, 11 | U, C, D |
| Add goal after wind-down without full resurvey | 7, 9, 11 | U, C, D |
| Quick setup, unfamiliar user says “you decide” | 9, 11 | C, D |
| Survey finds bulk/validators, suggests delegation only | 9, 10, 11 | C, D |
| Quota enabled/disabled/absent; one call or none | 3, 9, 11 | U stub, C, D |
| Gate missing evidence offers check/task-only/exception | 7, 9, 11 | U, C, D |
| Off-goal fix and park mid-batch preserve roadmap | 4, 9, 11 | U, C, D |
| User overrides selection, logs line, preserves work | 4, 7, 9, 11 | U, C, D |
| Shelve/drop with reason/record, resume shelved goal | 3, 7, 9, 11 | U, C, D |
| Warning-only lint proceeds, repairs are repeatable | 4, 9, 11 | U, C, D |
| Goal consistency, IDs, parked, archives, sign-off gates | 3, 7 | U |
| Pointer reachability, hygiene, limits, diff/apply | 4 | U |
| Scope/input/policy freshness and accepted exceptions | 5, 7 | U |
| Current delegation claims vs scoped historical evidence | 6 | U actual checker |
| Brief progress and Needs-you list | 3, 8, 9 | U, C, D |
| Commit/merge/push/sync are separate claims | 8 | U local bare remote |
| Durable findings, recovery routes, pinned context | 5, 6, 9 | U, C, D |
| Idempotent setup/record/repair/archive/closure/reactivation | 2, 4, 5, 7, 8, 9 | U, C, D |
| Deferred claims, scheduling and generic cost measurement | 1, 12 | Scope review; no v1 implementation |
| game-decomp adoption separately authorized | 12 | Explicit follow-on checklist |

## Planning completion criteria

The planning deliverable is complete when every spec section and acceptance
scenario maps to an implementation task and proof, the contracts above resolve
all open design choices, and the plan is committed and pushed as requested.
Implementation completion is distinct: the unchecked tasks and release evidence
above must actually be performed. Remaining decisions about a consuming
project's goal, acceptance authority, external bytes and remote authorization
are intentionally collected by setup; the plugin cannot choose them globally.
