"""XDG safety exercised against disposable Git repositories and real OS locks."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from delegation_support import git, git_repo, isolate_xdg, run_cli, state_payload, SCRIPTS, write_overlay
from delegation_check import DelegationError, state, file_lock, locks
from delegation_check.ledger import read_events, ledger_lock
from delegation_check.overlay import Lock
from delegation_check.tree import tree_hash


class StateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='delegation state ')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        isolate_xdg(self, self.base)
        self.root = git_repo(self.base / 'repo with spaces')
        self.paths = state.Paths(self.root)

    def legacy(self, pending=False):
        source = self.root / '.delegation'
        (source / 'briefs').mkdir(parents=True)
        (source / 'context').mkdir()
        (source / 'logs/d1').mkdir(parents=True)
        (source / '.gitignore').write_text('*\n')
        (source / 'briefs/d1.md').write_text('Old brief\n')
        (source / 'context/pinned.md').write_text('Old context\n')
        (source / 'logs/d1/1.log').write_text('Original output\n')
        events = [{'event': 'open', 'delegation': 'd1', 'tier': 'routine', 'writes': False,
                   'brief': '.delegation/briefs/d1.md', 'tree': 'old-tree',
                   'context': {'.delegation/context/pinned.md': hashlib.sha256(b'Old context\n').hexdigest()}},
                  {'event': 'result', 'delegation': 'd1', 'id': 'd1#1', 'ok': True,
                   'stable': True, 'tree': 'old-tree', 'output_sha256': 'historical-hash',
                   'log': '.delegation/logs/d1/1.log'}]
        if not pending:
            events.append({'event': 'close', 'delegation': 'd1', 'outcome': 'done'})
        (source / 'ledger.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        return source, events

    def test_paths_inspection_creates_nothing(self):
        result = run_cli(self.root, 'paths', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(info['version'], 1)
        self.assertEqual(len(info['repository_key']), 64)
        self.assertEqual(len(info['worktree_key']), 64)
        self.assertIn('xdg state', info['root_mutex'])
        self.assertFalse(self.paths.state_root.exists())
        self.assertFalse(self.paths.cache_root.exists())
        self.assertFalse((self.root / '.delegation').exists())

    def test_empty_read_creates_no_payload(self):
        self.assertEqual(read_events(self.root), [])
        self.assertFalse(self.paths.path.exists())
        self.assertTrue((self.paths.state_root / 'state.lock').exists())

    def test_xdg_default_empty_relative_and_custom(self):
        for raw in (None, '', 'relative/path'):
            with patch.dict(os.environ, {}, clear=True), patch('pathlib.Path.home', return_value=self.base):
                if raw is not None:
                    os.environ['XDG_STATE_HOME'] = raw
                    os.environ['XDG_CACHE_HOME'] = raw
                    with self.assertWarns(RuntimeWarning):
                        actual = state.xdg('state')
                else:
                    actual = state.xdg('state')
                self.assertEqual(actual, self.base / '.local/state/rickdiculousli-tools/delegation')
                with __import__('warnings').catch_warnings():
                    __import__('warnings').simplefilter('ignore')
                    self.assertEqual(state.xdg('cache'), self.base / '.cache/rickdiculousli-tools/delegation')
        self.assertEqual(self.paths.state_root, self.base / 'xdg state/rickdiculousli-tools/delegation')

    def test_case_normalized_full_keys(self):
        with patch('delegation_check.state.os.path.normcase', side_effect=lambda s: s.lower()):
            self.assertEqual(state.key(self.base / 'Foo'), state.key(self.base / 'foo'))
        self.assertEqual(len(state.key(self.root)), 64)

    def test_reject_runtime_roots_inside_checkout(self):
        for name in ('XDG_STATE_HOME', 'XDG_CACHE_HOME'):
            with patch.dict(os.environ, {name: str(self.root / 'runtime')}):
                with self.assertRaisesRegex(DelegationError, 'inside a checkout'):
                    state.Paths(self.root)

    def test_gc_rejects_checkout_runtime_root_before_creating_lock(self):
        with patch('pathlib.Path.cwd', return_value=self.root), patch.dict(os.environ, XDG_STATE_HOME=str(self.root / 'runtime')):
            with self.assertRaisesRegex(DelegationError, 'inside a checkout'):
                state.gc(apply=True)
        self.assertFalse((self.root / 'runtime').exists())

    def test_unwritable_root_no_fallback(self):
        bad = self.base / 'not a directory'
        bad.write_text('file')
        with patch.dict(os.environ, XDG_STATE_HOME=str(bad)):
            result = run_cli(self.root, 'pending')
        self.assertEqual(result.returncode, 2)
        self.assertIn('same writable XDG_STATE_HOME', result.stderr)
        self.assertFalse((self.root / '.delegation').exists())

    def test_linked_worktree_shares_repo_but_not_payload(self):
        other = self.base / 'linked worktree'
        git(self.root, 'worktree', 'add', '-q', '-b', 'fixture-linked', str(other))
        linked = state.Paths(other)
        self.assertEqual(self.paths.repo, linked.repo)
        self.assertNotEqual(self.paths.path, linked.path)
        state_payload(self.root)
        state_payload(other)
        self.assertEqual(linked.identity['common'], self.paths.identity['common'])

    def test_recreated_worktree_refuses_old_payload(self):
        state_payload(self.root)
        moved = self.base / 'old root'
        self.root.rename(moved)
        shutil.copytree(moved, self.root)
        with self.assertRaisesRegex(DelegationError, 'identity changed'):
            read_events(self.root)
        report = state.gc(apply=True, now=time.time() + state.MONTH)
        self.assertIn('recreated', report['entries'][0]['reason'])
        self.assertTrue(self.paths.path.exists())

    def test_logical_context_integrity_and_no_bookkeeping_hash_changes(self):
        payload = state_payload(self.root)
        context = payload / 'context/input with spaces.md'
        context.parent.mkdir()
        context.write_text('first')
        before = tree_hash(self.root, ['state:context/input with spaces.md'])
        (payload / 'ledger.jsonl').write_text('{}\n')
        self.assertEqual(before, tree_hash(self.root, ['state:context/input with spaces.md']))
        context.write_text('second')
        self.assertNotEqual(before, tree_hash(self.root, ['state:context/input with spaces.md']))
        self.assertEqual(state.context_path(self.root, 'state:context/input with spaces.md'), context)
        self.assertEqual(list(self.paths.cache.glob('hashing/*')), [])

    def test_context_traversal_symlink_and_ledger_reference_refused(self):
        payload = state_payload(self.root)
        (payload / 'context').mkdir()
        (payload / 'context/escape').symlink_to(self.base, target_is_directory=True)
        for ref in ('state:context/../../ledger.jsonl', 'state:context/escape/anything',
                    'state:logs/d1/1.log', 'state:context/C:\\outside', 'state:context/'):
            with self.subTest(ref=ref), self.assertRaises(DelegationError):
                state.context_path(self.root, ref)

    def test_no_git_discovery_under_ledger_mutex(self):
        state_payload(self.root)
        with ledger_lock(self.root):
            with patch('delegation_check.tree._git', side_effect=AssertionError('Git under mutex')):
                from delegation_check.ledger import _read_events_unlocked, log_path
                self.assertEqual(_read_events_unlocked(self.root), [])
                self.assertEqual(log_path(self.root, 'd1#1'), self.paths.path / 'logs/d1/1.log')
                self.assertEqual(state.context_path(self.root, 'state:context/a.md'), self.paths.path / 'context/a.md')

    def test_migration_preview_preserves_bytes_and_unknown_files(self):
        source, events = self.legacy()
        (source / 'keep.me').write_text('unknown')
        preview = state.migrate(self.root)
        self.assertEqual(preview['events'], 3)
        self.assertEqual(preview['unknown'], ['keep.me'])
        self.assertFalse(self.paths.state_root.exists())
        original = (source / 'ledger.jsonl').read_bytes()
        applied = state.migrate(self.root, True)
        self.assertTrue(applied['applied'])
        self.assertEqual((self.paths.path / 'ledger.jsonl').read_bytes(), original)
        self.assertEqual(read_events(self.root), events)
        from delegation_check.state import recorded_path
        self.assertEqual(recorded_path(self.root, events[1], 'log').read_text(), 'Original output\n')
        self.assertTrue(state.migrate(self.root, True)['noop'])
        self.assertEqual((source / 'keep.me').read_text(), 'unknown')

    def test_unmigrated_ledger_blocks_fresh_history(self):
        self.legacy()
        result = run_cli(self.root, 'pending')
        self.assertEqual(result.returncode, 2)
        self.assertIn('state migrate', result.stderr)
        self.assertFalse(self.paths.path.exists())

    def test_migration_open_and_busy_legacy_lock_refused(self):
        source, _ = self.legacy(pending=True)
        with self.assertRaisesRegex(DelegationError, 'quiescent'):
            state.migrate(self.root, True)
        events = state.events_at(source / 'ledger.jsonl')
        events.append({'event': 'close', 'delegation': 'd1'})
        (source / 'ledger.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        handle = file_lock.try_acquire(source / 'ledger.lock')
        try:
            self.assertIn(str(source / 'ledger.lock'), state.migrate(self.root)['busy_legacy_locks'])
            with self.assertRaisesRegex(DelegationError, 'busy legacy'):
                state.migrate(self.root, True)
        finally:
            file_lock.release(handle)

    def test_migration_destination_conflict_and_changed_source(self):
        source, _ = self.legacy()
        self.paths.path.mkdir(parents=True)
        (self.paths.path / 'ledger.jsonl').write_text('different')
        with self.assertRaisesRegex(DelegationError, 'Conflicting XDG'):
            state.migrate(self.root, True)
        shutil.rmtree(self.paths.path)
        state.migrate(self.root, True)
        (source / 'context/pinned.md').write_text('changed old bytes')
        with self.assertRaisesRegex(DelegationError, 'changed'):
            read_events(self.root)
        with self.assertRaisesRegex(DelegationError, 'changed'):
            state.migrate(self.root, True)

    def test_interrupted_staging_resumes_and_changed_staging_refuses(self):
        self.legacy()
        with patch('delegation_check.state.shutil.copyfile', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                state.migrate(self.root, True)
        self.assertTrue(state.migrate(self.root, True)['applied'])
        self.assertFalse((self.paths.repo / ('migration-' + self.paths.worktree_key)).exists())

    def test_interrupted_migration_conflicting_staging_and_source_refused(self):
        source, _ = self.legacy()
        with patch('delegation_check.state.shutil.copyfile', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                state.migrate(self.root, True)
        staging = self.paths.repo / ('migration-' + self.paths.worktree_key)
        (staging / 'unknown.txt').write_text('retain')
        with self.assertRaisesRegex(DelegationError, 'Unknown/unsafe'):
            state.migrate(self.root, True)
        (staging / 'unknown.txt').unlink()
        target = staging / 'briefs/d1.md'
        target.parent.mkdir(exist_ok=True)
        target.write_text('conflicting')
        with self.assertRaisesRegex(DelegationError, 'staging conflict'):
            state.migrate(self.root, True)
        target.unlink()
        (source / 'context/pinned.md').write_text('changed while interrupted')
        with self.assertRaisesRegex(DelegationError, 'source changed'):
            state.migrate(self.root, True)
        self.assertFalse(self.paths.path.exists())

    def test_owner_pid_reuse_unknown_and_crash(self):
        record = {'pid': 123, 'start': 'original'}
        for current, expected in [('original', True), ('new', False), ('gone', False), (None, None)]:
            with patch('delegation_check.state.process_start', return_value=current):
                self.assertIs(state.alive(record), expected)
        self.assertTrue(state.alive(state.owner()))
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            record = {'pid': proc.pid, 'start': state.process_start(proc.pid)}
            self.assertTrue(state.alive(record))
        finally:
            proc.kill()
            proc.wait()
        self.assertFalse(state.alive(record))

    def test_gc_preview_throttle_and_recovery_window(self):
        other = self.base / 'disposable worktree'
        git(self.root, 'worktree', 'add', '-q', '-b', 'fixture-linked', str(other))
        payload = state_payload(other)
        (payload / 'ledger.jsonl').write_text(json.dumps({'event': 'open', 'delegation': 'unfinished'}) + '\n')
        git(self.root, 'worktree', 'remove', '--force', str(other))
        now = time.time()
        preview = state.gc(now=now)
        entry = next(x for x in preview['entries'] if x['path'] == str(payload))
        self.assertEqual(entry['pending'], ['unfinished'])
        self.assertEqual(entry['deadline'], now + state.WEEK)
        self.assertIsNone(state.read(payload / 'identity.json')['missing_since'])
        state.gc(apply=True, now=now)
        self.assertFalse(state.gc(apply=True, if_due=True, now=now + 1)['due'])
        state.gc(apply=True, now=now + state.WEEK - 1)
        self.assertTrue(payload.exists())
        state.gc(apply=True, now=now + state.WEEK)
        self.assertFalse(payload.exists())
        self.assertTrue((self.paths.state_root / 'state.lock').exists())
        self.assertFalse((self.root / 'docs').exists())

    def test_gc_retains_stale_registration(self):
        other = self.base / 'disposable worktree'
        git(self.root, 'worktree', 'add', '-q', '-b', 'fixture-linked', str(other))
        payload = state_payload(other)
        shutil.rmtree(other)
        state.gc(apply=True, now=time.time() + 2 * state.WEEK)
        self.assertTrue(payload.exists())
        self.assertIsNone(state.read(payload / 'identity.json')['missing_since'])

    def test_gc_pins_evidence_and_declared_roles_but_expires_drafts(self):
        payload = state_payload(self.root)
        (payload / 'context').mkdir()
        (payload / 'briefs').mkdir()
        for name in ('context/pinned.md', 'context/role.md', 'context/draft.md', 'briefs/draft.md'):
            target = payload / name
            target.write_text('bytes')
            os.utime(target, (1, 1))
        write_overlay(self.root, '## Roles\nr: tier=routine, runbook=state:context/role.md, max-uses=2\n')
        (payload / 'ledger.jsonl').write_text(json.dumps({'event': 'open', 'delegation': 'old',
            'context': {'state:context/pinned.md': 'hash'}}) + '\n')
        state.gc(apply=True, now=time.time())
        self.assertTrue((payload / 'context/pinned.md').exists())
        self.assertTrue((payload / 'context/role.md').exists())
        self.assertFalse((payload / 'context/draft.md').exists())
        self.assertFalse((payload / 'briefs/draft.md').exists())

    def test_active_hashing_and_uncertain_owner_protect_deleted_payload(self):
        payload = state_payload(self.root)
        attempt = self.paths.cache / 'hashing/attempt'
        state.atomic(attempt / 'identity.json', state.owner())
        saved = state.read(payload / 'identity.json')
        shutil.rmtree(self.root)
        state.atomic(payload / 'identity.json', {**saved, 'missing_since': 1})
        state.gc(apply=True, now=time.time())
        self.assertTrue(payload.exists())
        self.assertTrue(attempt.exists())
        state.atomic(attempt / 'identity.json', {'pid': os.getpid(), 'start': None})
        state.gc(apply=True, now=time.time())
        self.assertTrue(payload.exists())
        state.atomic(attempt / 'identity.json', {'pid': 999999999, 'start': 'gone'})
        state.gc(apply=True, now=time.time())
        self.assertFalse(payload.exists())
        self.assertFalse(attempt.exists())

    def test_native_slot_contention_and_waiter_pins_cleanup(self):
        with locks.hold(self.root, 'mem', Lock(wait=1), {'command': 'parent'}):
            path = self.paths.locks / 'mem.0.lock'
            self.assertFalse(state.locks_idle(self.paths.locks))
            meta = state.read(path.with_suffix('.json'))
            self.assertTrue(state.alive(meta['holder']))
            result = run_cli(self.root, 'paths', '--json')
            self.assertEqual(result.returncode, 0)
            # GC cannot replace the slot inode, including while a waiter exists.
            before = path.stat().st_ino
            state.gc(apply=True, now=time.time() + state.MONTH)
            self.assertEqual(before, path.stat().st_ino)
        self.assertTrue(state.locks_idle(self.paths.locks))
        path = self.paths.locks / 'mem.0.lock'
        state.atomic(path.with_suffix('.json'), {'waiters': {'one': state.owner()}})
        self.assertFalse(state.locks_idle(self.paths.locks))
        state.atomic(path.with_suffix('.json'), {'waiters': {'unknown': {'pid': os.getpid(), 'start': None}}})
        self.assertFalse(state.locks_idle(self.paths.locks))

    def test_live_waiter_gc_and_crashed_holder_use_same_inode(self):
        script = "import sys,time; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from delegation_check.locks import hold; from delegation_check.overlay import Lock;\nwith hold(Path(sys.argv[2]),'mem',Lock(wait=5),{'command':'fixture'}): time.sleep(float(sys.argv[3]))"
        argv = [sys.executable, '-c', script, str(SCRIPTS), str(self.root)]
        holder = subprocess.Popen([*argv, '30'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        waiter = None
        slot = self.paths.locks / 'mem.0.lock'
        try:
            deadline = time.monotonic() + 5
            while not state.read(slot.with_suffix('.json'), {}).get('holder'):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.02)
            inode = slot.stat().st_ino
            waiter = subprocess.Popen([*argv, '.2'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            while not state.read(slot.with_suffix('.json'), {}).get('waiters'):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.02)
            # Registered waiters and native contention protect collection.
            with state.mutex(self.paths.state_root):
                self.assertFalse(state.locks_idle(self.paths.locks))
            state.gc(apply=True, now=time.time() + state.MONTH)
            self.assertEqual(slot.stat().st_ino, inode)
            holder.kill()
            holder.communicate(timeout=5)
            out, err = waiter.communicate(timeout=5)
            self.assertEqual(waiter.returncode, 0, out + err)
            self.assertEqual(slot.stat().st_ino, inode)
            metadata = state.read(slot.with_suffix('.json'))
            self.assertFalse(metadata['holder'])
            self.assertFalse(metadata['waiters'])
        finally:
            for process in (holder, waiter):
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)

    def test_retired_repository_gc_cannot_remove_live_native_holder(self):
        with locks.hold(self.root, 'mem', Lock(wait=1), {'command': 'fixture'}):
            slot = self.paths.locks / 'mem.0.lock'
            inode = slot.stat().st_ino
            shutil.rmtree(self.root)
            for path in (self.paths.path, self.paths.repo):
                saved = state.read(path / 'identity.json')
                state.atomic(path / 'identity.json', {**saved, 'missing_since': 1})
            state.gc(apply=True, now=time.time())
            self.assertTrue(self.paths.path.exists())
            self.assertTrue(self.paths.repo.exists())
            self.assertEqual(slot.stat().st_ino, inode)
        state.gc(apply=True, now=time.time())
        self.assertFalse(self.paths.path.exists())
        self.assertFalse(self.paths.repo.exists())

    def test_retired_repository_resource_locks_expire_after_grace(self):
        with locks.hold(self.root, 'mem', Lock(wait=1), {'command': 'fixture'}):
            pass
        slot = self.paths.locks / 'mem.0.lock'
        self.assertTrue(slot.exists())
        shutil.rmtree(self.root)
        now = time.time()
        state.gc(apply=True, now=now)
        self.assertTrue(slot.exists())
        state.gc(apply=True, now=now + state.WEEK)
        self.assertFalse(self.paths.path.exists())
        # Repository recovery starts when its last payload is retired.
        state.gc(apply=True, now=now + 2 * state.WEEK)
        self.assertFalse(self.paths.repo.exists())
        self.assertTrue((self.paths.state_root / 'state.lock').exists())

    def test_unknown_volume_and_payload_symlink_retained(self):
        payload = state_payload(self.root)
        with patch('delegation_check.state.volume', return_value=-1):
            report = state.gc(apply=True, now=time.time() + state.MONTH)
        self.assertIn('unavailable volume', report['entries'][0]['reason'])
        (payload / 'briefs').symlink_to(self.base, target_is_directory=True)
        state.gc(apply=True, now=time.time() + state.MONTH)
        self.assertTrue(payload.exists())
        self.assertTrue(self.root.exists())

    def test_migration_new_native_slot_and_other_worktree_activity_refused(self):
        self.legacy()
        self.paths.locks.mkdir(parents=True)
        handle = file_lock.try_acquire(self.paths.locks / 'mem.0.lock')
        try:
            with self.assertRaisesRegex(DelegationError, 'resource owner'):
                state.migrate(self.root, True)
        finally:
            file_lock.release(handle)
        other = self.base / 'other'
        git(self.root, 'worktree', 'add', '-q', str(other))
        payload = state_payload(other)
        state.atomic(payload / 'active/probe.json', state.owner())
        with self.assertRaisesRegex(DelegationError, 'active new'):
            state.migrate(self.root, True)

    def test_root_lock_inode_is_permanent(self):
        state_payload(self.root)
        lock = self.paths.state_root / 'state.lock'
        inode = lock.stat().st_ino
        state.gc(apply=True)
        state_payload(self.root)
        self.assertEqual(inode, lock.stat().st_ino)

    def test_gc_outside_checkout(self):
        result = run_cli(self.base, 'state', 'gc', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['entries'], [])


class NativeBackendTests(unittest.TestCase):
    def test_mock_windows_byte_lock_and_release(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        backend = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=Mock())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.lock'
            with patch.object(file_lock.os, 'name', 'nt'), patch.object(file_lock, 'msvcrt', backend, create=True):
                handle = file_lock.try_acquire(path)
                file_lock.release(handle)
            self.assertEqual([x.args[1:] for x in backend.locking.call_args_list], [(1, 1), (2, 1)])
            self.assertTrue(handle.closed)
