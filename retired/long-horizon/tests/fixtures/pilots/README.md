# Copyright-free behavioral pilots

The tiny function/test and all prompts here are original disposable fixtures.
`project/` is the starting code tree; `configured/` adds an existing roadmap,
handoff, host pointer and overlay. Runner supplies local Git identity, XDG paths,
linked worktrees, per-scenario mutations, bare remote/target worktrees, actual
registered checker results or external-input/one-call quota stubs. No real remote
or consuming repository is touched. Acceptance comes from observed calls/files,
not prompts alone.

Run with an explicitly chosen credential file and installed host:

```sh
python3 scripts/run_long_horizon_pilots.py --host codex --credentials "$PILOT_CODEX_AUTH" --scenario new
python3 scripts/run_long_horizon_pilots.py --host claude --credentials "$PILOT_CLAUDE_AUTH" --scenario checkpoint
```

The named credential is copied mode 0600 into a disposable profile; normal host
settings/plugin config are not copied or edited. Profiles/credential copies are
removed even on failure. Claude uses session-only plugin-dir; Codex registers and
installs this local marketplace only in its disposable profile. An unavailable
login/model is an observed blocker, never replaced by installation assertions.

Reports/prompt/transcripts/fixture outputs live in XDG cache under
rickdiculousli-tools/long-horizon/pilots/<UTC-host-scenario>. Keep curated summaries
in docs; local pilot artifacts can be removed after review or after 30 days.
No automatic cleanup removes a running pilot; manually remove only completed
pilot directories after checking profile absence. Script prints report path and
assertions, never credentials. Actual tool-call inspection is required in addition
to assertions, including any failed commands the model recovers from.

| Scenario | Starting state / inspect actual actions |
| --- | --- |
| new | Vague aim, linked worktree; bounded questions/defaults, dry-run before surgical application, no tests or retrospective PASS, repeat no-op |
| adopt | Existing roadmap in main and unrelated dirty bytes; text/order preserved, one pointer/import |
| branch | Unique existing policy on another local branch; local survey no fetch, budget 67 adopted |
| blocked | Native tag unavailable and second task handoff-blocked; concrete choices, no milestone skip, park/off-goal override/pause preserve work |
| checkpoint | Dirty bounded implementation; prepare/run/record observed unit, task-only completion, explicit pending gate, missing human whole-call acceptance, docs-only reuse |
| external | First actual unit FAIL, later PASS, ignored external token changed; probes/freshness unknown by default, stale proof never PASS |
| composed | Actual seeded registered d1#1; exact-tree record before docs edits, historical reuse, durable commit/recovery after lost ledger, no workers/second ledger |
| closure | Committed batch already recorded; separate merge/rejected push/retry/failing sync/retry, preserved prior successes, local remote-ref qualification, fresh-session recommendation |
| lifecycle | Await sign-off, rejection/reopening, approved completion/archive/compression, partial wind-down, retained archive, approved add-goal/reactivation no resurvey |
| selection | Authorized preparation, first blocked then all blocked, stale handoff, bounded later-domain override |
| outcomes | Actual SKIP and scope-changing UNSTABLE, PASS refusal, no completion |
| reconstruct | Fresh local clone with old state removed, durable historical scope recovered, no invented closure |
| boundary | Prior milestone accepted, current coarse tasks refined within ownership, parked idea deferred |
| stop | Shelve/unshelve/drop preserve original work and claim no completion |
| quota | One stub read only, low usage stays bounded; warning-only lint, preview/apply ID repair, second no-op |

Fixtures/unit tests separately cover first-blocked selection, malformed inputs,
all-of tags, fresh clone, failing/timeout probes, skips/unstable checks, corrupt
checker, incomparable evidence, scope changes, forged archives, sign-off errors,
GC grace/throttle/concurrency, lock backends and idempotent local closure. They are
not model execution evidence. The pilot report maps each required scenario to
observed host evidence or an explicit untested release blocker.
