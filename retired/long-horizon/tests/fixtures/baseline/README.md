These goldens are the output of long-horizon 0.5.2 for a repository whose overlay has no `## Lanes` section; `tests/test_long_horizon_baseline.py` compares the current plugin against them byte for byte after normalizing run-specific values.
Regenerate them with `python3 tests/test_long_horizon_baseline.py --regenerate <plugins-root>`, where `<plugins-root>` is a checkout containing `plugins/long-horizon` (default: this checkout).
Regenerating from a newer version is only allowed for an intentional change to lanes-free output.
