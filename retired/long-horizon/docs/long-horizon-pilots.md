# Long-horizon behavioral verification

Observed on 2026-10-11 with **Codex 0.162.1** and **Claude Code 2.1.296**, Python
**3.14.4**, long-horizon **0.1.0**, and disposable configuration profiles. All
30 final host/scenario cells passed inspection across 35 actual model runs. One
additional fixture preflight failed before model execution and was fixed/rerun.
The [curated results](long-horizon-pilot-results.json) retain every attempt,
including the three initially misleading automated passes rejected by manual
review. This is observed model behavior, distinct from unit/install checks.

Claude initialization events identify `claude-opus-5-5`. Codex used the host
default; `gpt-6.1-sol` was confirmed from turn-context metadata in the corrected
reconstruction session and final quota rerun. Earlier Codex exec event streams did not expose a model
slug, so their per-run metadata leaves it unknown. No worker agents were spawned.

Pilots ran the in-progress uncommitted implementation based on `928299ca94e28d97e87b2cfc324210f4c90f41f6`.
Each report records its actual plugin-content digest, prompt/event/tool-call
hashes, starting Git commit/tree, elapsed time and resulting assertions. Starting
Git trees cover committed inputs; the runner and fixtures explicitly define dirty
starting mutations. Later defensive parser/state fixes were regression-tested
and affected behavioral cases rerun; the final packaging/suite evidence is in
[verification](verification.md). Do not interpret earlier content hashes as the
final committed tree or infer model observations for native Windows.

[Stable fixtures/prompts](../tests/fixtures/long_horizon/pilots/README.md) and the
[standard-library runner](../scripts/run_long_horizon_pilots.py) reproduce these
cases with explicitly supplied pilot credentials. Only that named credential
file is copied, mode 0600, into a disposable profile; normal settings/plugin
configuration are not copied or edited. Profiles/credential copies were removed
for every attempt. Claude loaded the session-only plugin directory; Codex
registered/installed the local marketplace in its disposable profile. Local bare
remotes/linked worktrees belonged solely to fixtures. No real hosted remote or
consuming repository was changed by pilots.

Artifacts are below
`${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/long-horizon/pilots/<artifact>/`:
`prompt.txt`, `events.jsonl`, `stderr.log`, `report.json`, fixture files and their
explicit external XDG directories. Completed local artifacts may be removed after
review or after 30 days; curated hashes/results remain tracked. Exact passing
artifact IDs for each cell are in the JSON's `final_cells` map.

| Scenario | Codex | Claude Code | Inspected behavior |
| --- | --- | --- | --- |
| new | Pass | Pass | Vague aim in linked worktree, “you decide”, concrete drafts/dry-run, commit-only alternative, no source/test changes or retrospective PASS, repeated setup no-op |
| adopt | Pass | Pass | Existing main roadmap preserved byte-for-byte, unrelated dirty bytes preserved, one pointer/import, reused survey/policy |
| branch | Pass | Pass | Unique other local branch adopted without fetch; custom budget 67 and host text retained; corrected cache namespace verified |
| blocked | Pass | Pass | All-blocked recovery choices; park, explicit off-goal override and pause preserve roadmap and claim no acceptance |
| checkpoint | Pass | Pass | Prepare/run/record actual solo unit PASS, explicit pending gate, task-only completion, missing whole-call review stays open, docs-only evidence reuse |
| external | Pass | Pass | Actual first FAIL, later PASS, changed ignored input makes proof stale; default unknown without probes; final requested open tasks preserved |
| outcomes | Pass | Pass | Actual exit-77 SKIP and scope-changing UNSTABLE; attempted PASS refused, outcomes preserved without whole-call completion |
| selection | Pass | Pass | Stale/dirty handoff reconciliation, authorized readiness helper, fixture/native all-of levels, first blocked/second eligible then all blocked, later metadata-only domain stays limited |
| composed | Pass | Pass | Actual checker d1#1 registered result recorded before docs edits, no validator rerun, historical scoped provenance, durable recovery after ledger loss, no second ledger/workers |
| reconstruct | Pass | Pass | Fresh local clone/new profile without old XDG state recovers committed observed scope; task-only completion, no invented current-tree checker or push/sync; corrected external XDG roots |
| closure | Pass | Pass | Already committed batch resumes at merge; real local receive-hook rejection/retry, observed sync failure/retry, independent ancestry/ref/sync claims, repeated verification no extra integration |
| boundary | Pass | Pass | First milestone gated with existing proof, next coarse tasks refined within agent ownership, parked scope deferred, no duplicate refinement or goal completion |
| lifecycle | Pass | Pass | Await sign-off, rejection/reopening, explicit acceptance/archive/compression, no-active-goal, partial wind-down and exact payload clear, approved add-goal/reactivation |
| stop | Pass | Pass | Shelve with preserved reason/roadmap, unshelve original ID/work, drop a later goal without claiming completion, no resurvey |
| quota | Pass | Pass | Exactly one deterministic low-capacity stub call, bounded batch, warning-only ID repair preview/apply and repeated no-op; disabled/absent behavior described separately |

Quota-disabled/absent flows made no calls in the other observed resume cases.
Missing declared quota values are also covered by deterministic tests. This
report claims no live subscription savings, live quota pilot, GUI testing or
remote-hosting behavior. Closure sync used explicitly authorized fixture
commands; Git cannot authenticate host sync. A local remote-ref observation is
not server-present-state proof.

Manual review found and corrected:

1. Codex reconstruction placed XDG state under `.pilot-host` in the checkout.
   The CLI now rejects checkout/Git/installed-plugin runtime roots; all skills
   preserve shared external XDG roots. Regression and corrected pilot passed.
2. Claude external-input checkpoint checked a task despite “keep all tasks open”.
   Checkpoint now explicitly honors that requested boundary; stronger assertions
   and the rerun confirmed no checked tasks.
3. Claude branch adoption used a sibling cache draft directory. Setup now takes
   the exact plugin `cache_directory` from status; stronger cache assertions and
   the rerun confirmed the namespace and scratch cleanup.

The preflight reconstruction failure was an attempted empty seed-policy commit;
fixtures now skip unchanged policy commits and report actual Git diagnostics.
Expected failing tests, PASS refusals, rejected pushes and failed syncs are
scenario evidence, not concealed failures. Codex closure also disclosed a wording
imprecision (“updated” versus Git's new remote branch); actual OIDs and operation
results were inspected rather than trusting that wording.

The required v1 behavioral matrix has observed proof on both supported hosts for
setup, selection, proportional acceptance, continuation and recovery. Native
Windows process contention/atomic replacement remains **untested** (no Windows
runner), with both lock backends tested through mocks and real POSIX contention.
No model-driven Windows, GUI or real-server closure claim is made.

Adoption in a consuming repository remains separately authorized: adopt existing goals/handoff,
preserve ownership/host policy, add readiness output to tools/resume.py, replace
cache globbing with a declared checker path, move standing policy out of handoff,
dry-run selection, approve concrete edits, lint/status and verify authorized
startup/evidence. No consuming-repository changes were applied here.
