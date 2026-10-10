# Delegation Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `delegation` plugin 0.1.0: a base skill, overlay format, generated `execute`/`routine` tier definitions from one `tiers.json`, and a stdlib `check.py` evidence ledger keyed by delegation id and tree hash.

**Architecture:** `check.py` is a thin CLI over a small stdlib package (`delegation_check`: overlay parsing and lint, tree hashing with a temporary index, an append-only JSONL ledger). `scripts/sync_marketplaces.py` gains a tiers step that turns `plugins/<name>/tiers.json` into committed Claude agent files and a generated host table the skill reads. The skill itself is Markdown that names tiers only.

**Tech Stack:** Python 3.10+ standard library (`argparse`, `json`, `hashlib`, `subprocess`, `fcntl`, `unittest`), git, Claude Code 2.1.296 and Codex 0.162.1 CLIs.

**Spec:** [docs/superpowers/specs/2026-10-09-delegation-design.md](../specs/2026-10-09-delegation-design.md)

## Global Constraints

- Plugin `delegation`, version `0.1.0`, listed last in `catalog.json`; skill `delegation`; all skill files under `plugins/delegation/skills/delegation/`.
- Python 3.10+ standard library only, for scripts and tests. No build step for consumers.
- Generated files (host manifests, marketplaces, agent definitions, `reference/hosts.md`) are only ever written by `python3 scripts/sync_marketplaces.py`, and committed with their sources.
- Tier models, verbatim: judge = `claude-opus-5-5` effort `medium` / `gpt-6.1-sol` effort `medium`; execute = `claude-sonnet-5-5` (host default effort) / `gpt-6.1-sol` effort `low`; routine = `claude-haiku-5-5` (default) / `gpt-6-luna` (default). No `judge` definition is generated.
- `check.py` writes only inside the worktree it runs in: never to `$TMPDIR`, the git directory or the real index.
- At most one writer per worktree; parallel readers up to the overlay's `## Parallel limit` (default 3). Return cap default 400 words.
- Claim labels are exactly `checked`, `cited`, `asserted`; close outcomes exactly `done`, `stuck`, `abandoned`; findings statuses include `refuted`.
- Lifecycle tests use the verifier's disposable profiles. Never modify Rick's normal Claude or Codex configuration for automation.
- Work in a T3-created worktree under `a separate worktree`, never inside the repo.
- Don't claim model-driven, GUI or remote checks unless they were performed. `docs/verification.md` records actual versions.

### Decisions made while planning (fold into the spec in Task 6)

- **State directory.** Ledger state lives in `<root>/.agents/delegation/`, which `check.py` creates with a `.gitignore` containing `*`. This replaces the spec's `.agents/delegation-ledger.jsonl`, so consuming repos need no ignore rule. The ledger is `ledger.jsonl`, the lock is `ledger.lock`, and temporary indexes are `tmp-index-<pid>-<hex>`. Briefs go in `briefs/<id>.md`.
- **Writer enforcement.** `check.py open --writes` refuses to start a writer while any delegation is open, refuses any delegation while a writer is open, and refuses a reader once open readers reach the parallel limit.
- **Codex route** (Rick, 2026-10-09). If Codex plugins can't ship agent definitions but spawn-time model and effort work, the Codex skill spawns its default subagent with the tier's model and effort from the generated host table. The spec's same-model fallback applies only if spawn-time values don't work either.
- **Claude spawn rule.** The Agent tool's per-call `model` overrides frontmatter, so the skill forbids passing `model` or `effort` when starting a tier agent. `CLAUDE_CODE_EFFORT_LEVEL` and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` override definitions, and `hosts.md` says so.

## Review Focus

- Writing the ledger or the temporary index must not change the tree hash, or every check goes stale the moment it's recorded. Tested in Task 3 (`test_state_dir_does_not_change_tree`).
- Several readers calling `check.py run` at the same moment must each get a distinct result id, with no interleaved or torn JSONL lines. Tested in Task 5 (`test_concurrent_runs_get_distinct_ids`).
- A validator that edits tracked files while it runs must not produce a `checked` result at either tree. Tested in Task 5 (`test_validator_that_edits_tree_is_unstable`).
- A repo with no commits and no index, and a linked worktree whose git directory is outside it, must both hash. Tested in Task 3.
- Overlays edited on other machines must still parse: CRLF line endings, heading case, trailing spaces, `- ` list markers and backticked paths. Tested in Task 2 (`test_tolerant_parsing`).

---

## Shared test support

`tests/delegation_support.py` (created in Task 2) puts `plugins/delegation/skills/delegation/scripts` on `sys.path` and provides:

- `git_repo(path: Path) -> Path`: runs `git init -q`, sets local `user.name`/`user.email`, writes `a.txt` = `"a\n"`, commits it, and returns `path`.
- `write_overlay(root: Path, text: str) -> Path`: writes `root/.agents/delegation.md`.
- `run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]`: runs `sys.executable <scripts>/check.py *args` with `cwd=root`, text output, no `check`.

---

### Task 1: Step 0, host capabilities

No code. Its outcome sets `routes.codex` in Task 7.

**Files:**
- Modify: `docs/verification.md` (new section `## Delegation host capabilities (step 0)`)

- [ ] **Step 1: Can a Codex plugin ship agent definitions?** Read the plugin loader for the installed version in `openai/codex` (`gh api` / `gh search code` for the plugin manifest struct and any `agents` handling in `codex-rs`, at tag `rust-v0.162.1`), plus https://developers.openai.com/plugins/build/plugins and https://learn.chatgpt.com/docs/agent-configuration/subagents. Record the answer, the file and line references, and whether anything other than skills, MCP, apps, hooks and assets is loaded. Label it `cited` (source reading), not `checked`.
- [ ] **Step 2: Do spawn-time model and effort work on Codex?** From a scratch directory, run `codex exec --sandbox read-only` with a prompt asking it to spawn one subagent using model `gpt-6-luna` and reasoning effort `low` that replies `ok`. Use the normal profile's auth and pass no `-c` changes to persistent config. Find the child session's rollout under `~/.codex/sessions/` and record its `model` and effort fields verbatim. Repeat once with `gpt-6.1-sol` at `low`.
- [ ] **Step 3: Decide `routes.codex`.**
  - `definitions` if Step 1 found a supported plugin path. Record the exact directory and file format. Task 7 then adds a TOML writer for that path, with fields `name` (`delegation-<tier>`), `description`, `developer_instructions`, `model` and `model_reasoning_effort`.
  - Otherwise `spawn` if Step 2's rollouts show the requested model and effort.
  - Otherwise `same-model`.
- [ ] **Step 4: Record and commit.** Write the section: date, `codex --version`, `claude --version`, each answer with its evidence and label, and the chosen route. Claude Code: cite the subagent docs (plugin agents honour `model` and `effort`; `hooks`, `mcpServers`, `permissionMode` and `initialPrompt` are ignored). The live Claude check happens in Task 8.

```bash
git add docs/verification.md && git commit -m "docs(delegation): record step 0 host capabilities"
```

### Task 2: Overlay parsing and lint

**Files:**
- Create: `plugins/delegation/skills/delegation/scripts/delegation_check/__init__.py`, `.../delegation_check/overlay.py`, `.../delegation_check/cli.py`, `.../scripts/check.py`
- Create: `tests/delegation_support.py`, `tests/test_delegation_overlay.py`

**Interfaces:**
- Produces, in `delegation_check/__init__.py`: `class DelegationError(Exception)`, raised for refused operations and environment errors.
- Produces, in `overlay.py`:
  - `KNOWN_HEADINGS: tuple[str, ...]`: the ten spec headings, in spec order.
  - `DEFAULT_PARALLEL_LIMIT = 3` and `DEFAULT_RETURN_CAP = 400`.
  - `overlay_path(root: Path) -> Path`: returns `root/.agents/delegation.md`.
  - `load_overlay(root: Path) -> Overlay`. It never raises on content and collects problems instead.
  - `@dataclass(frozen=True) class Overlay` with fields `path: Path`, `exists: bool`, `sections: dict[str, str]` (canonical heading to body), `validators: dict[str, str]`, `extra_inputs: tuple[str, ...]`, `parallel_limit: int`, `return_cap: int`, `problems: tuple[str, ...]`.
- Produces, in `cli.py`: `main(argv: list[str] | None = None) -> int`, with global `--root PATH` (default: `git rev-parse --show-toplevel` of the cwd; Task 3 supplies `repo_root`, and until then use `Path.cwd()`). It also produces the subcommand `lint`. `check.py` only calls `sys.exit(main())`. Exit codes: 0 ok, 1 lint problems or failing validator, 2 `DelegationError` or usage.

Parsing rules:
- `##` headings match `KNOWN_HEADINGS` case-insensitively after stripping. The `#` title is ignored.
- Body lines drop a leading `- ` and blank lines are skipped. `## Validators` lines are `name: command`, with name matching `[a-z0-9][a-z0-9_-]*`. `## Extra inputs` lines are paths with surrounding backticks stripped.
- `## Parallel limit` and `## Return cap` take the leading integer, and the rest of the line is a comment.
- A validator reference anywhere in the overlay is written `validator:<name>`.

- [ ] **Step 1: Write the failing tests**

```python
class OverlayTests(unittest.TestCase):
    def test_missing_overlay_uses_defaults(self):
        o = load_overlay(self.root)
        self.assertFalse(o.exists); self.assertEqual((o.parallel_limit, o.return_cap), (3, 400))
        self.assertEqual(o.problems, ())
    def test_parses_spec_example(self):  # the game-decomp overlay from the spec, verbatim
        o = load_overlay(self.root)
        self.assertEqual(o.validators["refs"], "uv run --no-project python -I research/modules/check_refs.py")
        self.assertEqual(o.parallel_limit, 3); self.assertEqual(o.problems, ())
    def test_tolerant_parsing(self):  # CRLF, "## validators  ", "- unit: x", "- `golden/trace.bin`"
        o = load_overlay(self.root)
        self.assertEqual(o.validators, {"unit": "x"}); self.assertEqual(o.extra_inputs, ("golden/trace.bin",))
    def test_lint_problems(self):
        # "## Bogus", duplicate "## Oracle", "bad line" under Validators, duplicate validator,
        # "## Parallel limit\nmany", extra input "../x", reference validator:trace-diff unregistered
        problems = "\n".join(load_overlay(self.root).problems)
        for needle in ('unknown heading "Bogus"', 'duplicate heading "Oracle"', 'expected "name: command"',
                       'duplicate validator "unit"', "Parallel limit", "escapes the repository: ../x",
                       'unregistered validator "trace-diff"'):
            self.assertIn(needle, problems)
    def test_cli_lint_exit_codes(self):
        self.assertEqual(run_cli(self.root, "lint").returncode, 0)   # no overlay: says defaults apply
        write_overlay(self.root, "## Bogus\n")
        r = run_cli(self.root, "lint"); self.assertEqual(r.returncode, 1); self.assertIn("Bogus", r.stdout)
```

Each problem string carries `line N: ` where a line exists.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_delegation_overlay -v`. Expected: FAIL (`ModuleNotFoundError: delegation_check`).
- [ ] **Step 3: Implement** `overlay.py`, `cli.py` (`lint` prints each problem, or `Overlay OK: <path>`, or `No overlay at <path>; base defaults apply.`) and `check.py`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(delegation): parse and lint the per-repo overlay`.

### Task 3: Tree hash

**Files:**
- Create: `plugins/delegation/skills/delegation/scripts/delegation_check/tree.py`, `tests/test_delegation_tree.py`
- Modify: `delegation_check/cli.py` (subcommand `tree`, and `--root` resolution via `repo_root`)

**Interfaces:**
- Produces, in `tree.py`:
  - `repo_root(start: Path) -> Path`: wraps `git rev-parse --show-toplevel` and raises `DelegationError("check.py needs a git worktree: <start>")`.
  - `state_dir(root: Path) -> Path`: creates `root/.agents/delegation/` and its `.gitignore` (`*\n`) if missing, then returns it.
  - `git_tree(root: Path) -> str`.
  - `tree_hash(root: Path, extra_inputs: Sequence[str] = ()) -> str`.

Algorithms:
- **`git_tree`.** Take a temporary index path in `state_dir(root)`. Copy the real index (`git rev-parse --git-path index`, resolved against `root`) to it if one exists; otherwise leave the path absent, since git rejects an empty file. Run `git add -A` then `git write-tree` with `GIT_INDEX_FILE=<tmp>`. Remove the temp file and `<tmp>.lock` in `finally`. A failing git call raises `DelegationError` with git's stderr.
- **`tree_hash` with no extras** is `git_tree(root)`.
- **`tree_hash` with extras** is the SHA-256 hex digest of `f"git {git_tree}\n"`, followed by `f"{path}\t{digest}\n"` for each path in sorted order.
  - A file's digest is the SHA-256 of its bytes.
  - A directory's digest is the SHA-256 of sorted `f"{relposix}\t{file_sha}\n"` lines over its files. `os.walk` doesn't follow directory symlinks.
  - A missing path's digest is `missing`.
  - So a 40-character tree is a plain git tree, and a 64-character tree includes extras.

- [ ] **Step 1: Write the failing tests**

```python
class TreeTests(unittest.TestCase):
    def test_stable_when_nothing_changes(self): self.assertEqual(tree_hash(self.root), tree_hash(self.root))
    def test_changes_on_edit_untracked_and_extra_input(self):
        t0 = tree_hash(self.root); (self.root / "a.txt").write_text("b\n"); t1 = tree_hash(self.root)
        (self.root / "new.txt").write_text("n\n"); t2 = tree_hash(self.root)
        self.assertEqual(len({t0, t1, t2}), 3)
        (self.root / ".gitignore").write_text("golden/\n"); (self.root / "golden").mkdir()
        (self.root / "golden/t.bin").write_bytes(b"1"); e1 = tree_hash(self.root, ["golden"])
        (self.root / "golden/t.bin").write_bytes(b"2"); self.assertNotEqual(e1, tree_hash(self.root, ["golden"]))
        self.assertEqual(len(e1), 64)
    def test_ignored_file_does_not_change_tree(self): ...  # ignored build output: tree unchanged
    def test_never_touches_real_index(self):
        # stage a change, record .git/index bytes and `git diff --cached --name-only`;
        # after tree_hash both identical
    def test_state_dir_does_not_change_tree(self):
        t0 = tree_hash(self.root); (state_dir(self.root) / "ledger.jsonl").write_text("{}\n")
        self.assertEqual(t0, tree_hash(self.root)); self.assertEqual(list(state_dir(self.root).glob("tmp-index-*")), [])
    def test_repo_without_commits(self):  # git init only, one untracked file → 40-hex tree
    def test_linked_worktree(self):  # `git worktree add <tmp>/wt` → hashes; no files written outside <tmp>/wt except git's own
    def test_not_a_repo(self): self.assertEqual(run_cli(Path(tempdir), "tree").returncode, 2)
    def test_cli_tree_prints_hash(self): self.assertRegex(run_cli(self.root, "tree").stdout.strip(), r"\A[0-9a-f]{40}\Z")
```

- [ ] **Step 2: Run** `python3 -m unittest tests.test_delegation_tree -v`. Expected: FAIL (no `tree` module).
- [ ] **Step 3: Implement** `tree.py`, and `tree` in `cli.py`, which prints `tree_hash(root, overlay.extra_inputs)`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(delegation): tree hash via a temporary index inside the worktree`.

### Task 4: Ledger lifecycle (open, close, pending)

**Files:**
- Create: `plugins/delegation/skills/delegation/scripts/delegation_check/ledger.py`, `tests/test_delegation_ledger.py`
- Modify: `delegation_check/cli.py` (subcommands `open`, `close`, `pending`)

**Interfaces:**
- Consumes: `state_dir` and `tree_hash` from Task 3, and `load_overlay` from Task 2.
- Produces, in `ledger.py`:
  - `SCHEMA = 1` and `ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")`.
  - `ledger_path(root: Path) -> Path`: returns `state_dir(root)/"ledger.jsonl"`.
  - `read_events(root: Path) -> list[dict]`: a missing file gives `[]`, and a malformed line raises `DelegationError("ledger line N: ...")`.
  - `append_event(root: Path, event: dict) -> dict`: adds `schema` and `timestamp` (UTC ISO, seconds), and writes one line under `ledger_lock`.
  - `ledger_lock(root: Path)`: a context manager using `fcntl.flock` on `ledger.lock`, and a no-op where `fcntl` is unavailable.
  - `open_delegation(root, delegation: str, tier: str, brief: Path, writes: bool, parallel_limit: int, extra_inputs: Sequence[str]) -> dict`.
  - `close_delegation(root, delegation: str, outcome: str, note: str | None) -> dict`.
  - `pending(root) -> list[dict]`: returns open events with no close, in order.

Event shapes:
- `open`: `{schema, event: "open", delegation, timestamp, tier, writes, brief, brief_sha256, tree}`.
- `close`: `{schema, event: "close", delegation, timestamp, outcome, note}`.

Refusals, each a `DelegationError` (CLI exit 2):
- an invalid id;
- a tier other than `execute`/`routine`;
- a missing brief;
- an id that was ever opened before;
- closing an id that isn't open;
- the writer rules from Global Constraints.

Check the refusals and append under one `ledger_lock`.

CLI:
- `open --delegation ID --tier T --brief PATH [--writes]` prints `opened ID (tier, reader|writer) at <tree[:12]>`.
- `close --delegation ID --outcome done|stuck|abandoned [--note TEXT]`.
- `pending` prints one `ID tier reader|writer opened <timestamp>` line per delegation, or `No open delegations.`
- `pending --json` prints `{"pending": [{"delegation", "tier", "writes", "opened", "tree"}]}`. This is the relay's contract, and empty means releasable.

- [ ] **Step 1: Write the failing tests**: `test_open_close_pending_roundtrip` (open two readers, close one as `done`, `pending --json` lists exactly the other), `test_refusals` (each refusal above, exit 2, ledger unchanged), `test_writer_rules` (a writer refused while a reader is open; a reader refused while a writer is open; a fourth reader refused at limit 3; and a reader allowed at `## Parallel limit\n4`), `test_open_records_tree_and_brief_hash`, and `test_pending_json_empty` (`{"pending": []}`).
- [ ] **Step 2: Run** `python3 -m unittest tests.test_delegation_ledger -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `ledger.py` and the three subcommands.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(delegation): ledger lifecycle with single-writer enforcement`.

### Task 5: Validators and queries (run, query)

**Files:**
- Modify: `delegation_check/ledger.py`, `delegation_check/cli.py`
- Create: `tests/test_delegation_run.py`

**Interfaces:**
- Produces, in `ledger.py`:
  - `run_validator(root: Path, delegation: str, name: str, command: str, extra_inputs: Sequence[str], timeout: float | None) -> dict`.
  - `query(root: Path, delegation: str, tree: str | None) -> list[dict]`.

Result event fields:
- the spec's fields: `schema`, `event: "result"`, `delegation`, `timestamp`, `validator`, `command`, `exit`, `duration_s`, `tree`, `output_sha256`, `output_tail`;
- `id`, which is `f"{delegation}#{n}"` with n counting the delegation's results from 1, assigned under the lock at append time;
- `stable`, which is whether the tree hash taken after the run equals the one taken before;
- `timed_out`.

Behaviour:
- The delegation must be open. Run the command with `shell=True`, `cwd=root` and stderr merged into stdout. Don't hold the lock while the validator runs.
- `output_tail` is the last 40 lines, capped at 4,000 characters. A timeout records `exit: null` and `timed_out: true`.
- `query(tree=X)` keeps results whose `tree == X` and that are `stable`. `tree=None` keeps all results.

CLI:
- `run VALIDATOR --delegation ID [--timeout S]`: an unknown validator gives exit 2 listing the registered names. It prints `<id> PASS|FAIL exit=<n> tree=<12>` plus the tail on failure, and exits 0 on pass, 1 on fail or timeout.
- `query --delegation ID [--tree current|HASH] [--json]`: `current` recomputes the hash. `--json` prints `{"tree": <hash or null>, "results": [...]}`, and the text form prints one line per result.

- [ ] **Step 1: Write the failing tests**:
  - `test_run_appends_result` (`ok: true`, id `d1#1`, stable, exit 0);
  - `test_failing_validator_exits_1`;
  - `test_query_filters_by_delegation_and_tree` (a run, then an edit to `a.txt`; `--tree current` excludes the old result, and no `--tree` includes it);
  - `test_validator_that_edits_tree_is_unstable` (a validator `echo x >> a.txt` gives `stable: false`, excluded at both trees);
  - `test_concurrent_runs_get_distinct_ids` (four processes, each running `sleep 0.2` for its own open reader at `## Parallel limit\n4`, started together; four parseable result lines with distinct ids);
  - `test_run_requires_open_delegation` (exit 2);
  - `test_timeout_is_recorded`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_delegation_run -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `run_validator`, `query` and both subcommands.
- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(delegation): run registered validators and query evidence by tree`.

### Task 6: Skill, references and plugin manifest

**Files:**
- Create: `plugins/delegation/plugin.json`, `plugins/delegation/skills/delegation/SKILL.md`, `.../reference/overlay.md`, `.../reference/return-format.md`
- Modify: `catalog.json` (append `plugins/delegation`), `docs/superpowers/specs/2026-10-09-delegation-design.md` (the planning decisions above)
- Generated: host manifests and marketplaces through `python3 scripts/sync_marketplaces.py`

**Interfaces:**
- Consumes: the CLI from Tasks 2–5, and `reference/hosts.md`, which Task 7 generates. `SKILL.md` links it by that path.

Content requirements:
- **`plugin.json`.** Copy `visual-audit`'s shape: `$schema`, name `delegation`, version `0.1.0`, description `Pods of judge, execute and routine agents: route bulk work to cheaper tiers and keep evidence by tree hash.`, author Rick Li, keywords `["delegation", "subagents", "evidence"]`.
- **`SKILL.md` frontmatter.** `name: delegation`. The description says to use it when the repo's `AGENTS.md` points to the delegation skill, or when the user asks to delegate work to execute/routine tiers.
- **`SKILL.md` body.** Define `<skill-dir>` as visual-audit does. Then, in order:
  1. Loading the overlay. If it's absent, say once that base defaults apply. Run `python3 <skill-dir>/scripts/check.py lint` at the start of a session.
  2. Base rules 1–9 from the spec, phrased as instructions.
  3. The procedure, as data-flow steps 3–5 with exact `check.py` commands. Briefs go at `.agents/delegation/briefs/<id>.md`.
  4. The tier-to-host lookup: "read `reference/hosts.md`; on Claude Code never pass `model` or `effort` when starting a tier agent".
  5. Expected judge setting: medium effort, which the skill can't set.
  6. "Pods and relay": the quota zones, and the `pending --json` contract with its exact shape.
  7. Error handling, from the spec's list.
- **`reference/overlay.md`.** The heading table, the parsing rules from Task 2 (including `validator:<name>` references), and the game-decomp example verbatim from the spec.
- **`reference/return-format.md`.** The return format block, the evidence table and the downgrade rule from the spec. Then a brief template with these fields:
  - Goal
  - Inputs
  - May write
  - Must not write
  - Done when / validators
  - Delegation id
  - The absolute `check.py` path and the exact `run` command
  - Return format (quote this file's block)
  - Return fields
  - Return cap
- **Spec edits.** Update Components, `check.py` and Verification for the state directory, `--writes`, the generated `hosts.md` and the Codex route rule. Keep everything else.

- [ ] **Step 1: Write** the files above. Run `python3 scripts/sync_marketplaces.py`.
- [ ] **Step 2: Verify:** `python3 scripts/sync_marketplaces.py --check` prints `Generated metadata is current.`, and `claude plugin validate plugins/delegation` passes.
- [ ] **Step 3: Commit** `feat(delegation): base skill, overlay and return-format references`.

### Task 7: Generate tier definitions from `tiers.json`

**Files:**
- Create: `plugins/delegation/tiers.json`
- Modify: `scripts/sync_marketplaces.py`, `tests/test_sync_marketplaces.py`
- Generated: `plugins/delegation/agents/execute.md`, `plugins/delegation/agents/routine.md`, `plugins/delegation/skills/delegation/reference/hosts.md`, plus Codex definitions if Task 1 chose `definitions`

**Interfaces:**
- Produces, in `sync_marketplaces.py`:
  - `load_tiers(plugin_dir: Path) -> dict | None`: returns `None` when there is no `tiers.json`, and raises `ValueError` on invalid content before any write.
  - `render_tiers(plugin_path: Path, tiers: dict) -> dict[Path, str]`: maps repo-relative paths to file content. `render_outputs` merges it in.

`tiers.json` shape:

```json
{
  "schema": 1,
  "reference": "skills/delegation/reference/hosts.md",
  "routes": {"claude": "definitions", "codex": "<from Task 1>"},
  "tiers": {
    "judge":   {"subagent": false, "role": "plan, rule, review, diagnose",
                "hosts": {"claude": {"model": "claude-opus-5-5", "effort": "medium"},
                          "codex":  {"model": "gpt-6.1-sol", "effort": "medium"}}},
    "execute": {"subagent": true, "role": "...", "description": "...", "instructions": "...",
                "hosts": {"claude": {"model": "claude-sonnet-5-5"},
                          "codex":  {"model": "gpt-6.1-sol", "effort": "low"}}},
    "routine": {"subagent": true, "role": "...", "description": "...", "instructions": "...",
                "hosts": {"claude": {"model": "claude-haiku-5-5"}, "codex": {"model": "gpt-6-luna"}}}
  }
}
```

Validation, each failure a `ValueError` naming the field:
- `schema == 1`;
- `reference` stays under `skills/` inside the plugin;
- `routes.claude == "definitions"` and `routes.codex` is one of `definitions`, `spawn` or `same-model`;
- tier names are kebab-case, and each tier has both hosts with a nonempty `model`;
- `effort` is in `low|medium|high|xhigh|max` for Claude and `minimal|low|medium|high|xhigh` for Codex;
- `subagent` tiers need a nonempty `description` and `instructions`.

Instructions content: about six lines per tier.
- **Both tiers.** Follow the brief. Write only what it permits. Return proposed changes for single-writer resources. Run validators only through the `check.py run` command in the brief, and cite ledger ids as `[checked: <id>]`. Use the brief's return format and cap.
- **`execute`.** Stop and report with evidence when stuck.
- **`routine`.** Report oddities without interpreting them.

Rendering:
- **Claude agent `agents/<tier>.md`.** YAML frontmatter `name: <tier>`, `description: <json.dumps(description)>`, `model: <model>`, and `effort: <effort>` only when set. Then a blank line, `<!-- Generated by scripts/sync_marketplaces.py from tiers.json; do not edit. -->`, a blank line, and the instructions.
- **`hosts.md`.** The same generated comment. Then a table of tier, role, Claude Code (model, effort or "default") and Codex. Then a "Starting a tier" section per host:
  - Claude: Agent tool with `subagent_type` `delegation:<tier>`; never pass `model` or `effort`; the environment overrides.
  - Codex `spawn`: spawn the default subagent with `model` and `reasoning_effort` given explicitly, one bullet per tier.
  - Codex `same-model`: spawn a same-model subagent and put the tier name in the brief; effort stays the default.
  - Codex `definitions`: the agent name `delegation-<tier>`.
- **Orphans.** In a plugin with `tiers.json`, any `agents/*.md` (and any Codex definition file) that isn't generated is drift: `--check` fails and `sync` deletes it.

- [ ] **Step 1: Write the failing tests** in `test_sync_marketplaces.py`, using a fixture plugin with a minimal `tiers.json`:
  - `test_tiers_generate_claude_agents` (frontmatter lines exact; `effort` absent when unset; no `judge.md`);
  - `test_hosts_reference_lists_every_tier_and_route` (each model id is present; the `spawn` route text includes `gpt-6-luna`);
  - `test_hand_edited_agent_fails_check` (an edit to `agents/execute.md` makes `--check` false and leaves the file unchanged);
  - `test_orphan_agent_is_drift_and_removed_by_sync`;
  - `test_invalid_tiers_rejected_before_writes` (a bad effort, a missing model and a `reference` that escapes; nothing written);
  - `test_plugin_without_tiers_unchanged` (existing outputs are identical).
- [ ] **Step 2: Run** `python3 -m unittest tests.test_sync_marketplaces -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `load_tiers` and `render_tiers`, wire them into `render_outputs`/`sync`, and write `plugins/delegation/tiers.json` with `routes.codex` from Task 1.
- [ ] **Step 4: Run** `python3 scripts/sync_marketplaces.py`, then `python3 scripts/sync_marketplaces.py --check` and `python3 -m unittest discover -s tests -v`. Expected: `Generated metadata is current.` and all tests PASS. `claude plugin validate plugins/delegation` passes.
- [ ] **Step 5: Commit** `feat(delegation): generate tier agents and host table from tiers.json`, including the generated files.

### Task 8: Lifecycle verification, live checks and docs

**Files:**
- Modify: `scripts/verify_lifecycle.py`, `tests/test_verify_lifecycle.py`, `README.md`, `docs/verification.md`

**Interfaces:**
- Produces, in `verify_lifecycle.py`:
  - `plugin_agents(plugin_dir: Path) -> list[str]`: sorted stems of `agents/*.md`.
  - `missing_inventory(details: str, skills: list[str], agents: list[str]) -> list[str]`: returns problems such as `missing skill: x` and `missing agent: execute`. Agents match by name appearing on the `Agents (` line of `claude plugin details` output.
- Replace the inline Claude inventory check with `missing_inventory`, and record `agents` in each inspection.

- [ ] **Step 1: Write the failing tests**:
  - `test_missing_inventory_reports_absent_agent`, using a captured `plugin details` text in the shape `Agents (4)  a, b` (as printed by Claude Code 2.1.296);
  - `test_plugin_agents_lists_generated_definitions` against `plugins/delegation`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_verify_lifecycle -v`. Expected: FAIL. **Then implement**, and run again. Expected: PASS.
- [ ] **Step 3: Run the full gate**:

```sh
python3 scripts/sync_marketplaces.py --check
python3 -m unittest discover -s tests -v
uv run --no-project --python 3.10 -m unittest discover -s tests -v
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```

Expected: all pass, and both hosts print `PASS` with four plugins installed, byte-compared and removed.

- [ ] **Step 4: Live Claude check.** Without touching any configuration, run `claude --plugin-dir plugins/delegation -p "<ask it to start delegation:routine to run echo ok and report>"`. If `--plugin-dir` is unsupported, stop and ask Rick for an interactive check instead. Find the subagent transcript under `~/.claude/projects/` and record its `model` field. Record effort only if the transcript shows it; otherwise write "effort not observable; documented behaviour".
- [ ] **Step 5: Docs.**
  - **README:** a `delegation` row and a section covering the `AGENTS.md` pointer line verbatim, the overlay path, `check.py` usage and install/uninstall lines for both hosts.
  - **`docs/verification.md`:** the new versions, four plugins, the `delegation` skill hash, generated agents in the inventory, the Task 8 live check with its labels, and the Python 3.10 run.
  - **Not claimed:** routing quality (that's the pilot's job), GUI or remote checks.
- [ ] **Step 6: Commit** `feat(delegation): verify agent inventory; document delegation 0.1.0`.
