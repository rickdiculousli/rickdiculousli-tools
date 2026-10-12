# Overlay format

`.agents/long-horizon.md` is Markdown with a title, an optional `## Version`
heading holding one plugin version line (like `0.5.0`), and named level-two
headings below. Setup and migrate write `## Version` after a clean lint. `status`
warns `version-mismatch` when it is missing or its major.minor is older than the
installed plugin, and `version-newer` when it is newer; patch differences are
ignored. A `## Schema` heading is superseded: it is ignored and lint reports it
as `layout-outdated`. Headings/keys are case-insensitive;
values retain case. Each nonblank line under a heading is `key: <JSON value>`
(optionally `- key:`). Full-line `<!-- comments -->` are allowed. Duplicate or
unknown keys/headings and wrong types are errors. No YAML, inline comments or
command interpolation. JSON arrays/maps must fit one line.

| Heading | Keys: types and defaults |
| --- | --- |
| State | `state`: string active (default) or dormant |
| Goals and ownership | `path`: string docs/goals.md; `milestone-policy`: user; `task-refinement`: agent; `task-completion`: agent; `milestone-completion`: agent; `goal-signoff`: user. Ownership strings are user or agent. |
| Goals format | `markers`: object with four distinct nonempty literal strings current/done/shelved/dropped; defaults `— current`, `— done`, `— shelved`, `— dropped`. No regex. |
| Continuation | `handoff`: string docs/handoff.md; `archive`: string docs/goals-archive; `findings`: string array []; `evidence`: string docs/evidence; `non-code`: string array defaulting to configured goals/handoff/archive/findings; `handoff-budget`: positive integer 80 |
| Startup | `command`: string; `effects`: string array; `context`: string; `readiness`: string `cache:<relative-json-path>` resolved under this worktree’s XDG cache `readiness/` directory; any other value is `layout-outdated` and not read. All absent by default. Command/effects describe actual skill authorization, never an instruction executed by status. |
| Capabilities | `tags`: object mapping tag to array of named readiness levels; default `{"any": []}`. All tags/levels required; unknown tags ineligible. |
| Evidence | `checks`: object {}; `inputs`: object {}; `delegation-script`: string literal path OR `delegation-env`: string variable name; `validator-policy`: string path; when delegation is configured defaults to .agents/delegation.md |
| Batch | `tasks`: positive integer 1; `blocker-resolutions`: positive integer 1; `quota`: boolean false; `quota-script`: string literal path OR `quota-env`: string variable name |
| Integration | `steps`: string array []; `target`: string branch; `remote`: string; `sync`: string operation; `stop-conditions`: string array []; `authorization`: string. Nonempty steps need actual recorded authorization. Ordered unique steps: validate, commit, merge, push, sync. Merge/push need target, push needs remote, sync needs operation. |

Each Evidence check key is the exact token, such as `validator:unit`. Its object:
`scope` (optional string array of Git pathspecs), `inputs` (string array of declared
input names, default []), `domain` (string, default default), `allowed-skips`
(string array of exact domains where SKIP is allowed, default []), `validator`
(optional registered delegation validator name, otherwise token suffix).
Each input object has exactly `command` (nonempty argv string array), `timeout`
(number >0 and <=60 seconds), `recover` (nonempty string route). These describe
cheap, read-only, authorized probes; output must be exactly one lowercase SHA-256.
Probes only execute with `--probe-inputs` on evidence/gate commands.

Managed goals/handoff/archive/findings/evidence paths stay inside the current
checkout even through symlinks. Explicit draft relative paths resolve under
`--draft-root`; Git identity remains the actual `--root` checkout. Context and
recovery links may be external. Explicit missing script/env values are findings;
no guessed checkout/cache paths. Omitted Integration authorizes no operation.
The evidence sink is excluded from default code scope, but acceptance policy is
fingerprinted separately. Other Markdown files are not implicitly non-code.

Quick setup (Integration added only after actual approval):

```markdown
# Long-horizon
## Goals and ownership
path: "docs/goals.md"
## Integration
steps: ["validate", "commit", "merge", "push"]
target: "main"
remote: "origin"
authorization: "User approved standing batch closure on 2026-10-11."
```

A full example:

```markdown
# Long-horizon
## Version
0.5.0
## State
state: "active"
## Goals and ownership
path: "docs/project goals.md"
milestone-policy: "user"
task-refinement: "agent"
task-completion: "agent"
milestone-completion: "agent"
goal-signoff: "user"
## Continuation
handoff: "docs/handoff.md"
archive: "docs/goals-archive"
findings: ["research/findings.jsonl"]
evidence: "docs/evidence"
handoff-budget: 80
## Startup
command: "python3 tools/resume.py"
effects: ["read local files", "write XDG readiness cache and identity"]
context: "docs/current-context.md"
readiness: "cache:readiness.json"
## Capabilities
tags: {"any": [], "fixtures": ["fixtures"], "native": ["fixtures", "native"]}
## Evidence
checks: {"validator:unit": {"scope": ["src/**", "tests/**"], "domain": "fixtures-v1", "inputs": ["corpus"], "allowed-skips": [], "validator": "unit"}, "observation:review": {"domain": "design-v1", "reviewer": "human"}}
inputs: {"corpus": {"command": ["python3", "tools/input_digest.py"], "timeout": 10, "recover": "docs/capture.md#corpus"}}
delegation-env: "DELEGATION_CHECK_SCRIPT"
validator-policy: ".agents/delegation.md"
## Batch
tasks: 1
blocker-resolutions: 1
quota: false
## Integration
steps: ["validate", "commit", "merge", "push"]
target: "main"
remote: "origin"
stop-conditions: ["dirty target checkout", "rejected push"]
authorization: "User approved these named local/remote operations on 2026-10-11."
```

An `observation:` check takes an optional `reviewer`: `"human"` (the default) or
`"any"`, which also accepts an agent reviewer. Other checks reject the key.

Every leaf command accepts `--root`, `--overlay`, `--json`, `--draft-root`,
`--goals`, `--handoff` after its name (e.g. `evidence prepare validator:unit --root
... --json`). Explicit dry-run path overrides do not activate draft policy.
JSON contains version 1, command, ok, findings (severity/code/path/line/message/
remedy) and structured command data. Exit 0: inspection succeeded, warnings,
manual/no selection and absent evidence allowed. Exit 1: inconsistent hierarchy,
failed required acceptance or unfinished verified closure. Exit 2: invalid
usage/environment. `--json` emits JSON only to stdout.
