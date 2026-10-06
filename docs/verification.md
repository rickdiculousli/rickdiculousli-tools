# Native lifecycle verification

Verified on October 5, 2026 (America/Los_Angeles; report timestamp
2026-10-06T03:59:31Z), using the real locally installed CLIs, with a fresh temporary
configuration profile for each host.

| Check | Codex 0.160.1 | Claude Code 2.1.290 |
| --- | --- | --- |
| Generated metadata matches portable sources | Passed | Passed |
| Native manifest and skill validation | Discovery/install accepted manifests | `claude plugin validate` passed |
| Empty isolated profile confirmed | Passed | Passed |
| Repository marketplace registered and listed | Passed | Passed |
| All three plugins discoverable | Passed | Passed |
| All three plugins installed and enabled | Passed | Passed |
| Installed portable manifests match source | Passed | Passed |
| Every committed plugin file matches its installed copy byte for byte; no extra files | Passed | Passed |
| Native skill component inventory | Installed files inspected | `plugin details` lists `hello`, `about`, and `audit-report` |
| All three plugins uninstalled; absent from installed list | Passed | Passed |
| Marketplace removed; absent from marketplace list | Passed | Passed |

The marketplace is `rickdiculousli-plugins`. The tested plugins are
`visual-audit`, `hello-world`, and `repository-info` (all `@rickdiculousli-plugins`,
version `0.1.0`). File comparison covers every file tracked by Git in each plugin
directory except generated host manifests, so `visual-audit`'s renderer scripts,
templates, and references are included. Both hosts installed identical skill content:

| Skill | SHA-256 |
| --- | --- |
| `audit-report` | `d014925c6443c961b72529866b868ad1ece1146b62b97322a2076027a193117b` |
| `hello` | `bf6ab583d5cd7ee791d8f3f551fc04c120b180bcd6e99effc4e52f3f3d6bd07d` |
| `about` | `764ab249ba09f27a645b7fe4b60ab60e33b7b569bc189d158f7e139a46ec1434` |

## Visual audit renderer

The renderer's unit tests passed on Python 3.14.7 and 3.10.22 (via
`uv run --no-project --python 3.10`). Example, 300-step, and all-pass reports were
rendered and inspected in the T3 Code preview browser at 1280 px and 390 px wide, in light
and dark schemes, including filter buttons and anchor navigation into collapsed
groups. Behaviour with JavaScript disabled was checked structurally (filters exist only
when the script runs; anchors and disclosure are native HTML), not by disabling
JavaScript in a browser. The Impeccable design detector's contrast findings were
false positives from measuring dark-scheme colours on the light background; contrast
was computed per scheme instead.

## Reproduce

From the repository root, with Python 3.10+ and both CLIs on PATH:

```sh
python3 scripts/sync_marketplaces.py --check
python3 -m unittest discover -s tests -v
python3 scripts/verify_lifecycle.py --report /tmp/plugin-verification.json
```

The verifier exits nonzero on failure. Its optional JSON report records versions,
each command and exit code, native output, installation paths, skill hashes,
passed stages, and any primary or cleanup errors. Reports include absolute local
paths and are intended as local test evidence.

## Isolation and scope

The verifier creates new temporary directories, sets `CODEX_HOME` and
`CODEX_SQLITE_HOME` for Codex and `CLAUDE_CONFIG_DIR` for Claude Code, and runs
commands from a temporary working directory. It confirms empty state and checks
that marketplace metadata and installed content land in the temporary profile.
No credentials are copied. Test marketplaces and plugins are removed;
temporary profiles are deleted afterward. No permanent user installation is
requested by the verifier.

Uninstallation is checked using native installed-plugin lists. Available catalog
entries or host-retained cache directories do not count as installed plugins.

This verifies local CLI marketplaces, installation, skill packaging, and removal.
It does not claim graphical marketplace testing, model-driven execution of any
skill (including an agent producing a real audit report), or Git remote deployment. The repository had no configured remote
during verification. The external skill-creator validator needed unavailable
PyYAML; native Claude skill validation and installed-content checks were used
instead, without adding a dependency.

## Format references

- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)
- [Codex profile environment variables](https://developers.openai.com/codex/environment-variables)
- [Claude Code marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code profile environment variables](https://code.claude.com/docs/en/env-vars)
