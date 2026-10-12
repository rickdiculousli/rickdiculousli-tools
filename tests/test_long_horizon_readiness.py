import json
import os
from pathlib import Path
import time
import warnings
from unittest.mock import patch
from long_horizon_support import RepoTest, OVERLAY
from long_horizon import readiness, state, overlay
from long_horizon.git import Git


class ReadinessTests(RepoTest):
    def configure(self, name='cache:readiness.json'):
        self.write('.agents/long-horizon.md', OVERLAY + '\n## Startup\nreadiness: ' + json.dumps(name) + '\n')

    def report(self, checkout=None, age=0):
        from datetime import datetime, timezone
        return {'version': 1, 'checkout': str(checkout or self.root),
                'generated_at': datetime.fromtimestamp(time.time() - age, timezone.utc).isoformat(),
                'levels': {'fixtures': {'ready': True, 'strength': 'probed'}}}

    def test_paths_readonly_and_worktree_scoping(self):
        self.configure()
        output = self.cli('paths')
        current = state.State(Git(self.root))
        self.assertEqual(output['readiness_path'], str(current.cache / 'readiness/readiness.json'))
        self.assertEqual(output['cache_directory'], str(current.cache))
        self.assertEqual(output['state_directory'], str(current.path))
        self.assertEqual(output['cache_identity']['worktree'], str(self.root.resolve()))
        self.assertFalse(state.xdg('cache').exists())
        self.assertFalse(state.xdg('state').exists())
        linked = self.base / 'linked'
        self.git('worktree', 'add', '-b', 'linked', str(linked))
        self.assertNotEqual(output['readiness_path'], self.cli('paths', root=linked)['readiness_path'])

    def test_cache_lookup_and_existing_unknown_rules(self):
        self.configure()
        output = self.cli('paths')
        path = Path(output['readiness_path'])
        self.assertIn('readiness-unknown', [x['code'] for x in self.cli('status')['findings']])
        path.parent.mkdir(parents=True)
        state.atomic(Path(output['cache_identity_path']), output['cache_identity'])
        for report, valid in [(self.report(), True), (self.report(age=86401), False),
                              (self.report(self.base), False), ({'invalid': True}, False)]:
            path.write_text(json.dumps(report))
            policy = overlay.load(Git(self.root))
            value, findings = readiness.load(policy, Git(self.root))
            self.assertEqual(bool(value['levels']), valid)
            self.assertEqual(bool(findings), not valid)

    def test_reject_cache_escape_and_reserved_paths(self):
        for name in ['cache:', 'cache:../escape.json', 'cache:a/../escape.json',
                     'cache:/absolute.json', 'cache:C:\\escape.json', 'cache:..\\escape.json',
                     'cache://server/file', 'cache:a.txt', 'cache:.. /escape.json',
                     'cache:foo:bar.json', 'cache:a./report.json']:
            with self.subTest(name=name):
                self.configure(name)
                self.cli('paths', code=2)
        self.configure()
        current = state.State(Git(self.root))
        current.cache.mkdir(parents=True)
        (current.cache / 'readiness').symlink_to(self.root, target_is_directory=True)
        self.cli('paths', code=2)

    def test_checkout_path_is_outdated_and_not_read(self):
        self.configure('readiness.json')
        self.write('readiness.json', json.dumps(self.report()))
        self.assertIsNone(self.cli('paths')['readiness_path'])
        result = self.cli('status', code=1)
        self.assertEqual(result['selection']['task']['id'], '1.1')
        outdated = next(x for x in result['findings'] if x['code'] == 'layout-outdated')
        self.assertEqual(outdated['severity'], 'error')
        self.assertIn('cache:', outdated['remedy'])

    def test_readiness_only_cache_deleted_worktree_gc(self):
        self.configure('cache:nested/report.json')
        linked = self.base / 'linked'
        self.commit('Cache policy')
        self.git('worktree', 'add', '-b', 'linked', str(linked))
        output = self.cli('paths', root=linked)
        cache = Path(output['cache_directory'])
        state.atomic(cache / 'identity.json', output['cache_identity'])
        state.atomic(Path(output['readiness_path']), self.report(linked))
        self.git('worktree', 'remove', '--force', str(linked))
        now = time.time()
        state.gc(apply=True, now=now)
        self.assertEqual(state.read(cache / 'identity.json')['missing_since'], now)
        state.gc(apply=True, now=now + state.WEEK - 1)
        self.assertTrue(cache.exists())
        state.gc(apply=True, now=now + state.WEEK)
        self.assertFalse(cache.exists())

    def test_unknown_cache_files_protected(self):
        self.configure()
        output = self.cli('paths')
        cache = Path(output['cache_directory'])
        state.atomic(cache / 'identity.json', output['cache_identity'])
        (cache / 'unknown.bin').write_bytes(b'keep')
        result = state.gc(apply=True, now=time.time() + state.MONTH)
        self.assertTrue((cache / 'unknown.bin').exists())
        self.assertTrue(any(x['reason'] == 'unknown cache identity' for x in result['entries']))

    def test_windows_readiness_uses_localappdata_and_override(self):
        self.configure()
        git = Git(self.root)
        for override in ('', str(self.base / 'override')):
            env = {'LOCALAPPDATA': str(self.base / 'local'), 'XDG_CACHE_HOME': override}
            with patch.dict(os.environ, env), patch.object(state, 'sys_platform', return_value='win32'):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    path = readiness.resolve(overlay.load(git), git)
                base = Path(override) / 'rickdiculousli-tools/long-horizon' if override else self.base / 'local/rickdiculousli-tools/long-horizon/cache'
                self.assertEqual(path, base / state.path_key(git.common) / 'worktrees' / state.path_key(git.root) / 'readiness/readiness.json')
                self.assertFalse(base.exists())

    def test_cache_read_rejects_missing_or_recreated_identity(self):
        self.configure()
        output = self.cli('paths')
        state.atomic(Path(output['readiness_path']), self.report())
        for saved in (None, ['malformed'], {**output['cache_identity'], 'volume': -1}):
            if saved is not None:
                state.atomic(Path(output['cache_identity_path']), saved)
            findings = self.cli('status')['findings']
            self.assertIn('readiness-unknown', [x['code'] for x in findings])
        self.cli('paths', code=2)
