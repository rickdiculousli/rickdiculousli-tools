# Addendum: unified XDG state and locks

Status: specified side work for delegation, requested alongside long-horizon.
This document changes the design contract and repository contributor guidance;
it does not change released delegation behavior or migrate any user state.

Applies to the [delegation design](2026-10-09-delegation-design.md), the
[long-horizon design](2026-10-11-long-horizon-design.md) and its
[implementation plan](../plans/2026-10-11-long-horizon.md). Where their state,
cache, lock or cleanup locations differ, this addendum takes precedence.

## Purpose and scope

Worktrees are created, abandoned and deleted daily. Both plugins should use one
predictable convention for local bookkeeping, explicit paths and weekly cleanup,
without requiring one plugin to be installed for the other to work. Durable
project decisions and acceptance remain tracked in the consuming repository.

Move delegation's plugin-owned ledger, briefs, generated shared context, role
runbooks and validator logs from `.delegation/` to XDG state. Move its repository
resource locks from `/tmp` or Windows' temporary directory to XDG state. Move
temporary Git indexes and object directories to XDG cache. Keep its current
POSIX/Windows native locks, repository-wide resource-slot behavior, validator
ledger authority, tree algorithm and agent lifecycle. Do not introduce a second
ledger or let location migration create a new PASS.

The installed implementation currently uses `.delegation/` for worktree state
and system temporary directories for resource locks. These are legacy layouts
requiring the explicit migration below, not compliant paths to preserve forever.

## Shared location contract

Use an absolute, nonempty `XDG_STATE_HOME` or default to `Path.home() /
'.local/state'`; use an absolute, nonempty `XDG_CACHE_HOME` or default to
`Path.home() / '.cache'`. Relative/empty environment values are ignored, with a
compact explanation when explicitly set. Resolve paths in Python, without shell
expansion. Apply these same conventions on macOS, Linux and Windows. A configured
unwritable root produces an actionable diagnostic; never fall back to a second
state or resource-lock domain under the checkout or `/tmp`.

Each plugin uses its own `rickdiculousli-tools/<plugin>/` namespace and bundles
its own small stdlib helpers. Share format and behavior, not a cross-plugin
import. All processes sharing resource locks must use the same state root on
that host; changing roots while validators are running is unsupported. No
network filesystem or cross-host lock guarantee is implied.

Repository keys are full SHA-256 digests of the canonical, platform-case-normalized
Git common-directory path. Worktree keys are the equivalent digest of the
canonical worktree-root path. Resolve relative Git paths before hashing. Keys
are local storage identifiers, never acceptance tree hashes. Store identity
metadata including original paths, directory file identities and volume identity;
a recreated path must not silently inherit old worktree state.

Delegation layout:

```text
<state-home>/rickdiculousli-tools/delegation/
  state.lock
  gc.json
  <repo-key>/
    identity.json
    locks/<name>.<slot>.lock
    locks/<name>.<slot>.json
    worktrees/<worktree-key>/
      identity.json
      ledger.jsonl
      briefs/<id>.md
      context/<name>.md
      logs/<id>/<result-number>.log

<cache-home>/rickdiculousli-tools/delegation/
  <repo-key>/worktrees/<worktree-key>/hashing/<attempt-id>/
    identity.json
    index
    objects/
```

Long-horizon uses the same `<repo-key>/worktrees/<worktree-key>/` structure for
its payload and its own fixed root `state.lock` and `gc.json`. It does not use
delegation's ledger or resource-slot directory. State includes operational logs
needed for pending work; cache includes only reproducible scratch bytes. No
configurable state location beside installed plugin scripts is introduced.

## Locks and safe removal

Use delegation's existing `fcntl.flock` on POSIX and `msvcrt.locking` on Windows,
with nonblocking attempts, bounded waits, exception-safe release and closed
replacement-file handles before `os.replace`. Keep holder metadata in a sidecar
on both platforms, separating payload reads from the locked byte on Windows.

Each plugin's fixed root `state.lock` serializes short bookkeeping and cleanup
transactions. It replaces worktree-specific ledger mutex files for new state.
Never delete, truncate for metadata, or replace that root lock. Readers needing
a consistent ledger snapshot also acquire it briefly; they do not create a
payload merely to inspect empty state. Validators, startup, input probes, Git
hashing and remote integration never run while holding this root mutex.

Delegation's resource-slot locks remain separate, held during a validator or
`exec` operation and shared across all worktrees of the repository. Their
acquisition, waiter registration, release metadata and cleanup must coordinate
through delegation's root mutex. Register a waiter before releasing the mutex
between retry attempts; attempt slot acquisition nonblockingly while holding
the mutex. Never wait on a slot while holding the mutex. Release/update holder
metadata under the same mutex. Persistent local owner records contain a PID and
process-start identity, not merely a PID; uncertain liveness protects state.
Native lock contention always protects the slot even if metadata is absent.

Cleanup cannot unlink a slot file when a process holds it, has a registered
waiter, or may be using it under an uncertain owner record. Recheck eligibility
and probe every slot under the root mutex before removing a retired repository's
lock directory. New acquisitions use that same mutex, closing the unlink/recreate
race. Live repositories keep their slot files; deleted repositories can lose
slot files after the recovery window when there are no holders/waiters. Empty
repository/worktree directories are then removed. Only one tiny fixed root lock
per plugin must remain indefinitely, not one per daily worktree.

A crashed process releases its OS locks. Reap its owner record only when its
process-start identity is confirmed gone; reused PIDs must not be mistaken for
that owner. Where native liveness checks cannot establish this, report unknown
and retain it. Do not silently reset open delegations because a holder exited.

## Path discovery and context references

Add `check.py paths --json` returning version 1, resolved state/cache roots,
repository/worktree keys, worktree state directory, brief/context/log directories,
resource-lock directory and root mutex path. A text view is also available.
Path inspection neither migrates nor creates state. Skills/helpers use this
output instead of constructing paths or globbing installed caches; all shell
examples quote returned paths containing spaces.

New briefs and role declarations use logical `state:context/<relative-path>`
references resolved inside the current worktree's XDG context directory. Hash
those bytes and retain single-writer/pinned-context rules. Reject path traversal,
symlink escape and references into another worktree. Named context inputs can
use this same prefix in `Extra inputs`; never fold the live ledger/log directory
into its own validator tree. Preserve external fixture recovery policies.

Recorded plugin-owned paths become worktree-state-relative paths with an explicit
`location: state` marker. Caller-provided brief paths may remain absolute and are
not automatically moved. Commands that print/log/read briefs resolve their
recorded location rather than blindly joining all paths to the checkout.
Historical event paths remain historical provenance; a migration mapping supplies
new locations. Do not change result IDs, outcomes, stability flags, old tree
hashes or log hashes to fit the new layout. If a renamed logical input changes
a current acceptance fingerprint, report stale and rerun the authorized check.

## Weekly cleanup and disposable worktrees

Use the long-horizon plan's cadence: one opportunistic sweep at most every seven
days (168 hours), triggered by normal setup/resume/checkpoint or a state-writing
command. No daemon or scheduled network work. Add `check.py state gc` for preview
and `check.py state gc --apply [--if-due]` for application, usable outside a
checkout. Both plugins scan only their own namespaces; they do not clean one
another's state. Read-only inspection does not silently run collection.

Confirm a deleted worktree through missing directory and missing Git registration;
retain stale registrations, unavailable volumes, access errors and uncertain
identities. Start a seven-day recovery window on the first confirmed missing
observation. Afterward remove its payload only when there is no active validator,
hashing attempt or resource holder/waiter. Open ledger records in a confirmed
deleted worktree are abandoned bookkeeping: report them during the grace period,
then remove them without claiming a close event or forging continuation. Existing
worktrees retain open delegations and pinned briefs/context/logs regardless of
age. Durable findings and acceptance must have been committed independently.

Delete unreferenced generated snapshots/context/drafts after 30 days without use;
ledger references and active roles pin their input bytes. Hashing attempt files
are removed immediately in a `finally` block. An interrupted attempt is eligible
for the weekly sweep only when its recorded owner is confirmed gone; uncertain
owner state is retained. Never unlink a native lock inode to break contention.
Cache cleanup uses the same state-root lifecycle mutex and attempts' owner
records, even though the bytes live under cache home. Collection previews list
eligible/protected/unknown entries, pending work and recovery deadlines. Applied
collection is confined, idempotent and recoverable after partial deletion.

Expiry is eligibility, not an exact deletion deadline: the next weekly sweep
performs deletion. Manual `--apply` bypasses the cadence, not safety or retention.
If the plugin is no longer used, automatic cleanup cannot run; explicit GC can
sweep its state/cache namespace later. Plugin-wide usage history (such as quota's
JSONL) is outside this worktree retention rule.

## Migration, compatibility and release

Ship this as a separately reviewable delegation release, initially `0.7.0` from
the currently inspected `0.6.2`; re-read the version before implementation.
Location/reference/CLI changes need a minor version bump, shared skills and
README updates, regenerated manifests and actual lifecycle verification.
Long-horizon continues to work with the old checker's evidence/pending interface;
XDG migration is not a prerequisite for using it solo or with legacy delegation.

Add `check.py state migrate` (preview) and `check.py state migrate --apply`:

1. Locate the current worktree's `.delegation/`, legacy repository resource locks
   and new XDG destination. Present source/destination, event/log/context counts,
   affected overlay/helper references and conflicts before mutation.
2. Require all old/new checker processes and validators for this repository to
   be quiescent, no open delegations and no busy legacy resource/ledger locks.
   The operator must stop/restart sessions with the new checker; old binaries
   cannot be taught the new mutex protocol by a marker they do not understand.
   Refuse detected activity or conflicting destination histories. Do not merge
   ledgers with colliding IDs or copy a live ledger between worktrees.
3. Copy only recognized files into a staging payload under XDG, verify content
   digests, write identity and path mappings, then publish atomically under the
   new root mutex. Preserve original event provenance and all evidence hashes.
   Unknown legacy files stay untouched and are listed. No automatic deletion of
   the source or `/tmp` locks, and no migration of another worktree's ledger.
4. Propose surgical overlay/helper updates from legacy context references to
   logical state references. Applying repository edits requires current task
   authorization; keep user-written helpers and captured external bytes intact.
   Explicitly inspect policy `Host side effects` for any new XDG prohibition;
   never override a consuming repository's restrictions.
5. Write a migration receipt containing source/destination digests and mappings.
   An identical rerun is a no-op; interrupted staging can resume after verified
   comparisons. Changed legacy files or a different destination fail with a
   remedy. An unmigrated existing legacy ledger blocks opening a fresh XDG
   ledger for that worktree and directs the user to migration, avoiding split
   histories. Retain legacy copies for explicit review/removal, not weekly GC.

After migration, all sessions must use the new checker and the same XDG root.
Do not support simultaneous old/new resource-lock domains by silently acquiring
both or falling back to `/tmp`. Document this coordinated upgrade explicitly.
The plugin can detect changed legacy files and refuse dependent writes, but
cannot prove that an arbitrary old binary will never be launched again.

## Implementation side work and acceptance

Implement independently of the long-horizon core in this order:

1. Add path/identity/state helpers and path inspection; isolate XDG in every test.
2. Move ledger/brief/context/log resolution and temporary hash scratch; preserve
   current tree algorithm and evidence provenance. Add state-reference parsing.
3. Move resource slots with root-mutex lifecycle coordination and owner records.
4. Add weekly preview/apply cleanup and explicit quiescent migration.
5. Update skills, references, generated metadata, README and verification record;
   release after compatibility and lifecycle checks.

Affected source: `delegation_check/tree.py`, `file_lock.py`, `ledger.py`,
`locks.py`, `overlay.py`, `brief.py`, `cli.py`, delegation's setup/base skills,
`reference/overlay.md`, `reference/return-format.md`, tests and plugin identity.
A small self-contained `state.py` should own path/identity/GC/migration helpers;
`file_lock.py` remains the shared backend within this plugin. Do not introduce a
runtime dependency between plugins or rewrite the existing lock-slot algorithm
beyond lifecycle coordination required for safe GC.

Tests must cover custom/default/empty/relative XDG roots; Windows/POSIX branches;
spaces and case normalization; main/linked/recreated/deleted worktrees; unwritable
roots without fallback; no real index/object-database mutation; hash stability
while bookkeeping changes; context integrity and path confinement; multi-worktree
resource contention; waiter/holder/crash/PID-reuse/GC races; weekly throttling and
retention with an injected clock; migration preview/no-op/interruption/conflict/
activity refusal; legacy evidence lookup; and pinned-input retention. Native
Windows results remain untested until actually exercised on Windows.

Run the contributor-required generated metadata check, unit suite and disposable
profile lifecycle verifier after packaging changes. Verify installed state-root
paths and scripts through both hosts using disposable XDG homes, record actual
versions/results in `docs/verification.md`, and report any sandbox inability to
write XDG explicitly. Never modify a user's normal plugin config or claim model,
GUI, Windows or remote execution from mocked/unit or installation checks.
