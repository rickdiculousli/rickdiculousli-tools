---
name: delegation
description: Use when the repository's AGENTS.md points to the delegation skill, or when the user asks to delegate work to execute or routine tier subagents. Keeps the main session (the judge) small by routing bulk work to cheaper tiers, and records validator evidence by git tree hash.
---

# Delegation

You are the **judge**: the main session. You plan, rule, review and diagnose. Bulk
work (reading many files, work a mechanical oracle verifies, independent parallel
items) goes to tier subagents, `execute` or `routine`, so your context stays
mostly hypotheses and rulings. **This skill is your explicit instruction to spawn
tier subagents for delegated work.**

`<skill-dir>` below means the directory containing this SKILL.md. All commands use

```sh
python3 <skill-dir>/scripts/check.py [--root <worktree>] <command> ...
```

`--root` goes before the command (default: the git root of the current
directory). Exit codes: 0 ok; 1 lint problems or a failing validator; 2 an error
or a refused operation (the reason is on stderr).

## 1. Load the overlay

The repo's overlay is `.agents/delegation.md`; its format is in
[reference/overlay.md](reference/overlay.md). At the start of a session, read it
and run `check.py lint`. Fix or report any problems it lists. If there is no
overlay, say once that base defaults apply (parallel limit 3, return cap 400
words, no validators, findings go to the execution log) and carry on. To create
or change an overlay, use the `setup` skill from this plugin.

## 2. Rules

1. **Delegate when the work's tokens far exceed the brief plus the review**: bulk
   reading, work a mechanical oracle verifies, or independent items that can run
   in parallel. Keep work yourself when it is short, depends on your accumulated
   hypotheses, or is a ruling.
2. **Pick the tier.** `execute` for work that needs reasoning but is pinned by a
   spec or oracle. `routine` for work with an obvious right answer. Use the
   overlay's `## Tier hints`. Neither tier guesses: `execute` stops and reports
   with evidence when stuck; `routine` reports oddities without interpreting them.
3. **Brief** with the template in
   [reference/return-format.md](reference/return-format.md): settled context,
   goal, inputs, what it may write, what it must not write, and the done
   condition or validators.
4. **Return format.** Don't write it: `check.py brief` appends the delegation
   id, the validator command, the return format and the overlay's return fields
   and cap to every brief.
5. **Batch and limit concurrency.** Group similar routine items into one call.
   Readers (write nothing, return data) may run in parallel up to the overlay's
   parallel limit. **At most one writer per worktree, and a writer runs alone.**
   `check.py open` enforces both.
6. **Read shared context once.** Parallel siblings that need the same material
   (a spec, shared types, conventions) each pay to read it. Fan out when that
   material is small next to each item's own work. When it is large, batch the
   items into fewer calls, or first delegate one `execute` reader to digest it:
   facts, signatures and conventions with refs, within the return cap. Review
   the digest, save it once to `.delegation/context/<name>.md`, and point every
   sibling's `Settled` field at it. Fill `Settled` yourself only from what you
   already know; don't read bulk material to write it.
7. **Sequence dependent work.** When one item needs another's output (shared
   types, module exports), open it after the producer is reviewed and in the
   worktree, and name the producer's paths or commit in its `Settled` field.
   Don't let parallel workers write their own copies of shared code; merging
   them costs more than waiting.
8. **Check focused, then broad.** A brief's `Done when` names the validators
   that cover its own change. After you combine a batch of work, run the broad
   ones (whole-workspace suites) once, by delegating them to one `routine`
   reader. Treat each writer's results as evidence for its part only, not for
   the combined tree.
9. **Single writer.** Subagents return proposed changes for the overlay's
   `## Single writer` resources. Only you apply them.
10. **Write findings as they happen** to the overlay's `## Findings` sink (else the
    execution log): id, date, claim, status (including `refuted`), evidence. Do it
    when a discovery or dead end is established, not at handoff. On the second
    similar brief, or at handoff, record a concrete script or reusable-role
    proposal in the repo findings/handoff sink (fallback: execution log), rather
    than only in session memory. Use `name: command; what it replaces` for
    deterministic rote scripts; writing repository scripts needs explicit approval; if the sink is
    tracked and delegations are open, see the hold in section 3, step 5.
11. **Check; don't redo.** Review ledger results and the diff. Read raw material
    only to dig into a specific doubt. A failed result keeps its full output in
    the file `log` names; read it there instead of rerunning the command.
12. **Quota zones**, when a relay or a soft limit is in play. You learn the zone
    from the relay or the user. At `last-task`, open no new implementation work:
    spend what's left on review, the broad check (rule 8) and findings. At
    `wrap`, close every open delegation before handing off (see section 6), and
    name any check that didn't finish in the close note.

## 3. Procedure

1. **Brief.** Choose an id matching `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` (a letter
   or digit first; never reused in this worktree). Write the brief to
   `.delegation/briefs/<id>.md` (create the folder if needed; `check.py`
   keeps `.delegation/` git-ignored). Don't edit it after opening: `open`
   records its hash, and the hash of every `.delegation/context/` file the brief
   names.
2. **Open.**

   ```sh
   python3 <skill-dir>/scripts/check.py open --delegation <id> --tier execute|routine --brief .delegation/briefs/<id>.md [--writes]
   ```

   Pass `--writes` if the subagent may edit the worktree. Exit 2 means refused:
   a writer is open, a writer was asked for while others are open, the parallel
   limit is reached, or the id was used. Wait for a close, or keep the work.
3. **Start the tier agent** (section 4). Its task is one line `open` printed,
   so the brief isn't written into your context a second time: `task:` for an
   agent defined with the tier's instructions, `task with instructions:` for any
   other subagent (it prints the tier's instructions first). The `task:` line:

   ```text
   Run `python3 <absolute skill-dir>/scripts/check.py --root <absolute worktree root> brief --delegation <id>` and follow the brief it prints exactly.
   ```

   `brief` prints the brief recorded at `open` with the fixed parts appended, and
   exits 2 if the delegation isn't open or the brief, or a context file it
   names, no longer matches its recorded hash. Tools don't expand shell syntax:
   never pass `$(cat ...)` or a bare path as the task.
4. **The subagent** works, runs validators only with the brief's `run` command
   (cheap ones while it works, then the brief's set cheapest first after its
   final edit, stopping at the first failure), and returns the report. `run` prints `<id>#<n> PASS|FAIL exit=<code>
   tree=<first 12 chars>`, with `unstable` appended if the tree changed while it
   ran. For the full hash use `query --json` or `check.py tree`.
5. **Review** before you change anything in the worktree:

   ```sh
   python3 <skill-dir>/scripts/check.py query --delegation <id> --tree current [--json]
   ```

   This lists only stable results recorded at the current tree; when there are
   none, stderr names the latest result and its tree instead. A
   `[checked: <id>#<n>]` claim stands only if that id is listed and passed;
   otherwise treat the claim as `asserted`. Then review the diff, apply proposed
   single-writer changes, and write findings. If you need fresh evidence after
   your edits, rerun validators under the same id before closing.

   **While delegations are open, hold edits to tracked files**, findings
   included: they change the tree, so a running check turns `unstable` and a
   finished one goes stale. Query those delegations first, or wait for them to
   return, then edit. Write the finding the moment the delegations are reviewed.
6. **Close.**

   ```sh
   python3 <skill-dir>/scripts/check.py close --delegation <id> --outcome done|stuck|abandoned [--note "<text>"]
   ```

`check.py run <validator> --delegation <id> [--timeout <seconds>]` needs the
delegation open. It uses the overlay's timeout for that validator unless
`--timeout` is given, waits for the validator's `lock` if the overlay sets one,
and keeps the full output in `.delegation/logs/<id>/<n>.log`; a failed run
prints that path. `check.py tree` prints the current tree hash.

### Reusable roles and continuations

The optional `## Roles` section registers a tier, runbook and at least one reuse
cap. Open a first use with `open --delegation <new-id> --tier execute --role capture --brief
.delegation/briefs/<new-id>.md`; continue it with `open --delegation <new-id> --tier execute
--continue <prior-id> --brief .delegation/briefs/<new-id>.md`. The prior use must
be closed, the tier stays the same, and the role session cannot have another open
brief. `--tier` remains required; a role validates it rather than selecting it.
Use a new delegation id and brief each time. Counters include the first
brief and all ancestor branches; every use records fresh brief/runbook hashes.
The byte cap accumulates supplied brief/context file sizes per use, excluding
outputs, rather than measuring actual model context. Prefer a use-count cap.

`open` prints a follow-up loader for Claude `SendMessage` or Codex
`collaboration.followup_task`. The judge maintains the mapping from delegation
ids to host agent ids; the checker does not know it. Preserve the original
tracked-file write permissions. Proactively refresh the runbook during the final
allowed use, after work and checks complete and before close. That change
invalidates the current brief's recorded hash; do not reload it afterward.

A cap refusal happens after the prior use is already closed. Open a separate
short refresh delegation without `--role` or `--continue`, granting `May write`
only for the already-authorized runbook. Send its loader to the existing host
agent solely to refresh, close the refresh delegation, then start a fresh role
session. Do not reuse the capped agent for more task work or reload an old closed
brief. Refreshing grants no additional tracked-file permissions.

### Asynchronous peer role calls

A caller brief names both the peer host id and caller delegation id. The peer
runs caller commands with `run ... --delegation <caller-id>` or
`exec --lock <name> --timeout <seconds> --delegation <caller-id> -- <command>`,
so the caller receives the ledger evidence. Keep the caller open through peer
completion. Serialize the role agent's actual execution; callers and the judge
may do independent work asynchronously while waiting. The judge receives stop
handbacks and resolves failures or required human action.

Claude peer messaging supplied and verified by the user supports `SendMessage`
ids that do not appear in `ListAgents`; stopped peers resume. See [host guidance](reference/hosts.md) and the repository
verification documentation for observed host evidence. Codex uses canonical agent
paths. `collaboration.send_message` does not
trigger an idle agent's turn; the judge uses `collaboration.followup_task` to
resume it. Check the current harness's capabilities before promising peer calls;
fall back to judge relay when unavailable. This observation does not guarantee
peer behavior on every Codex harness.

Brief footers give agent instructions for commit policy, committed prose, and
host-side isolation. They do not enforce filesystem access. A nonempty
`## Host side effects` section appends its prohibited changes to those instructions.

A registered validator marked `needs-human`, or a tier hint such as
`execute [needs-human]: native launches require human action`, requires the judge
to notify the user before work and early while the user is present. Stop
for needed human action; do not retry indefinitely.

**Locks** (overlay `## Locks`) cap how many heavy commands run at once across
every worktree of the repo. `check.py exec --lock <name> --timeout <seconds>
[--delegation <id>] -- <command>` runs any other command under a lock (the brief
footer shows subagents this command). `check.py locks` shows who holds each
slot; check it when a subagent reports waiting. If this machine can take more or
fewer than the overlay's slots, set `DELEGATION_LOCK_<NAME>` for the session
(see [reference/overlay.md](reference/overlay.md)). Locks also protect physical
resources, for example `games: slots=6, wait=3600`. `exec` holds a slot for the
complete foreground process lifetime; never detach a launch. One command owns
one slot: multiple jobs must acquire a slot per child or serialize, otherwise
they oversubscribe the resource. Windows uses native byte locks; macOS/Linux use
`flock`. Ledger reads and appends use the same native lock to prevent partial reads.
`exec` requires both `--lock` and `--timeout`. With a delegation id its ledger
results have `validator=null`: cite command observations or mark them `asserted`;
they cannot count as `checked` registered-validator acceptance.

## 4. Starting a tier on this host

Read [reference/hosts.md](reference/hosts.md) for this host's tier table and
exact start instructions. **On Claude Code, never pass `model` or `effort` when
starting a tier agent**: the generated definition carries them, and a per-call
value overrides it.

## 5. Judge setting

The judge is expected to run at **medium effort** on its host's judge model
(table in `reference/hosts.md`). This skill can't set that. If you know the
session is at another setting, say so once and continue.

## 6. Pods and relay

A pod is you plus your subagents. Pods never depend on a relay, but one may hand
your session to another provider. Subagents can't survive that switch, so:

- At quota zone `last-task`, open no new implementation delegations. A short
  `routine` reader for the broad check is fine if it can finish before `wrap`.
- At `wrap`, close every open delegation (as `abandoned` if unfinished) before
  handing off. Findings, the ledger and the execution log carry the state.
- The relay's release check runs `check.py pending --json` and requires an empty
  list. Its exact output shape:

  ```json
  {"pending": [{"delegation": "<id>", "tier": "execute|routine", "writes": false, "opened": "<UTC ISO-8601>", "tree": "<hash>"}]}
  ```

## 7. Errors

- **No overlay:** base defaults apply; say so once.
- **A validator fails:** the ledger records it (exit 1). The claim is `asserted`,
  not `checked`.
- **An executor is stuck:** it stops and reports its evidence. Close the
  delegation as `stuck`, then rule on the next step yourself.
- **The host lacks the generated tier definitions:** follow this host's
  fallback in `reference/hosts.md`.
- **`check.py` exits 2:** read stderr. It refuses rather than guesses; don't work
  around a refusal by editing `.delegation/`.
