"""Lanes-free long-horizon output must stay byte-identical to the 0.5.2 baseline.

A repository whose overlay has no `## Lanes` section gets exactly the output the plugin produced before
lanes existed, apart from the plugin version inside the `version-mismatch` finding. The goldens under
tests/fixtures/long_horizon/baseline come from long-horizon 0.5.2.

Regenerate (intentional output changes only):
    python3 tests/test_long_horizon_baseline.py --regenerate <plugins-root>
where <plugins-root> is a checkout containing plugins/long-horizon (default: this checkout).
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

tempfile.tempdir = os.path.realpath(tempfile.gettempdir())
ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests/fixtures/long_horizon/baseline'
LH = 'plugins/long-horizon/skills/resume/scripts/lh.py'
FIXED_DATE = '2026-10-13T00:00:00Z'

FILES = {
    '.agents/long-horizon.md': '''# Long-horizon
## Goals and ownership
path: "docs/goals.md"
## Evidence
checks: {"validator:unit": {"domain": "unit-v1"}, "observation:review": {"domain": "review-v1"}}
''',
    'docs/goals.md': '''# Goal: Tiny project — current
ID: tiny
Done when: validator:unit
## 1. Build — current
Done when: validator:unit
- [ ] [1.1] Implement tiny function. (any)
- [ ] [1.2] Review tiny function. (any)
## 2. Integrate
Done when: observation:review
- [ ] [2.1] Exercise the whole call. (any)
## Parked
- Unrelated idea
''',
    'docs/handoff.md': '# Handoff\n## Blockers\n## Pending decisions\n',
    'AGENTS.md': 'Long horizon: use long-horizon:resume and long-horizon:checkpoint; overlay .agents/long-horizon.md.\n',
    'CLAUDE.md': '@AGENTS.md\n',
    'tiny.py': 'def tiny():\n    return 1\n',
}
COMMANDS = [
    ['status', '--json'], ['status'], ['status', '--brief'], ['lint', '--json'], ['lint'],
    ['lint', '--fix', '--json'], ['gate', '--json'], ['closure', 'verify', '--json'],
]


def environment(base):
    env = dict(os.environ, XDG_STATE_HOME=str(base / 'state'), XDG_CACHE_HOME=str(base / 'cache'),
               GIT_AUTHOR_NAME='Baseline Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_NAME='Baseline Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid',
               GIT_AUTHOR_DATE=FIXED_DATE, GIT_COMMITTER_DATE=FIXED_DATE)
    env.pop('XDG_CONFIG_HOME', None)
    return env


def build(repo, env):
    repo.mkdir(parents=True)
    for name, text in FILES.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    for args in (['init', '-q', '-b', 'main'], ['config', 'commit.gpgsign', 'false'], ['add', '.'],
                 ['commit', '-q', '-m', 'Initial fixture']):
        subprocess.run(['git', '-C', str(repo), *args], env=env, check=True, capture_output=True)


def slug(args):
    return '_'.join(a.lstrip('-') for a in args)


def normalize(text, base, plugin_root):
    """Replace only the bytes that differ between runs or checkouts; everything else stays verbatim."""
    # The disposable temp base directory.
    text = text.replace(str(base), '<BASE>')
    # The checkout whose plugin was run (it appears in recovery commands).
    text = text.replace(str(plugin_root), '<PLUGIN>')
    # 64-hex repository and worktree keys in XDG paths (preceded by a slash, so content digests stay).
    text = re.sub(r'(?<=/)[0-9a-f]{64}(?=[/"\s]|$)', '<KEY>', text)
    # ISO-8601 UTC timestamps.
    text = re.sub(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z', '<TIME>', text)
    # Measured durations.
    text = re.sub(r'("duration_s": )[0-9.eE+-]+', r'\1<DUR>', text)
    # Host platform, machine and node names.
    text = re.sub(r'("(?:platform|machine|node)": )"[^"]*"', r'\1"<HOST>"', text)
    # The plugin version inside the version-mismatch message and version.installed.
    text = re.sub(r'(long-horizon plugin is )\d+\.\d+\.\d+', r'\1<VERSION>', text)
    text = re.sub(r'("installed": )"\d+\.\d+\.\d+"', r'\1"<VERSION>"', text)
    return text


def capture(plugin_root):
    """Run every command against a fresh fixture; return {golden file name: normalized text}."""
    plugin_root = Path(plugin_root).resolve()
    script = plugin_root / LH
    with tempfile.TemporaryDirectory(prefix='lh-baseline-') as name:
        base = Path(os.path.realpath(name))
        env = environment(base)
        repo = base / 'repo'
        build(repo, env)
        results = {}
        for args in COMMANDS:
            done = subprocess.run([sys.executable, str(script), *args, '--root', str(repo)], env=env,
                                  capture_output=True, text=True, timeout=60)
            text = normalize(done.stdout, base, plugin_root) + f'exit={done.returncode}\n'
            results[slug(args) + '.txt'] = text
        return results


class BaselineTests(unittest.TestCase):
    def test_output_matches_the_0_5_2_baseline(self):
        results = capture(ROOT)
        self.assertEqual(set(results), {p.name for p in GOLDEN.glob('*.txt')})
        for name, text in results.items():
            with self.subTest(command=name):
                self.assertEqual(text, (GOLDEN / name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--regenerate':
        source = sys.argv[2] if len(sys.argv) > 2 else ROOT
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for old in GOLDEN.glob('*.txt'):
            old.unlink()
        for name, text in capture(source).items():
            (GOLDEN / name).write_text(text, encoding='utf-8')
    else:
        unittest.main()
