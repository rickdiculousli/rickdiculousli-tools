"""Lanes-free delegation output must stay byte-identical to the 0.10.1 baseline.

A repository whose overlay has no `## Lanes`, `## Deps` or `## Rules` section and no `provider:` under
`## Locks` gets exactly the output the plugin produced before lanes existed, apart from the plugin version
inside the `version-mismatch` finding. The goldens under tests/fixtures/delegation/baseline come from
delegation 0.10.1.

Regenerate (intentional output changes only):
    python3 tests/test_delegation_baseline.py --regenerate <plugins-root>
where <plugins-root> is a checkout containing plugins/delegation (default: this checkout).
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

tempfile.tempdir = os.path.realpath(tempfile.gettempdir())
ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests/fixtures/delegation/baseline'
CHECK = 'plugins/delegation/skills/delegation/scripts/check.py'
FIXED_DATE = '2026-10-13T00:00:00Z'

OVERLAY = '''# Delegation overlay: fixture
## Validators
- unit: python3 -c "print(1)" [cheap] [paths=crates/core/**]
- build: python3 -c "print(2)" [timeout=60] [lock=cargo]
## Locks
- cargo: slots=2, wait=10
## Tier hints
- execute: porting
## Single writer
- docs/table.md
## Findings
- docs/findings.md
## Parallel limit
2
## Return fields
- files read
'''
FILES = {
    '.agents/delegation.md': OVERLAY,
    'AGENTS.md': "Delegation: follow the delegation skill; this repo's overlay is .agents/delegation.md.\n",
    'CLAUDE.md': '@AGENTS.md\n',
    'crates/core/test_core.py': 'def test_ok():\n    pass\n',
    'crates/ui/lib.py': 'x = 1\n',
}
BRIEF = ('# Brief\nSettled: none\nGoal: read a file\nInputs: crates/core\nMay write: nothing\n'
         'Must not write: anything\nDone when: validator unit passes\n')
BEFORE = [['lint'], ['lint', '--json'], ['suggest'], ['suggest', '--json'], ['kinds'], ['paths', '--json'],
          ['pending'], ['pending', '--json'], ['locks'], ['locks', '--json'], ['patterns'],
          ['patterns', '--json'], ['tree']]
AFTER = [['brief', '--delegation', 'd1'], ['pending', '--json'], ['run', 'unit', '--delegation', 'd1'],
         ['query', '--delegation', 'd1', '--json'], ['close', '--delegation', 'd1', '--outcome', 'done'],
         ['kinds', '--json'], ['patterns', '--json']]
OPEN = ['open', '--delegation', 'd1', '--tier', 'routine', '--kind', 'read-files', '--new-kind', 'read files']


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
    # One dirty file under the paths-scoped unit.
    (repo / 'crates/core/lib.py').write_text('y = 2\n', encoding='utf-8')


def slug(args):
    return re.sub(r'[^A-Za-z0-9_-]+', '_', '_'.join(a.lstrip('-') for a in args))


def normalize(text, base, plugin_root):
    """Replace only the bytes that differ between runs or checkouts; everything else stays verbatim."""
    # The disposable temp base directory.
    text = text.replace(str(base), '<BASE>')
    # The checkout whose plugin was run (it appears in the task line `open` and `brief` print).
    text = text.replace(str(plugin_root), '<PLUGIN>')
    # 64-hex repository and worktree keys in XDG paths (preceded by a slash, so content digests stay).
    text = re.sub(r'(?<=/)[0-9a-f]{64}(?=[/"\s]|$)', '<KEY>', text)
    # The same keys as bare JSON values.
    text = re.sub(r'("(?:repository_key|worktree_key)": )"[0-9a-f]{64}"', r'\1"<KEY>"', text)
    # ISO-8601 UTC timestamps.
    text = re.sub(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z', '<TIME>', text)
    # Measured durations.
    text = re.sub(r'("duration_s": )[0-9.eE+-]+', r'\1<DUR>', text)
    # Host platform, machine and node names.
    text = re.sub(r'("(?:platform|machine|node)": )"[^"]*"', r'\1"<HOST>"', text)
    # The plugin version inside the version-mismatch message and version.installed.
    text = re.sub(r'(delegation plugin is )\d+\.\d+\.\d+', r'\1<VERSION>', text)
    text = re.sub(r'("installed": )"\d+\.\d+\.\d+"', r'\1"<VERSION>"', text)
    return text


def capture(plugin_root):
    """Run every command against a fresh fixture; return {golden file name: normalized text}."""
    plugin_root = Path(plugin_root).resolve()
    script = plugin_root / CHECK
    with tempfile.TemporaryDirectory(prefix='del-baseline-') as name:
        base = Path(os.path.realpath(name))
        env = environment(base)
        repo = base / 'repo'
        build(repo, env)
        results = {}

        def run(args, label, name=None):
            done = subprocess.run([sys.executable, str(script), '--root', str(repo), *args], env=env,
                                  capture_output=True, text=True, timeout=60)
            results[f'{label:02d}_{slug(name or args)}.txt'] = normalize(done.stdout, base, plugin_root) + f'exit={done.returncode}\n'
            return done

        count = 0
        for args in BEFORE:
            count += 1
            run(args, count)
        paths = subprocess.run([sys.executable, str(script), '--root', str(repo), 'paths', '--json'], env=env,
                               capture_output=True, text=True, timeout=60)
        brief_dir = Path(json.loads(paths.stdout)['brief_directory'])
        brief_dir.mkdir(parents=True, exist_ok=True)
        brief = brief_dir / 'd1.md'
        brief.write_text(BRIEF, encoding='utf-8')
        count += 1
        run([*OPEN, '--brief', str(brief)], count, OPEN)
        for args in AFTER:
            count += 1
            run(args, count)
        return results


class BaselineTests(unittest.TestCase):
    maxDiff = None

    def test_output_matches_the_0_10_1_baseline(self):
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
