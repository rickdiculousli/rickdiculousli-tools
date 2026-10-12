# Work labels, the pattern log and scratch

Labels and the pattern log let the judge notice repeated work across worktrees
and sessions, so it can propose roles and repository scripts. They record what
kinds of work recur. They are never validator evidence.

## Where things live

`check.py paths --json` reports each path:

| Key | Scope | Content |
|---|---|---|
| `kind_registry` | repository (`<state>/<repo-key>/kinds.json`) | Labels, descriptions, aliases, decisions, archived counts |
| `pattern_log` | repository (`<state>/<repo-key>/patterns.jsonl`) | One line per labeled or unlabeled open and its close |
| `scratch_directory` | worktree (`<cache>/<repo-key>/worktrees/<worktree-key>/scratch`) | Throwaway scripts and intermediate files |

Every worktree of a repository shares the registry and the log; writes take the
plugin's root `state.lock` briefly. The repository identity check that guards the
ledger also guards them, so a recreated repository at the same path doesn't inherit
old labels silently.

## Labels

A label matches `[a-z0-9]+(-[a-z0-9]+)*`, at most 48 characters. It names a task
type that one runbook could cover. A label with a numeric word (`port-module-12`)
is accepted with a note, because it usually names an instance.

```sh
check.py kinds [--all] [--json]           # active labels, most recent first (25 unless --all)
check.py open ... --kind <label>          # reuse a registered label
check.py open ... --kind <label> --new-kind "<one-line description>"   # register one
check.py kinds merge <old> <into>         # <old> and its history now count as <into>
check.py kinds rename <old> <new>         # <old> becomes an alias of <new>
check.py kinds mark <label> proposed|approved|declined [--note "<text>"]
```

- `open --kind` with an unregistered label exits 2 before opening anything and
  names the closest existing labels (similar spelling or shared words, then the
  most recent). `--new-kind` on a registered label also exits 2.
- `--role <name>` records `<name>` as the kind and registers it on first use;
  `--continue` keeps the prior role's kind. `--kind` with a different label is
  refused.
- `open` without `--kind` still logs the brief's shape, with a note.
- Aliases resolve when counting, so merges and renames never rewrite the log.
- `kinds` hides declined labels and labels with no uses inside the retention
  window; `--all` shows them.

## Brief shape

`open` fingerprints the brief from its tier, `--writes`, the paths named in
`Inputs` and `May write`, and the validator names after `validators:` in
`Done when`. File names collapse to directory plus extension and digit runs to
`#`, so the same task on another module or item has the same shape. When a
labeled or unlabeled brief has the shape of earlier briefs under a different
label, `open` prints `note: brief shape matches kind "<label>" (<n> earlier uses)`.
The shape is a hint: two different tasks can share one, and one task can vary.

## Patterns

```sh
check.py patterns [--min 3] [--since <days>] [--json]
```

Prints the overlay's `## Authoring` policy, then:

- **Candidates:** kinds with at least `--min` uses, no role of that name in the
  overlay, and no `approved` or `declined` mark. Each shows uses, worktrees,
  distinct days, outcomes (`done`, `stuck`, `abandoned`, `open`) and tiers.
- **Other kinds:** with why they aren't candidates.
- **Unlabeled shapes** with at least `--min` uses; give them a label.

`--since` counts only opens in that window and excludes archived counts. `--json`
returns the same data, plus aliases and the authoring policy.

## Retention

Pattern log lines older than 180 days are removed by `check.py state gc --apply`
(and the weekly sweep normal writes trigger). Before removal, each labeled open is
added to its kind's `archived` count, so totals survive; unlabeled shapes past
retention are dropped. Registry entries are not expired: they are small, and
decisions such as `declined` should persist. A retired repository's registry and
log are removed with its other repository state.

## Scratch

`brief` prints the delegation's scratch directory, `<scratch_directory>/<id>`.
Tiers may write throwaway scripts and intermediate files there without being
granted it in `May write`; it is outside the worktree, so it never changes the
tree hash. Scratch output is not evidence. Files untouched for 30 days are removed
by collection, and a deleted worktree's scratch goes with its cache. A script
worth keeping becomes a repository script only through the judge's authoring
path, which asks first where the overlay says `scripts: ask`.
