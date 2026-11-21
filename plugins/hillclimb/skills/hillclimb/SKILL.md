---
name: hillclimb
description: Improves a piece of work round by round until fresh LLM judges score each chosen aspect at its target out of 10, such as 9.5/10. Use when the user asks to hill-climb something, or to iterate on it until reviewers rate it some score.
---

Without this, the judging drifts: one reviewer scores everything, judges see the last round's scores or the target and anchor on them, and the same settled complaint costs points every round.

## 1. Pin the task

Take the work and its goal from the conversation: what is being improved (a file, a diff, a plan, a prompt), who it is for, and what it must do. If either is unclear, ask in one message before anything else.

## 2. Let the user pick aspects and targets

Suggest the aspects that matter for this task, numbered, each with one line on what a 10 looks like and a suggested target. Put closely related aspects on one line as a pair when one reading judges both; the pair gets one judge. Offer any invariants already settled in the conversation (see step 3). Then ask, for example:

```text
1. Correctness: every claim and command is true for the code as it stands. Target 9.5
2. Clarity + structure: a newcomer finds and follows the steps in order. Target 9.5
3. Concision: no line the reader doesn't need. Target 9
4. Tone: plain, no hype. Target 9

Reply with numbers to keep and their targets ("1 9.5, 2 9, drop 4"), add your own ("+ accessibility 9"), and any invariants.
```

Spawn no judge until the user has replied. Their reply is the go-ahead for the whole climb.

## 3. Keep the invariants

An invariant is a point the user has ruled on: something judges must not deduct for or ask to change. Keep the list in the conversation, numbered, in the user's words. It goes verbatim into every judge brief from then on.

When a judge's deduction contradicts an invariant, discard it. When a judge deducts for something you think the user would keep, or two judges ask for opposite changes, ask the user to rule and offer to add the ruling as an invariant. Add one only when they say so.

## 4. Judge with fresh subagents

Each round, spawn one fresh read-only subagent per aspect or pair, all at once, in parallel. Never resume or reuse a judge from an earlier round; a fresh one is the point. Use the session's model unless the user names another.

Give each judge:

- the work itself (its path, or the text) and its goal and audience
- its aspect or pair, with what a 10 looks like
- the invariants, as "already decided; do not deduct for or suggest changing these"
- what to return: a score out of 10 to one decimal for each aspect, then each deduction with where it is, why it costs points and the change that would remove it

Never tell a judge the target, an earlier score, what changed, or that the work has been revised. Each one anchors the score.

## 5. Climb

After each round, show a scoreboard: one row per aspect, a column per round, the target last. Then revise the work against the deductions, aspects furthest below target first. A deduction you disagree with and that isn't an invariant goes to the user, not silently ignored. Judge every aspect every round, including those already at target, since a fix for one can cost another.

Stop when every aspect meets its target in the same round. Also stop and show the user the remaining deductions when an aspect hasn't risen for two rounds, or after five rounds: the target may be out of reach, the aspects may conflict, or a deduction may be one they want as an invariant. Ask before going further.

## 6. Report

End with the scoreboard, the invariants, what changed overall, and any deduction left standing at the end with why.
