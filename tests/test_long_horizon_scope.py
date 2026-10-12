import json
from long_horizon_support import RepoTest, OVERLAY


class ScopeTests(RepoTest):
    def test_git_pathspec_spaces_symlink_and_exclusion(self):
        self.write('src with spaces/a.py', 'one')
        self.write('src with spaces/ignored.py', 'ignored')
        (self.root / 'src with spaces/link.py').symlink_to('a.py')
        spec = {'validator:unit': {'scope': ['src with spaces/**', ':(exclude)src with spaces/ignored.py']}}
        self.write('.agents/long-horizon.md', '# Long-horizon\n## Evidence\nchecks: ' + json.dumps(spec) + '\n')
        before = self.prepare()
        self.write('src with spaces/ignored.py', 'different excluded')
        self.assertEqual(before['scope'], self.prepare()['scope'])
        (self.root / 'src with spaces/link.py').unlink()
        (self.root / 'src with spaces/link.py').symlink_to('ignored.py')
        self.assertNotEqual(before['scope'], self.prepare()['scope'])

    def test_external_input_changed_fail_timeout_and_extra_output(self):
        import sys
        self.write('.git/info/exclude', 'external.data\n')
        self.write('external.data', 'a' * 64)
        probe = {'command': [sys.executable, '-c', 'from pathlib import Path; print(Path("external.data").read_text())'], 'timeout': 1, 'recover': 'restore bytes'}
        spec = {'validator:unit': {'inputs': ['native']}}
        self.write('.agents/long-horizon.md', '# Long-horizon\n## Evidence\nchecks: ' + json.dumps(spec) + '\ninputs: ' + json.dumps({'native': probe}) + '\n')
        before = self.cli('evidence', 'prepare', 'validator:unit', '--probe-inputs')['snapshot']
        self.write('external.data', 'b' * 64)
        self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS', '--command', 'true', '--exit', '0', '--probe-inputs', '--log', 'regenerate:external fixture check', code=1)
        for command in [[sys.executable, '-c', 'raise SystemExit(1)'], [sys.executable, '-c', 'import time; time.sleep(2)'], [sys.executable, '-c', 'print("a"*64); print("extra")']]:
            probe['command'] = command
            self.write('.agents/long-horizon.md', '# Long-horizon\n## Evidence\nchecks: ' + json.dumps(spec) + '\ninputs: ' + json.dumps({'native': probe}) + '\n')
            self.cli('evidence', 'prepare', 'validator:unit', '--probe-inputs', code=2)

    def test_incomparable_conflicting_runs_need_review(self):
        self.git('checkout', '-b', 'pass-branch')
        passed = self.record(self.prepare())
        self.carry(passed)
        self.git('checkout', 'main')
        self.git('checkout', '-b', 'fail-branch')
        failed = self.record(self.prepare(), 'FAIL')
        self.carry(failed)
        self.git('merge', '--no-edit', 'pass-branch')
        result = self.cli('evidence', 'find', code=1)
        self.assertEqual(result['checks'][0]['status'], 'conflict')
        self.carry(self.record(self.prepare()))
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'fresh')

    def test_scope_is_the_same_for_crlf_and_lf_checkouts(self):
        # Windows checkouts with core.autocrlf get CRLF files from the same LF blobs.
        self.write('tiny.py', 'def tiny():\n    return 2\n')
        self.commit('LF blob')
        lf = self.prepare()
        self.git('config', 'core.autocrlf', 'true')
        (self.root / 'tiny.py').unlink()
        self.git('checkout', '--', 'tiny.py')
        self.assertIn(b'\r\n', (self.root / 'tiny.py').read_bytes())
        self.assertEqual(self.prepare()['scope'], lf['scope'])
