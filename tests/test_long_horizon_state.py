import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
from long_horizon_support import RepoTest
from long_horizon import state
from long_horizon.git import Git
from long_horizon.model import Invalid


class StateTests(RepoTest):
    def test_xdg_defaults(self):
        for raw in ('', 'relative/path'):
            with patch.dict(os.environ, {'XDG_STATE_HOME': raw}):
                self.assertEqual(state.xdg('state'), Path.home() / '.local/state/rickdiculousli-tools/long-horizon')

    def test_fixed_lock_and_atomic_failure(self):
        current = state.State(Git(self.root))
        current.put('closure.json', {'old': True})
        lock_stat = (current.root / 'state.lock').stat().st_ino
        with patch('long_horizon.state.os.replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                current.put('closure.json', {'new': True})
        self.assertEqual(current.get('closure.json'), {'old': True})
        state.gc(apply=True)
        self.assertEqual((current.root / 'state.lock').stat().st_ino, lock_stat)
        self.assertFalse(list(current.path.glob('.write-*')))

    def test_deleted_worktree_grace_and_registration(self):
        linked = self.base / 'linked'
        self.git('worktree', 'add', '-b', 'linked', str(linked))
        current = state.State(Git(linked))
        current.put('closure.json', {'steps': ['push'], 'observations': {}})
        now = time.time()
        import shutil
        shutil.rmtree(linked)
        state.gc(apply=True, now=now)
        self.assertTrue(current.path.exists())  # Git still registers it
        self.git('worktree', 'prune')  # fixture deliberately removes registration
        state.gc(apply=True, now=now)
        self.assertEqual(state.read(current.path / 'identity.json')['missing_since'], now)
        preview = state.gc(now=now + state.WEEK)
        self.assertTrue(any(x['action'] == 'remove' and x.get('unfinished_closure') for x in preview['entries']))
        self.assertTrue(current.path.exists())
        state.gc(apply=True, now=now + state.WEEK - 1)
        self.assertTrue(current.path.exists())
        state.gc(apply=True, now=now + state.WEEK)
        self.assertFalse(current.path.exists())
        state.gc(apply=True, now=now + 2 * state.WEEK)
        self.assertTrue((current.root / 'state.lock').is_file())

    def test_live_pending_protection_and_unreferenced_expiry(self):
        current = state.State(Git(self.root))
        current.put('snapshots/' + 'a' * 64 + '.json', {'created': 1})
        current.put('snapshots/' + 'b' * 64 + '.json', {'created': 1})
        current.put('evidence/' + 'c' * 64 + '.json', {'snapshot': 'a' * 64})
        state.gc(apply=True)
        self.assertTrue((current.path / 'snapshots' / ('a' * 64 + '.json')).is_file())
        self.assertFalse((current.path / 'snapshots' / ('b' * 64 + '.json')).exists())
        self.assertTrue((current.path / 'evidence' / ('c' * 64 + '.json')).is_file())

    def test_weekly_throttle_and_preview_no_creation(self):
        state.gc()
        self.assertFalse(state.xdg('state').exists())
        current = state.State(Git(self.root))
        current.put('closure.json', {'ok': True})
        last = state.read(current.root / 'gc.json')['last_sweep']
        self.assertFalse(state.gc(apply=True, if_due=True, now=last + state.WEEK - 1)['due'])
        self.assertTrue(state.gc(apply=True, if_due=True, now=last + state.WEEK)['due'])

    def test_recreated_identity_quarantines(self):
        current = state.State(Git(self.root))
        current.put('closure.json', {'old': True})
        saved = state.read(current.path / 'identity.json')
        saved['files']['worktree']['inode'] += 1
        state.atomic(current.path / 'identity.json', saved)
        with self.assertRaises(Invalid):
            current.get('closure.json')
        current.put('closure.json', {'new': True})
        self.assertEqual(current.get('closure.json'), {'new': True})
        retired = list(current.path.parent.glob('*.retired-*'))
        self.assertEqual(len(retired), 1)
        self.assertEqual(state.read(retired[0] / 'closure.json'), {'old': True})

    def test_process_contention_and_exception_release(self):
        current = state.State(Git(self.root))
        script = 'import sys; sys.path.insert(0,sys.argv[1]); from long_horizon.state import lock; from pathlib import Path;\nwith lock(Path(sys.argv[2]), timeout=.15): print("acquired")'
        with state.lock(current.root):
            result = subprocess.run([sys.executable, '-c', script, str(Path(__file__).resolve().parents[1] / 'plugins/long-horizon/skills/resume/scripts'), str(current.root)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('State lock busy', result.stderr)
        with self.assertRaises(RuntimeError):
            with state.lock(current.root):
                raise RuntimeError('fixture')
        with state.lock(current.root, timeout=.1):
            pass

    def test_volume_unknown_symlink_and_unexpected_lock_errors(self):
        current = state.State(Git(self.root))
        current.put('closure.json', {'preserve': True})
        with patch('long_horizon.state.containing_volume', return_value=-1):
            result = state.gc(apply=True)
        self.assertTrue(any(x['reason'] == 'volume unavailable or changed' for x in result['entries']))
        self.assertTrue(current.path.exists())
        import fcntl
        import errno
        with patch.object(fcntl, 'flock', side_effect=OSError(errno.EIO, 'fixture I/O error')):
            with self.assertRaises(Invalid):
                with state.lock(current.root):
                    pass
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'keep.json').write_text('{}')
        link = current.root / ('f' * 64)
        link.symlink_to(outside, target_is_directory=True)
        state.gc(apply=True)
        self.assertTrue((outside / 'keep.json').exists())

    def test_windows_backend_byte_position_and_release(self):
        import types
        events = []
        backend = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)
        def locking(fd, kind, length):
            events.append((os.lseek(fd, 0, os.SEEK_CUR), kind, length))
        backend.locking = locking
        root = self.base / 'windows mock state'
        with patch.dict(sys.modules, {'fcntl': None, 'msvcrt': backend}):
            with state.lock(root):
                pass
            with self.assertRaises(RuntimeError):
                with state.lock(root):
                    raise RuntimeError('fixture')
        self.assertEqual(events, [(0, 1, 1), (0, 2, 1)] * 2)
        self.assertEqual((root / 'state.lock').read_bytes(), b'\0')

    def test_windows_mock_contention_timeout_and_io_error(self):
        import errno
        import types
        root = self.base / 'windows contention'
        backend = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)
        backend.locking = lambda *args: (_ for _ in ()).throw(OSError(errno.EACCES, 'fixture contention'))
        with patch.dict(sys.modules, {'fcntl': None, 'msvcrt': backend}):
            with self.assertRaisesRegex(Invalid, 'State lock busy'):
                with state.lock(root, timeout=0):
                    pass
            backend.locking = lambda *args: (_ for _ in ()).throw(OSError(errno.EIO, 'fixture unexpected I/O'))
            with self.assertRaisesRegex(Invalid, 'Cannot lock'):
                with state.lock(root):
                    pass
        with state.lock(root):
            pass

    def test_interrupted_deletion_retries_without_losing_identity(self):
        import shutil
        linked = self.base / 'linked interrupted'
        self.git('worktree', 'add', '-b', 'interrupted', str(linked))
        current = state.State(Git(linked))
        current.put('evidence/' + 'a' * 64 + '.json', {'pending': True})
        shutil.rmtree(linked)
        self.git('worktree', 'prune')
        now = time.time()
        state.gc(apply=True, now=now)
        with patch('long_horizon.state.shutil.rmtree', side_effect=OSError('interrupted fixture deletion')):
            state.gc(apply=True, now=now + state.WEEK)
        self.assertTrue((current.path / 'identity.json').is_file())
        state.gc(apply=True, now=now + state.WEEK)
        self.assertFalse(current.path.exists())

    def test_reject_checkout_and_installed_plugin_runtime_roots(self):
        from long_horizon_support import SCRIPT
        for root in [self.root / 'scratch', self.root / '.git/scratch', SCRIPT.parent / 'scratch']:
            with patch.dict(os.environ, {'XDG_STATE_HOME': str(root)}):
                with self.assertRaisesRegex(Invalid, 'inside a checkout'):
                    state.State(Git(self.root))
                self.assertFalse(root.exists())
        with patch.dict(os.environ, {'XDG_STATE_HOME': str(self.root / 'scratch')}):
            with self.assertRaises(Invalid):
                state.gc(apply=True, location_root=self.root)

    def test_recreated_payload_allows_new_prepare_without_reusing_old_attempt(self):
        old = self.prepare('old-generation')
        current = state.State(Git(self.root))
        saved = state.read(current.path / 'identity.json')
        saved['files']['worktree']['inode'] += 1
        state.atomic(current.path / 'identity.json', saved)
        self.assertEqual(self.cli('status')['closure']['state'], 'unknown')
        new = self.prepare('new-generation')
        self.assertNotEqual(old['id'], new['id'])
        retired = list(current.path.parent.glob('*.retired-*'))
        self.assertEqual(len(retired), 1)
        self.assertTrue((retired[0] / 'snapshots' / (old['id'] + '.json')).exists())

    def test_scoped_draft_cli_and_expiry(self):
        output = self.cli('state', 'draft', '--id', 'review')
        current = state.State(Git(self.root))
        path = Path(output['draft_directory'])
        self.assertEqual(path, current.cache / 'drafts/review')
        self.assertEqual(self.cli('status')['cache_directory'], str(current.cache))
        self.assertFalse(state.alive(state.read(path / 'identity.json')['owner']))
        (path / 'overlay.md').write_text('draft bytes')
        now = time.time()
        state.gc(apply=True, now=now + state.MONTH - 1)
        self.assertTrue(path.exists())
        state.gc(apply=True, now=now + state.MONTH + 1)
        self.assertFalse(path.exists())

    def test_draft_active_unknown_symlink_and_renewal(self):
        path = Path(self.cli('state', 'draft', '--id', 'review')['draft_directory'])
        original = state.read(path / 'identity.json')
        state.atomic(path / 'identity.json', {**original, 'owner': state.owner()})
        state.gc(apply=True, now=time.time() + 2 * state.MONTH)
        self.assertTrue(path.exists())
        with self.assertRaises(Invalid):
            state.draft(Git(self.root), 'review')
        state.atomic(path / 'identity.json', {**original, 'owner': {'pid': os.getpid(), 'start': None}})
        state.gc(apply=True, now=time.time() + 2 * state.MONTH)
        self.assertTrue(path.exists())
        state.atomic(path / 'identity.json', original)
        self.cli('state', 'draft', '--id', 'review')
        (path / 'escape.md').symlink_to(self.root / 'tiny.py')
        state.gc(apply=True, now=time.time() + 2 * state.MONTH)
        self.assertTrue(path.exists())
        self.cli('state', 'draft', '--id', '../escape', code=2)

    def test_cache_draft_deleted_worktree_has_recovery_window(self):
        linked = self.base / 'linked'
        self.git('worktree', 'add', '-b', 'linked', str(linked))
        path = Path(self.cli('state', 'draft', '--id', 'recovery', root=linked)['draft_directory'])
        current = state.State(Git(linked))
        self.assertNotEqual(current.cache, state.State(Git(self.root)).cache)
        self.git('worktree', 'remove', '--force', str(linked))
        now = time.time()
        state.gc(apply=True, now=now)
        self.assertTrue(path.exists())
        state.gc(apply=True, now=now + state.WEEK)
        self.assertFalse(current.cache.exists())

    def test_git_registration_probe_never_holds_root_lock(self):
        current = state.State(Git(self.root))
        current.put('closure.json', {'preserve': True})
        native = state.registered
        def probe(common, worktree):
            with state.lock(current.root, timeout=.1):
                pass
            return native(common, worktree)
        with patch('long_horizon.state.registered', side_effect=probe):
            state.gc(apply=True)
