---
name: pick-principles
description: Picks and reads the principles and skills that fit a phase change in nontrivial work, and writes them into builder briefs. Use before designing, building, debugging, migrating or deleting, reporting a number, briefing a builder, or editing what steers an agent.
---

Without this, an agent crosses from one phase into the next on its own judgment. The lessons in the installed principles and skills never reach the work, or the subagents doing it.

Skip it for a lookup, a one-step change, or a subagent sent only to find or read something.

## At each threshold

1. **Check that the step before happened.** A build needs a design settled with the user and written down; a spec needs a settled design; a deletion needs to know how far back the evidence of use reaches. If the step is missing, do it first.
2. **Pick only what changes a decision,** usually two to five, from the table below and the skills the harness lists.
3. **Read each pick's SKILL.md in full,** unless you already have this session. Cite only what you've read.
4. **Apply them.**
   - In your own work, name each pick and the choice it changed.
   - In a builder's brief, add a "Principles for this task" section. Give each pick's absolute SKILL.md path and one line on how it applies here, and have the builder read them before starting.
5. **Tell the user in one sentence** what each pick changes, for example: "Using subtract-before-you-add (duplicates go before anything new) and prove-it-works (a script shows nothing was lost)."

## Where they live

- **pstack principles:** `<pstack>/skills/principle-<name>/SKILL.md`, where `<pstack>` is the newest of `~/.claude/plugins/cache/cursor-plugins/pstack/*/`. Find it with `ls -d ~/.claude/plugins/cache/cursor-plugins/pstack/*/ | sort -V | tail -1`. They aren't invocable as skills in Claude Code, so read them by path. For picks the table misses, the `## Principles` section of `<pstack>/skills/poteto-mode/SKILL.md` lists every principle with when it applies.
- **Everything else:** the skills the harness lists. Read those through the Skill tool, or by path for a subagent.

## Thresholds and the usual picks

| Threshold | Principles | Skills |
|---|---|---|
| Starting a design, or fitting a new requirement into one | redesign-from-first-principles, model-the-domain, foundational-thinking; exhaust-the-design-space when there's no precedent | pocock:grilling with pocock:domain-modeling, pocock:codebase-design |
| Design → spec or plan | sequence-verifiable-units, outcome-oriented-execution | method:writing-plans |
| Design → build | subtract-before-you-add, laziness-protocol, build-the-lever, prove-it-works | pocock:codebase-design |
| Debugging | fix-root-causes | |
| A second round failing the same way (a fix, a trial, a prompt version) | attack-the-premise | |
| Migrating or deleting | migrate-callers-then-delete-legacy-apis, make-operations-idempotent, sequence-verifiable-units | |
| Trusting or reporting a number | explain-the-number | benchmark-checklist (read by path, in `<pstack>/skills/`) |
| Briefing a builder | guard-the-context-window | |
| Declaring done | prove-it-works | |
| Writing or editing what steers an agent: a skill, an agent file, `AGENTS.md` or `CLAUDE.md`, rules, role prompts | subtract-before-you-add | skill-shaper:skill-shaper. Its newcomer test, baseline run and description rules hold for any of these, not only skills |

## Lessons from Rick's work

- **Deleting:** before calling anything unused, say how far back the evidence reaches. Session history, run logs and git history can differ by months. Never delete what the user asked for on usage evidence alone.
- **Steering text:** cutting history and dead references isn't enough. Run a fresh agent on a real ask without the text, keep what it got wrong and the local facts, and cut the rest.
- **Measuring:** judge by the user's real use, never by a question set the agents wrote. A gain that disappears on unseen questions was tuning.
