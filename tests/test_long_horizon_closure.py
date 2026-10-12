import hashlib
import json
from long_horizon_support import RepoTest, OVERLAY
from long_horizon.model import digest


class ClosureTests(RepoTest):
    def configure(self, steps=('commit', 'merge', 'push', 'sync')):
        policy = OVERLAY + '\n## Integration\nsteps: ' + json.dumps(list(steps)) + '\ntarget: "main"\nremote: "origin"\nsync: "fixture sync"\nauthorization: "Fixture authorizes local batch closure."\n'
        self.write('.agents/long-horizon.md', policy)
        self.commit('Fixture integration authorization')

    def batch(self):
        base = self.git('rev-parse', 'HEAD')
        self.write('tiny.py', 'def tiny():\n    return 2\n')
        paths = [{'path': 'tiny.py', 'digest': hashlib.sha256((self.root / 'tiny.py').read_bytes()).hexdigest()}]
        manifest = {'version': 1, 'base': base, 'paths': paths, 'evidence_ids': []}
        path = self.base / 'manifest.json'
        path.write_text(json.dumps(manifest))
        batch = digest({'evidence_ids': [], 'paths': paths})
        commit = self.commit('Owned batch')
        return batch, commit, path

    def test_commit_merge_push_sync_are_independent_and_retry(self):
        self.configure()
        remote = self.base / 'remote.git'
        self.git('init', '--bare', str(remote))
        self.git('remote', 'add', 'origin', str(remote))
        self.git('checkout', '-b', 'batch')
        batch, commit, manifest = self.batch()
        self.cli('closure', 'record', '--batch', batch, '--step', 'commit', '--outcome', 'success', '--commit', commit, '--manifest', str(manifest))
        self.assertEqual(self.cli('closure', 'verify', code=1)['next'], 'merge')
        target = self.base / 'target'
        self.git('worktree', 'add', str(target), 'main')
        self.git('merge', '--ff-only', 'batch', root=target)
        self.cli('closure', 'record', '--batch', batch, '--step', 'merge', '--outcome', 'success', '--commit', commit)
        self.assertEqual(self.cli('closure', 'verify', code=1)['next'], 'push')
        self.git('push', 'origin', 'main')
        self.cli('closure', 'record', '--batch', batch, '--step', 'push', '--outcome', 'success', '--commit', commit, '--observation', 'Local push exited 0')
        self.assertEqual(self.cli('closure', 'verify', code=1)['next'], 'sync')
        self.cli('closure', 'record', '--batch', batch, '--step', 'sync', '--outcome', 'failed', '--observation', 'Fixture sync failed')
        self.cli('closure', 'verify', code=1)
        self.cli('closure', 'record', '--batch', batch, '--step', 'sync', '--outcome', 'success', '--observation', 'Fixture sync succeeded')
        result = self.cli('closure', 'verify')
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(result['steps'][2]['observation']['oid'], commit)
        self.cli('closure', 'record', '--batch', batch, '--step', 'sync', '--outcome', 'success', '--observation', 'Fixture sync succeeded')
        self.cli('closure', 'record', '--batch', 'different', '--step', 'sync', '--outcome', 'success', '--observation', 'different', code=2)
        path = self.cli('status')['state_directory'] + '/closure.json'
        self.assertEqual(self.cli('closure', 'verify', '--state', path)['state'], 'complete')
        self.git('update-ref', '-d', 'refs/remotes/origin/main')
        self.assertEqual(self.cli('closure', 'verify', code=1)['next'], 'push')

    def test_rejected_push_remains_failed(self):
        self.configure(('commit', 'merge', 'push'))
        remote = self.base / 'remote.git'
        self.git('init', '--bare', str(remote))
        self.git('remote', 'add', 'origin', str(remote))
        hook = remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        batch, commit, manifest = self.batch()
        self.cli('closure', 'record', '--batch', batch, '--step', 'commit', '--outcome', 'success', '--commit', commit, '--manifest', str(manifest))
        self.cli('closure', 'record', '--batch', batch, '--step', 'merge', '--outcome', 'success', '--commit', commit)
        self.git('push', 'origin', 'main', check=False)
        self.cli('closure', 'record', '--batch', batch, '--step', 'push', '--outcome', 'failed', '--commit', commit, '--observation', 'Rejected by local receive hook')
        self.assertEqual(self.cli('closure', 'verify', code=1)['next'], 'push')
        hook.unlink()
        self.git('push', 'origin', 'main')
        self.cli('closure', 'record', '--batch', batch, '--step', 'push', '--outcome', 'success', '--commit', commit, '--observation', 'Retry push succeeded')
        self.cli('closure', 'verify')

    def test_wrong_owned_content_and_unordered_success(self):
        self.configure()
        batch, commit, manifest = self.batch()
        self.cli('closure', 'record', '--batch', batch, '--step', 'push', '--outcome', 'success', '--commit', commit, '--manifest', str(manifest), code=2)
        other = self.commit('Empty fixture') if False else self.git('rev-parse', 'HEAD~1')
        self.cli('closure', 'record', '--batch', batch, '--step', 'commit', '--outcome', 'success', '--commit', other, '--manifest', str(manifest), code=2)

    def test_complete_new_batch_and_policy_change(self):
        self.configure(('commit',))
        batch, commit, manifest = self.batch()
        self.cli('closure', 'record', '--batch', batch, '--step', 'commit', '--outcome', 'success', '--commit', commit, '--manifest', str(manifest))
        self.cli('closure', 'verify')
        base = commit
        self.write('tiny.py', 'def tiny():\n    return 3\n')
        paths = [{'path': 'tiny.py', 'digest': hashlib.sha256((self.root / 'tiny.py').read_bytes()).hexdigest()}]
        second_manifest = {'version': 1, 'base': base, 'paths': paths, 'evidence_ids': []}
        manifest.write_text(json.dumps(second_manifest))
        second = self.commit('Second batch')
        batch2 = digest({'evidence_ids': [], 'paths': paths})
        self.cli('closure', 'record', '--batch', batch2, '--step', 'commit', '--outcome', 'success', '--commit', second, '--manifest', str(manifest), code=2)
        self.cli('closure', 'record', '--new-batch', '--batch', batch2, '--step', 'commit', '--outcome', 'success', '--commit', second, '--manifest', str(manifest))
        self.cli('closure', 'verify')
        self.write('.agents/long-horizon.md', (self.root / '.agents/long-horizon.md').read_text().replace('Fixture authorizes', 'Changed authorization authorizes'))
        self.cli('closure', 'verify', code=1)

    def test_commit_step_accepts_eol_converted_checkout(self):
        self.configure(('commit',))
        self.git('config', 'core.autocrlf', 'true')
        base = self.git('rev-parse', 'HEAD')
        (self.root / 'tiny.py').write_bytes(b'def tiny():\r\n    return 2\r\n')
        built = self.cli('closure', 'manifest', '--base', base, '--pending', 'a' * 64)
        commit = self.commit('Owned batch')
        self.assertNotIn(b'\r\n', self.git_bytes('show', commit + ':tiny.py'))
        self.cli('closure', 'record', '--batch', built['batch'], '--step', 'commit', '--outcome', 'success',
                 '--commit', commit, '--manifest', built['path'])
        self.assertEqual(self.cli('closure', 'verify')['state'], 'complete')
        # Different content still fails even after eol conversion.
        (self.root / 'tiny.py').write_bytes(b'def tiny():\r\n    return 3\r\n')
        other = self.cli('closure', 'manifest', '--base', commit, '--pending', 'a' * 64)
        self.commit('Second batch')
        (self.root / 'tiny.py').write_bytes(b'def tiny():\r\n    return 4\r\n')
        wrong = self.commit('Wrong content')
        self.cli('closure', 'record', '--new-batch', '--batch', other['batch'], '--step', 'commit', '--outcome', 'success',
                 '--commit', wrong, '--manifest', other['path'], code=2)

    def git_bytes(self, *args):
        import subprocess
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, check=True).stdout
