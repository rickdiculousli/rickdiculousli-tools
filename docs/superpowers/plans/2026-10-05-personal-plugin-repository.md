# Personal Plugin Repository Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a reusable personal plugin repository with verified marketplace discovery, installation, and uninstallation in Claude Code and Codex.

**Architecture:** Store portable metadata and skills inside self-contained plugin folders. Generate host manifests and marketplaces from one catalog. Verify the real native CLI lifecycle with isolated temporary configuration profiles.

**Tech Stack:** Python standard library, JSON, Markdown, Git, installed Claude Code and Codex CLIs.

**Spec:** [Approved design](../specs/2026-10-05-personal-plugin-repository-design.md)

## Global Constraints

- Marketplace name: `rickdiculousli-plugins`; owner: `Rick Li`.
- Stub names: `hello-world` and `repository-info`; versions: `0.1.0`.
- Shared skill paths: `skills/hello/SKILL.md` and `skills/about/SKILL.md` within their respective plugins.
- Python standard library only; no package installation or build requirement for consumers.
- Generated compatibility metadata is committed; plugin content is authored once.
- No symlinks, hooks, external services, credentials, or MCP servers in the stubs.
- Use supported temporary configuration profiles without overwriting HOME or copying credentials.
- A missing CLI, unsupported isolation, or failed lifecycle assertion fails verification.
- Verify CLI behavior; do not claim model-driven execution, GUI behavior, or remote deployment was tested.

## Review Focus

- Catalog paths that escape the repository must fail before any generated file changes.
- Duplicate names or directory/manifest name mismatches must fail before generation.
- Check mode must detect drift without changing files.
- Successful subprocess exits with missing expected lifecycle state must fail assertions.
- Cleanup failures must be reported without replacing the original lifecycle failure.

## Task 1: Portable plugins and generated host metadata

**Files:** Create `catalog.json`, `.gitignore`, `plugins/hello-world/plugin.json`, `plugins/hello-world/skills/hello/SKILL.md`, `plugins/repository-info/plugin.json`, `plugins/repository-info/skills/about/SKILL.md`, `scripts/sync_marketplaces.py`, and `tests/test_sync_marketplaces.py`. Generate the two marketplace files and four compatibility manifests defined by the spec.

**Interfaces:**
- `load_catalog(root: Path) -> tuple[dict, list[tuple[Path, dict]]]` validates catalog and plugin metadata before writes.
- `render_outputs(root: Path) -> dict[Path, str]` returns deterministic generated JSON file contents keyed by destination paths.
- `sync(root: Path, check: bool = False) -> bool` writes output or checks it without mutation; returns whether output agrees after the operation.
- CLI: `python3 scripts/sync_marketplaces.py [--check] [--root PATH]`; nonzero exit on invalid input or check drift.

- [x] **Step 1:** Read the approved spec and applicable skill instructions for implementation, isolation, TDD, and skill authoring. Use the clean initial repository checkout unless the worktree skill identifies a need for a separate workspace.
- [x] **Step 2:** Create standard-library tests using a temporary repository fixture. Assert that duplicate catalog entries, escaping paths, and mismatched directory/manifest names raise errors and leave generated files absent. Assert that a modified generated file makes `sync(root, check=True)` return false without changing its bytes, and regeneration restores agreement.
- [x] **Step 3:** Run `python3 -m unittest discover -s tests -p 'test_sync_marketplaces.py' -v`; confirm failure because the generator is absent.
- [x] **Step 4:** Author the catalog and root portable manifests with the spec's exact identities. Author concise explicitly scoped stub skills. Implement the generator interfaces above using `json`, `pathlib`, and `argparse`. Generate Claude marketplace entries with string sources and Codex entries with local source objects, following official current formats. Generate minimal host manifests from portable metadata with skill discovery paths as required by each host. Do not copy portable-only schema keys into host manifests.
- [x] **Step 5:** Run the generator, its check mode, and the unit tests. Run `claude plugin validate .` and validation against both plugin folders, correcting actual compatibility findings before proceeding. Validate the skill frontmatter with the available skill-creator validator.
- [x] **Step 6:** Commit source plugins, generator, generated manifests, and tests with `feat: add portable plugins and generated marketplaces`.

## Task 2: Real marketplace lifecycle verification

**Files:** Create `scripts/verify_lifecycle.py`, `tests/test_verify_lifecycle.py`, and `docs/verification.md`.

**Interfaces:**
- Consumes `load_catalog(root)` from Task 1 to obtain exact expected plugin identities.
- `run_command(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]` captures stdout, stderr, exit status, and fails with useful diagnostics on nonzero exit; apply a bounded command timeout.
- `verify_host(host: str, root: Path, profile: Path) -> dict` runs and asserts the host lifecycle, returning version and stage evidence.
- CLI: `python3 scripts/verify_lifecycle.py [--report PATH]`; verifies both hosts and exits nonzero on any failure. With `--report`, save structured evidence including failures and cleanup outcomes.

- [x] **Step 1:** Inspect current native command help and documented profile environment overrides. Identify the isolated directories supported by each CLI and use a temporary working directory outside the repository for lifecycle commands. Assert generated state is under the intended profiles before installing plugins. Never mutate the user's normal installed-plugin state.
- [x] **Step 2:** Write tests with mocked subprocess responses that return success but omit an expected marketplace or installed plugin. Assert verification fails with the missing identity. Inject an install failure and a cleanup failure; assert both diagnostics survive. Test that an unsupported host or missing executable is a failure rather than a skip.
- [x] **Step 3:** Run `python3 -m unittest discover -s tests -p 'test_verify_lifecycle.py' -v`; confirm failure because the verifier is absent.
- [x] **Step 4:** Implement sequential native lifecycle commands with structured state assertions wherever available. Codex currently exposes `plugin marketplace add/list/remove`, `plugin list --available --json`, `plugin add --json`, and `plugin remove --json`; Claude exposes `plugin marketplace add/list/remove`, `plugin list --available --json`, `plugin install`, `plugin details`, and `plugin uninstall`. Inspect actual output before fixing parsers. Check both plugins after install, check skill inventory or installed files, uninstall each, assert neither is installed, remove the marketplace, and assert registration is gone. Use `finally` cleanup and report cleanup errors separately from primary failures.
- [x] **Step 5:** Run the verifier tests, then `python3 scripts/verify_lifecycle.py --report /tmp/rickdiculousli-plugin-verification.json`. Inspect the evidence for both CLI versions and every stage of the spec. Correct real failures and rerun affected checks until both hosts pass or a demonstrated external blocker is reported.
- [x] **Step 6:** Write `docs/verification.md` from observed evidence, including tool versions, verified stages, isolation method, and scope limits. Commit with `test: verify both native plugin lifecycles`.

## Task 3: Authoring guidance and final acceptance

**Files:** Create `README.md`, `AGENTS.md`, and `CLAUDE.md`; update verification documentation if final checks discover relevant changes.

**Interfaces:** Documentation uses Task 1's generator CLI and Task 2's verifier CLI. AGENTS.md is canonical contributor guidance; CLAUDE.md imports or refers to it using Claude's supported mechanism.

- [x] **Step 1:** Write the README with the layout, prerequisites, source/generated distinction, add-plugin workflow, and concrete install/uninstall commands for both hosts. Explain registering the local repository path and Git repository installation when a remote exists, without inventing a remote URL or claiming deployment.
- [x] **Step 2:** Write shared contributor guidance requiring regeneration and lifecycle checks when packaging changes. Keep CLAUDE.md as a reference to AGENTS.md.
- [x] **Step 3:** Run `python3 scripts/sync_marketplaces.py --check`, `python3 -m unittest discover -s tests -v`, `python3 scripts/verify_lifecycle.py --report /tmp/rickdiculousli-plugin-verification-final.json`, and `git diff --check`. Inspect results before claiming completion. Confirm no test state or credentials are tracked.
- [x] **Step 4:** Review the full change against the approved spec and fix any meaningful gaps. Use applicable review and completion skills; independent agent review is permitted only when the selected execution workflow requires it. Commit documentation with `docs: explain portable plugin authoring and installation`.
- [x] **Step 5:** Report verified lifecycle results with links to the README and verification record. State any real limitations. Do not create or publish a remote repository or PR unless subsequently requested.
