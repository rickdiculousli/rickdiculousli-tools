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

A claim that something passed must be `checked`. A validator that fails, or a
ledger entry at a different tree, downgrades the claim to `asserted`. Ledger ids
look like `<delegation>#<n>`; a result printed as `unstable` (the tree changed
while it ran) is never `checked`.

## Brief template

Save as `.delegation/briefs/<id>.md`. Fill every field; write `none` where
nothing applies. Write only these fields: `check.py brief` appends the
delegation id, the validator command with absolute paths, the return format,
and the overlay's return fields and cap.

```markdown
# Delegation <id>

Tier: <execute|routine>
Settled: <facts and rulings already established, with refs; or "read .delegation/context/<name>.md first"; or none>
Goal: <one or two sentences: what done looks like>
Inputs: <paths, symbols or addresses to read; these bound your reading>
May write: <paths, or "nothing (reader)">
Must not write: <the overlay's single-writer resources, and anything not listed above>
Done when: <the condition>; validators: <names from the overlay that cover this change, or none>. A writer runs them last, after its final edit, so the results are at the tree the judge reviews.
```

`open` records the hash of the brief and of every `.delegation/context/` file it
names; `brief` refuses if any of them changed. Don't edit either after opening.
