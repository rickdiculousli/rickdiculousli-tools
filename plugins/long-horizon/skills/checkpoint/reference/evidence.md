# Evidence and closure version 1

Checks use exact overlay tokens. Scope is Git pathspec matched tracked plus
nonignored untracked entries with content/mode/deletion/symlink/submodule identity.
No writes to real index or Git objects. Unresolved conflicts/unreadable or dirty
submodules fail closed. Default scope excludes configured goals/handoff/findings/
archives/evidence sink; acceptance policy has a separate digest covering check
scope/domain/inputs/skips, validator policy and normalized required criteria/checks.
Status markers, sign-off dates and task refinement do not invalidate it.

Prepare captures before-scope/inputs/policy/domain and attempt; it runs no check.
Repeated attempt with unchanged contents reuses it; changed attempt contents fail.
Record captures after-state and requires one provenance: observed command+exit,
registered delegation+result, or dated reviewer+durable review-note for observation.
Reviewed records also need `--reviewer-kind human|agent`, stored as `reviewer_kind`.
An observation check accepts only human reviewers unless its definition sets
`"reviewer": "any"`. Milestone ownership decides who may mark work done, not who
may review it.
PASS requires stable inputs and exit 0; delegated PASS also requires registered
validator, checker tree, stable true, ok true, exit 0 and no timeout. Arbitrary
checker exec is observed only. FAIL/SKIP/UNSTABLE remain their actual outcomes.
A domain-limited skip only satisfies its explicit allowed domain; never call it PASS.

External probes run only under `--probe-inputs`, on prepare and record and on
freshness/gate inspection. Probe is authorized read-only argv, <=60-second timeout,
exactly one SHA-256 token; absent/changed/failed probe cannot prove freshness.
Without probes, external freshness is unknown with recovery. Undeclared inputs fail.

Each record is canonical sorted-key JSON, content addressed by SHA-256 excluding
id, carrying commit, created/last-use timestamps, derived detail location and
scratch snapshot pointer. Attempt is included. Pending copies are immutable XDG
state; record emits proposed durable detail JSON and a shlex-quoted trailer:

```text
Accepted-Check: id=<sha256> name=validator:unit outcome=PASS scope=<sha256> policy=<sha256> domain=unit-v1 claim=observed detail=docs/evidence/<id>.json log='regenerate:declared unit validator at this commit' inputs=none ledger=none
```

Parser rejects malformed/repeated fields. Durable detail path defaults under
configured evidence sink. Review/write those files before committing. Record
writes a file only with `--write-proposed`, and then only the record's own detail
path; it refuses to overwrite different bytes. It never stages, commits or amends. Log must be a checkout file
or a specific persistent http(s)/regenerate route, never scratch-only state.
Copied logs can use their own content digest name; the evidence ID must not hash
its own ID or a path containing it. Reviewer note is a durable dated record;
the skill verifies the actual review and records which kind of reviewer signed.
A recorded observation is not authenticated by the CLI. Sign-off/exception text cannot authenticate approval either.

Reachable history only; newest matching scope/domain/policy/input result supersedes
older outcomes in ancestry order. Original introduction orders IDs; copying an old
PASS later does not supersede a later FAIL. Conflicting incomparable branches need
a new reviewed run. Fresh clone can reconstruct trailers/details with no XDG state.
Pending acceptance is accepted only through explicit repeated `--pending <id>`;
it remains pending, never already committed. Missing proof is data in find and an
error when required by gate.

Re-record after a criteria-only change. Records name the criterion they prove, so
an approved criteria edit (or the `Done when` layout repair) makes them stale:

```sh
python3 "$LONG_HORIZON_SCRIPT" evidence rerecord "$EVIDENCE" --root "$PROJECT" --write-proposed --trailers-file "$TRAILERS" --json
```

It prepares a fresh snapshot and carries the same observation onto the current
criteria only if scope, inputs, domain, log, check definition and validator policy
are unchanged; a delegated record also needs the same checker tree and its still
registered result, a reviewed one the same note. Otherwise rerun the check. A
superseded pending record loses its XDG copy, its untracked unchanged detail file
and its line in the trailers file; committed history is never touched. Update
any `Evidence:` citation of the old ID to the new one.

Exceptions after actual approval:

```sh
python3 "$LONG_HORIZON_SCRIPT" evidence record validator:unit --root "$PROJECT" --exception --target "$MILESTONE" --reason "Reviewed fixture limitation" --by user --json
```

Exception trailer: Accepted-Exception with id/check/target/reason/by/policy/detail.
It is targeted to the exact required check and criterion revision; does not waive
sign-off, unrelated milestone checks or remote policy. List exceptions in archive.

Commit assembly: `--trailers-file "$TRAILERS"` accumulates a batch: each record
appends its trailer once, in order, atomically; reruns do not duplicate it.
Review a message containing those exact lines and use `git commit --file "$MESSAGE"`
under authorization, staging only owned paths. Do not amend or add an automatic
empty commit. Cleanup verifies IDs in the exact carrying commit before removing
pending copies; retries deduplicate IDs.

Closure manifest JSON:

```json
{"version":1,"base":"<pre-batch-commit>","paths":[{"path":"src/file.py","digest":"<sha256-of-bytes-or-null-for-deletion>"}],"evidence_ids":["<accepted-id>"]}
```

Batch ID = SHA-256 canonical sorted-key JSON of `{"evidence_ids": <sorted IDs>,
"paths": <paths sorted by relative path>}`. `closure manifest --base <pre-batch>`
builds both from the worktree: every path changed since base plus untracked,
unignored files (narrow with repeated `--path <pathspec>` to leave unrelated dirty
work out), their current byte digests, and the pending records that currently
accept their check (or explicit repeated `--pending`). It reports stale pending
records as `unused_pending`, prints the batch ID and writes the manifest to XDG
state `manifests/<batch>.json` (or `--output` outside the checkout). Review it, then pass the reported path
to the first `closure record --manifest`. That record reports the expected ID if
mismatched. First closure record requires manifest. Ordered steps come only
from approved integration policy. `closure record` accepts step validate/commit/
merge/push/sync, outcome success/failed/pending, exact --commit, optional
--integrated-commit for reviewed squash mapping, --observation and --manifest.

Commit verification checks exact owned changed paths/bytes and ancestry. Merge
checks integrated OID is in local target. Push checks configured remote-tracking
ref contains integrated OID, qualified as of local observation; it also needs an
observed push success. Local refs cannot establish server present state or last
fetch time. Sync remains an observed host claim unverified by Git. Failure preserves
successful ordered steps; changed batch/policy cannot overwrite them. Imported
closure is explicit `closure verify --state PATH`. Missing refs/detached/unborn
histories/changed policy remain unknown/unfinished; never infer one success flag.

Pending cleanup after exact durable commit verification:

```sh
python3 "$LONG_HORIZON_SCRIPT" evidence cleanup --root "$PROJECT" --commit "$COMMIT" --id "$EVIDENCE" --json
```

Repeat `--id` for each included record. Missing/mismatched carrying proof refuses
cleanup; an already-cleaned verified record is a no-op. For a subsequent batch use
`closure record --new-batch` with a new reviewed manifest only after prior closure
verifies complete. Prior closure is retained as an expiring XDG snapshot.
