# Return format and brief template

## Return format

`check.py brief` appends this block to every brief; don't write it yourself.

```
Result: one paragraph.
Claims:
  - <claim> [checked: <ledger id>] | [cited: <refs>] | [asserted]
Fields: <the overlay's return fields>
Surprises: <anything unexpected>
Ruled out: <approaches tried and rejected, and why>
```

Length is capped by the overlay's `## Return cap` (default 400 words).

| Evidence kind | Backed by | Judge treats it as |
|---|---|---|
| **checked** | A ledger id from a registered validator, at the current tree | Accepted |
| **cited** | References (paths, lines, addresses, symbols) that a validator confirms *exist* | References accepted; reasoning judged |
| **asserted** | Prose only | A hypothesis; may drill in |

A claim that a registered validator passed must be `checked`. Command results
from `exec` have `validator=null`; cite their observations or mark them
`asserted`, even if the command exited successfully. A validator that fails, or a
ledger entry at a different tree, downgrades the claim to `asserted`. Ledger ids
look like `<delegation>#<n>`; a result printed as `unstable` (the tree changed
while it ran) is never `checked`.

## Brief template

Resolve `brief_directory` with `check.py paths --json`; save as
`<brief-directory>/<id>.md` and quote that absolute path in commands. Fill every field; write `none` where
nothing applies. Write only these fields: `check.py brief` appends the
delegation id, the validator command with absolute paths, the return format,
and the overlay's return fields and cap. The footer also prohibits commits unless
the brief explicitly authorizes them, first-person language in committed files,
and host-side never-write changes outside the isolated worktree when the overlay
section is nonempty. These are agent instructions, not filesystem enforcement.

```markdown
# Delegation <id>

Tier: <execute|routine>
Settled: <facts and rulings already established, with refs; or "read state:context/<name>.md first"; or none>
Goal: <one or two sentences: what done looks like>
Inputs: <paths, symbols or addresses to read; these bound your reading>
May write: <paths, or "nothing (reader)">
Must not write: <the overlay's single-writer resources, and anything not listed above>
Done when: <the condition>; validators: <names from the overlay that cover this change, or none>. A writer runs them last, after its final edit, so the results are at the tree the judge reviews.
```

`open` records the hash of the brief and of every `state:context/` file it
names; `brief` refuses if any of them changed. Don't edit either after opening.


## Role and peer briefs

For a reusable role, name its runbook in `Settled` or `Inputs` and explicitly
include that path in `May write` only when refreshing it is authorized. Preserve
all existing tracked-file permissions when continuing; role reuse grants no new
write access. A continuation uses a new delegation id and brief and records new
hashes; never edit the earlier brief.

For asynchronous peer calls, the caller's brief must include both the peer's host
agent id and the caller's delegation id. The judge maps host ids to delegation
ids; the ledger cannot infer that mapping. The role runs the caller's commands
with `check.py run <validator> --delegation <caller-id>` or
`check.py exec --lock <name> --timeout <seconds> --delegation <caller-id> -- <command>`.
Evidence belongs to the caller, not the role's own brief. Keep the caller open
until the peer completes. Report command observations as `cited` or `asserted`;
only stable current-tree registered-validator results qualify as `checked`.

Proactively refresh the runbook during the final allowed use after work and
checks complete, before close. Changing it invalidates the current brief's hash;
do not reload that brief afterward.

At a reuse-cap refusal the prior use is already closed. The judge opens a
separate short refresh delegation without `--role` or `--continue`, granting
`May write` only for the already-authorized runbook, and sends its loader to the
existing host agent solely to refresh. Close that refresh delegation and start a
fresh role session. Do not give the capped agent more task work, reload an old
closed brief, or broaden tracked-file permissions.
