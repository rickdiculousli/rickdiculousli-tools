# Contributor guidance

- Author shared plugin identity in `plugins/<name>/plugin.json` and marketplace
  identity/order in `catalog.json`. Keep plugin and directory names identical.
- Keep skills and their resources self-contained inside each plugin. Both hosts
  should consume the same content. Add host-specific behavior only with explicit
  compatibility handling and verification.
- Generate host manifests and marketplaces with
  `python3 scripts/sync_marketplaces.py`. Do not edit generated metadata by hand.
  Commit generated output alongside its sources.
- Anonymize other client and consuming repositories in all text: code, comments,
  docs, tests, fixtures, commit messages and verification notes. Do not name them,
  their paths or worktrees, or describe what they are for; say "a consuming
  repository" or use a generic, invented example instead.
- Keep development scripts on Python 3.10+ standard library; consumer installation
  must not require a build or extra dependencies.
- Plugin scripts may be PEP 723 scripts run with `uv run --script`; `uv` is
  expected on hosts using those scripts. Callers accept a configurable script path
  to an installed skill or any checkout's
  `plugins/<plugin>/skills/<skill>/scripts/<script>`; never hardcode a clone location
  or versioned plugin cache. Quote paths containing spaces.
- Use a consistent XDG layout for all plugin-owned runtime files:
  persistent operational state and locks under
  `${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/<plugin>/`,
  regenerable caches and temporary hashing/build files under
  `${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/<plugin>/`.
  For delegation and long-horizon on Windows, honor explicit absolute XDG
  overrides; otherwise use `%LOCALAPPDATA%/rickdiculousli-tools/<plugin>/state/`
  and `%LOCALAPPDATA%/rickdiculousli-tools/<plugin>/cache/`. If LOCALAPPDATA is
  missing, empty or relative, resolve `Path.home() / "AppData" / "Local"`.
  Treat empty or relative XDG values as unset and use the platform defaults.
  Resolve home paths in Python, not through shell expansion.
  Do not put runtime state or locks in consuming worktrees, installed plugin
  directories, Git directories or hardcoded `/tmp` paths. Keep durable project
  knowledge and acceptance in the consuming repository's tracked documents.
- Scope repository state by the SHA-256 of the canonical Git common-directory
  path and worktree state by the SHA-256 of the canonical worktree path; normalize
  path case where the platform requires it. Use `<repo-key>/worktrees/<worktree-key>/`
  for worktree payloads and `<repo-key>/locks/` for repository-wide resource locks.
  Store identity metadata so recreated paths cannot silently inherit old state.
  Each plugin is self-contained; matching conventions do not imply a runtime
  dependency on another plugin. All processes coordinating locks must use the
  same XDG state root; fail with an actionable diagnostic if it is not writable,
  rather than silently creating another lock domain elsewhere.
- Use standard-library locks on POSIX (`fcntl.flock`) and Windows
  (`msvcrt.locking`). Each plugin has one fixed root `state.lock` for short
  bookkeeping/cleanup transactions; never unlink or replace that lock file.
  Long-running resource locks are separate and shared across a repository's
  worktrees; protect their lifecycle so cleanup cannot race holders or waiters.
- Worktree-scoped state must support explicit cleanup and opportunistic weekly
  cleanup during normal use, without a background process. Confirm deleted
  worktrees and allow a seven-day recovery window before deleting their payloads;
  retain existing worktrees' unfinished work and unknown/inaccessible identities.
  Unreferenced snapshots/drafts expire after 30 days. Cleanup never removes
  durable Git evidence, live locks or active resource holders/waiters. Plugin-wide
  histories/caches need their own documented retention rules, not worktree expiry.
  Plugins support only the current layout: each plugin's `migrate` skill lints
  a consuming repository against it and tags the overlay's `## Version`; see
  [the migrate skills design](docs/superpowers/specs/2026-10-12-migrate-skills-design.md).
- After packaging changes run:

  ```sh
  python3 scripts/sync_marketplaces.py --check
  python3 scripts/run_tests.py   # parallel; python3 -m unittest discover -s tests -v runs it serially
  python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
  ```

- Use the verifier's disposable profiles for lifecycle tests. Do not modify a
  user's normal plugin configuration for automated verification. Record actual
  versions and results in `docs/verification.md`; do not claim GUI, remote, or
  model execution checks unless they were performed.
- Update README commands and documentation when supported packaging or CLI
  behavior changes. Bump versions for released plugin content changes.
- A modification is complete only after it is verified, merged to `main` and
  pushed to `origin`. This is standing authorization: run the checks above that
  apply, commit, merge any work branch or worktree into `main`, and push `main`
  without asking again. If a check fails, the merge conflicts or the push is
  rejected, stop and report; never force-push, skip checks or rewrite `main`.
