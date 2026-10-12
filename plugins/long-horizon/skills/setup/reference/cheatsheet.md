# Long-horizon cheat sheet

| Say | Action |
| --- | --- |
| Set up / adopt this roadmap | long-horizon:setup surveys once and presents concrete drafts |
| Continue | long-horizon:resume inspects, prepares authorized inputs, selects one task |
| Where are we? | Read-only status; three-line brief and Needs you |
| Checkpoint | Prepare/run/record or reuse evidence, gate/lint, authorized closure |
| Park this idea | One dated Parked line; roadmap scope stays intact |
| Do this instead | Requested work plus Override line and preserved original work |
| Pause | Preserve work, record next step; no invented closure |
| Sign off | Actual approval, completion archive, done marker and Signed-off |
| Reject sign-off | Reopen rejected work with reason and retained history |
| Shelve / drop | Actual instruction, reason and archive of where work stopped |
| Resume shelved goal | Restore preserved roadmap and ID |
| Wind down | Reviewed dormant/pointer diff; preserve durable files and other plugins |
| Add another goal | Reuse policy/survey, reactivate one pointer/import |

Set `LONG_HORIZON_SCRIPT` to the installed resume/scripts/lh.py or any checkout's
plugins/long-horizon/skills/resume/scripts/lh.py. Set PROJECT explicitly.

```sh
python3 "$LONG_HORIZON_SCRIPT" status --root "$PROJECT" --brief
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT"
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT" --fix
python3 "$LONG_HORIZON_SCRIPT" lint --root "$PROJECT" --fix --apply
python3 "$LONG_HORIZON_SCRIPT" gate --root "$PROJECT"
python3 "$LONG_HORIZON_SCRIPT" closure verify --root "$PROJECT"
python3 "$LONG_HORIZON_SCRIPT" state gc --json
```

Warning-only lint permits work. Gate proof missing? Run named checks; mark only
tasks done with evidence; or obtain actual targeted exception approval. Readiness
never means acceptance. Commit/merge/push/sync are separate claims. Runtime state
is XDG, with weekly collection, seven-day deleted-worktree recovery and 30-day
unreferenced draft/snapshot expiry. Durable Git evidence survives cleanup.

With a startup helper, draft `readiness: "cache:readiness.json"`. Helpers use
`lh.py paths --root PATH --json` for the per-worktree destination and cache
identity; follow [publication and recovery](../../resume/reference/readiness.md).
