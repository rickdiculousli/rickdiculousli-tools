import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

# macOS's /var is a symlink to /private/var, and the tools report resolved paths, so give every
# test resolved temporary directories rather than resolving them test by test.
tempfile.tempdir = os.path.realpath(tempfile.gettempdir())

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/long-horizon/skills/resume/scripts/lh.py'
sys.path.insert(0, str(SCRIPT.parent))

OVERLAY = '''# Long-horizon
## Goals and ownership
path: "docs/goals.md"
## Evidence
checks: {"validator:unit": {"domain": "unit-v1"}, "observation:review": {"domain": "review-v1"}}
'''
GOALS = '''# Goal: Tiny project — current
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
'''
HANDOFF = '# Handoff\n## Blockers\n## Pending decisions\n'


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='long horizon ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo with spaces'
        self.root.mkdir()
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.base / 'state'), XDG_CACHE_HOME=str(self.base / 'cache'))
        self.patch = patch.dict(os.environ, self.env)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Disposable Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('.agents/long-horizon.md', OVERLAY)
        self.write('docs/goals.md', GOALS)
        self.write('docs/handoff.md', HANDOFF)
        self.write('AGENTS.md', 'Long horizon: use long-horizon:resume and long-horizon:checkpoint; overlay .agents/long-horizon.md.\n')
        self.write('CLAUDE.md', '@AGENTS.md\n')
        self.write('tiny.py', 'def tiny():\n    return 1\n')
        self.commit('Initial fixture')

    def git(self, *args, root=None, check=True):
        result = subprocess.run(['git', '-C', str(root or self.root), *args], capture_output=True, text=True, env=self.env)
        if check and result.returncode:
            self.fail(result.stderr)
        return result.stdout.strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def cli(self, *args, code=0, root=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, '--root', str(root or self.root), '--json'],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def write_readiness(self, text):
        # Publish the cache identity the way a startup helper does, then the report.
        output = self.cli('paths')
        identity = Path(output['cache_identity_path'])
        identity.parent.mkdir(parents=True, exist_ok=True)
        identity.write_text(json.dumps(output['cache_identity']))
        path = Path(output['readiness_path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def prepare(self, attempt=None, check='validator:unit'):
        args = ['evidence', 'prepare', check]
        if attempt:
            args += ['--attempt', attempt]
        return self.cli(*args)['snapshot']

    def record(self, before, outcome='PASS', check='validator:unit'):
        return self.cli('evidence', 'record', check, '--snapshot', before['id'], '--outcome', outcome,
                        '--command', 'python -m unittest', '--exit', '0' if outcome == 'PASS' else '1',
                        '--log', 'regenerate:python -m unittest')

    def carry(self, output):
        for path, content in output['proposed_files'].items():
            self.write(path, content)
        return self.commit('Observed fixture check\n\n' + output['trailer'])
