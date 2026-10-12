"""Windows defaults are native; explicit XDG roots keep their existing contract.

Platform selection is injected on POSIX; these are not native Windows results.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import delegation_support
import long_horizon_support
from delegation_check import state as delegation, DelegationError
from long_horizon import state as horizon


class WindowsDefaultsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='windows defaults ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'user profile'
        self.local = self.base / 'redirected local appdata'

    def test_windows_native_defaults_for_both_plugins(self):
        for plugin, module in [('delegation', delegation), ('long-horizon', horizon)]:
            with self.subTest(plugin=plugin), patch.dict(os.environ, {'LOCALAPPDATA': str(self.local)}, clear=True), patch.object(module, 'sys_platform', return_value='win32'):
                for kind in ('state', 'cache'):
                    self.assertEqual(module.xdg(kind), self.local / 'rickdiculousli-tools' / plugin / kind)
                self.assertFalse(self.local.exists())  # resolution is read-only

    def test_explicit_xdg_overrides_still_win_on_windows(self):
        env = {'LOCALAPPDATA': str(self.local), 'XDG_STATE_HOME': str(self.base / 'state override'), 'XDG_CACHE_HOME': str(self.base / 'cache override')}
        for plugin, module in [('delegation', delegation), ('long-horizon', horizon)]:
            with self.subTest(plugin=plugin), patch.dict(os.environ, env, clear=True), patch.object(module, 'sys_platform', return_value='win32'):
                self.assertEqual(module.xdg('state'), self.base / 'state override/rickdiculousli-tools' / plugin)
                self.assertEqual(module.xdg('cache'), self.base / 'cache override/rickdiculousli-tools' / plugin)

    def test_empty_relative_xdg_values_use_windows_defaults(self):
        for plugin, module in [('delegation', delegation), ('long-horizon', horizon)]:
            for raw in ('', 'relative/path'):
                with self.subTest(plugin=plugin, raw=raw), patch.dict(os.environ, {'LOCALAPPDATA': str(self.local), 'XDG_STATE_HOME': raw, 'XDG_CACHE_HOME': raw}, clear=True), patch.object(module, 'sys_platform', return_value='win32'):
                    for kind in ('state', 'cache'):
                        with self.assertWarns(RuntimeWarning):
                            self.assertEqual(module.xdg(kind), self.local / 'rickdiculousli-tools' / plugin / kind)

    def test_missing_invalid_localappdata_uses_home_appdata_local(self):
        for plugin, module in [('delegation', delegation), ('long-horizon', horizon)]:
            for raw in (None, '', 'relative/appdata'):
                env = {} if raw is None else {'LOCALAPPDATA': raw}
                with self.subTest(plugin=plugin, raw=raw), patch.dict(os.environ, env, clear=True), patch.object(module, 'sys_platform', return_value='win32'), patch('pathlib.Path.home', return_value=self.home):
                    self.assertEqual(module.xdg('state'), self.home / 'AppData/Local/rickdiculousli-tools' / plugin / 'state')
                    self.assertEqual(module.xdg('cache'), self.home / 'AppData/Local/rickdiculousli-tools' / plugin / 'cache')

    def test_posix_defaults_ignore_localappdata(self):
        for plugin, module in [('delegation', delegation), ('long-horizon', horizon)]:
            for platform in ('linux', 'darwin'):
                with self.subTest(plugin=plugin, platform=platform), patch.dict(os.environ, {'LOCALAPPDATA': str(self.local)}, clear=True), patch.object(module, 'sys_platform', return_value=platform), patch('pathlib.Path.home', return_value=self.home):
                    self.assertEqual(module.xdg('state'), self.home / '.local/state/rickdiculousli-tools' / plugin)
                    self.assertEqual(module.xdg('cache'), self.home / '.cache/rickdiculousli-tools' / plugin)

    def test_windows_has_no_legacy_lock_location_or_migration(self):
        root = delegation_support.git_repo(self.base / 'repo')
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.local)}, clear=True), patch.object(delegation, 'sys_platform', return_value='win32'):
            paths = delegation.Paths(root)
            self.assertIsNone(paths.legacy_locks)
            for apply in (False, True):
                with self.assertRaisesRegex(DelegationError, 'POSIX'):
                    delegation.migrate(root, apply)
            self.assertFalse(self.local.exists())
            self.assertFalse((root / '.delegation').exists())
