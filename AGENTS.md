# Contributor guidance

- Author shared plugin identity in `plugins/<name>/plugin.json` and marketplace
  identity/order in `catalog.json`. Keep plugin and directory names identical.
- Keep skills and their resources self-contained inside each plugin. Both hosts
  should consume the same content. Add host-specific behavior only with explicit
  compatibility handling and verification.
- Generate host manifests and marketplaces with
  `python3 scripts/sync_marketplaces.py`. Do not edit generated metadata by hand.
  Commit generated output alongside its sources.
- Keep development scripts on Python 3.10+ standard library; consumer installation
  must not require a build or extra dependencies.
- After packaging changes run:

  ```sh
  python3 scripts/sync_marketplaces.py --check
  python3 -m unittest discover -s tests -v
  python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
  ```

- Use the verifier's disposable profiles for lifecycle tests. Do not modify a
  user's normal plugin configuration for automated verification. Record actual
  versions and results in `docs/verification.md`; do not claim GUI, remote, or
  model execution checks unless they were performed.
- Update README commands and documentation when supported packaging or CLI
  behavior changes. Bump versions for released plugin content changes.
