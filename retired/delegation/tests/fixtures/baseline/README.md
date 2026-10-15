These goldens are the output of delegation 0.10.1 for a repository whose overlay has no `## Lanes`, `## Deps` or `## Rules` section and no `provider:` under `## Locks`; `tests/test_delegation_baseline.py` compares the current plugin against them byte for byte after normalizing run-specific values.
Regenerate them with `python3 tests/test_delegation_baseline.py --regenerate <plugins-root>`, where `<plugins-root>` is a checkout containing `plugins/delegation` (default: this checkout).
Regenerating from a newer version is only allowed for an intentional change to lanes-free output.
