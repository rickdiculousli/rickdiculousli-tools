from delegation_support import isolate_xdg, state_payload
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from delegation_support import git, git_repo, run_cli, write_overlay
from delegation_check import patterns, state
from delegation_check.overlay import load_overlay


def brief_text(module='mod1', validators='unit'):
    return (f'Tier: execute\nGoal: name functions\nInputs: src/{module}/file.c\n'
            f'May write: src/{module}/file.c\nDone when: named; validators: {validators}\n')


class PatternTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        isolate_xdg(self, self.base)
        self.root = git_repo(self.base / 'repo')
        self.briefs = state_payload(self.root) / 'briefs'
        self.briefs.mkdir()

    def brief(self, name, text=None, root=None):
        directory = self.briefs if root is None else state_payload(root) / 'briefs'
        directory.mkdir(exist_ok=True)
        path = directory / f'{name}.md'
        path.write_text(text or brief_text())
        return path

    def open(self, name, *extra, root=None, text=None):
        root = root or self.root
        return run_cli(root, 'open', '--delegation', name, '--tier', 'execute',
                       '--brief', str(self.brief(name, text, root if root != self.root else None)), *extra)

    def cycle(self, name, *extra, root=None, text=None, outcome='done'):
        result = self.open(name, *extra, root=root, text=text)
        self.assertEqual(result.returncode, 0, result.stderr)
        closed = run_cli(root or self.root, 'close', '--delegation', name, '--outcome', outcome)
        self.assertEqual(closed.returncode, 0, closed.stderr)
        return result

    def summary(self, root=None, **options):
        root = root or self.root
        return patterns.summary(state.Paths(root), set(load_overlay(root).roles), **options)

    def kind(self, name, root=None):
        return next(item for item in self.summary(root)['kinds'] if item['kind'] == name)

    def test_unknown_kind_is_refused_before_opening_and_lists_existing_kinds(self):
        result = self.open('a', '--kind', 'name-module')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--new-kind', result.stderr)
        self.assertEqual(run_cli(self.root, 'pending').stdout.strip(), 'No open delegations.')
        self.cycle('b', '--kind', 'name-module', '--new-kind', 'name every function in one module')
        result = self.open('c', '--kind', 'module-naming')
        self.assertEqual(result.returncode, 2)
        self.assertIn('name-module (name every function in one module)', result.stderr)

    def test_registered_kind_is_reused_and_cannot_be_registered_twice(self):
        self.cycle('a', '--kind', 'name-module', '--new-kind', 'name functions')
        self.assertIn('kind name-module', self.cycle('b', '--kind', 'name-module').stdout)
        again = self.open('c', '--kind', 'name-module', '--new-kind', 'other')
        self.assertEqual(again.returncode, 2)
        self.assertIn('already registered', again.stderr)
        self.assertEqual(self.kind('name-module')['count'], 2)
        self.assertEqual(self.kind('name-module')['outcomes'], {'done': 2})

    def test_label_rules(self):
        bad = self.open('a', '--kind', 'Name_Module', '--new-kind', 'x')
        self.assertEqual(bad.returncode, 2)
        self.assertIn('lowercase words joined by hyphens', bad.stderr)
        instance = self.open('b', '--kind', 'port-module-12', '--new-kind', 'x')
        self.assertEqual(instance.returncode, 0, instance.stderr)
        self.assertIn('not one instance', instance.stderr)
        self.assertEqual(self.open('c', '--new-kind', 'x').returncode, 2)

    def test_registry_and_counts_span_linked_worktrees(self):
        linked = self.base / 'linked'
        git(self.root, 'worktree', 'add', '-q', str(linked))
        self.cycle('a', '--kind', 'triage-tests', '--new-kind', 'triage failing test output')
        self.cycle('a', '--kind', 'triage-tests', root=linked)
        main_paths, linked_paths = (json.loads(run_cli(r, 'paths', '--json').stdout) for r in (self.root, linked))
        self.assertEqual(main_paths['kind_registry'], linked_paths['kind_registry'])
        self.assertEqual(main_paths['pattern_log'], linked_paths['pattern_log'])
        self.assertNotEqual(main_paths['scratch_directory'], linked_paths['scratch_directory'])
        self.assertEqual(self.kind('triage-tests')['worktrees'], 2)
        self.assertEqual(self.kind('triage-tests', linked)['count'], 2)

    def test_matching_brief_shape_under_another_label_is_flagged(self):
        self.cycle('a', '--kind', 'name-module', '--new-kind', 'name functions', text=brief_text('mod1'))
        result = self.cycle('b', '--kind', 'module-naming', '--new-kind', 'dup', text=brief_text('mod22'))
        self.assertIn('brief shape matches kind "name-module" (1 earlier use)', result.stderr)
        unrelated = self.cycle('c', '--kind', 'triage', '--new-kind', 'triage', text=brief_text('mod3', 'lint'))
        self.assertNotIn('brief shape matches', unrelated.stderr)
        unlabeled = self.cycle('d', text=brief_text('mod4'))
        self.assertIn('counted by shape only', unlabeled.stderr)

    def test_fingerprint_ignores_instance_names_but_not_shape(self):
        first = patterns.fingerprint(brief_text('mod1').encode(), 'execute', True)
        self.assertEqual(first, patterns.fingerprint(brief_text('mod2').encode(), 'execute', True))
        self.assertNotEqual(first, patterns.fingerprint(brief_text('mod1').encode(), 'routine', True))
        self.assertNotEqual(first, patterns.fingerprint(brief_text('mod1', 'lint').encode(), 'execute', True))

    def test_merge_and_rename_resolve_history_and_future_uses(self):
        self.cycle('a', '--kind', 'name-module', '--new-kind', 'name functions')
        self.cycle('b', '--kind', 'module-naming', '--new-kind', 'dup')
        merged = run_cli(self.root, 'kinds', 'merge', 'module-naming', 'name-module')
        self.assertEqual(merged.returncode, 0, merged.stderr)
        self.assertEqual(self.kind('name-module')['count'], 2)
        alias = self.cycle('c', '--kind', 'module-naming')
        self.assertIn('now counts as "name-module"', alias.stderr)
        self.assertEqual(self.kind('name-module')['count'], 3)
        renamed = run_cli(self.root, 'kinds', 'rename', 'name-module', 'name-module-functions')
        self.assertEqual(renamed.returncode, 0, renamed.stderr)
        self.assertEqual(self.kind('name-module-functions')['count'], 3)
        self.assertEqual(run_cli(self.root, 'kinds', 'merge', 'name-module', 'name-module-functions').returncode, 2)
        listing = run_cli(self.root, 'kinds').stdout
        self.assertIn('name-module-functions (3 uses, 1 worktree, role: none): name functions', listing)
        self.assertNotIn('module-naming', listing)

    def test_patterns_candidates_respect_threshold_marks_and_roles(self):
        for name in ('a', 'b', 'c'):
            self.cycle(name, '--kind', 'triage', *(['--new-kind', 'triage output'] if name == 'a' else []))
        self.cycle('d', '--kind', 'rare', '--new-kind', 'rare work')
        output = run_cli(self.root, 'patterns').stdout
        self.assertIn('Authoring: roles=allowed, scripts=allowed', output)
        self.assertIn('triage: 3 uses, 1 worktree, 1 day; done 3; tiers execute', output)
        self.assertIn('rare: 1 use (below 3)', output)
        data = json.loads(run_cli(self.root, 'patterns', '--json').stdout)
        self.assertEqual([item['kind'] for item in data['kinds'] if item['candidate']], ['triage'])
        self.assertEqual(run_cli(self.root, 'kinds', 'mark', 'triage', 'declined', '--note', 'varied').returncode, 0)
        self.assertFalse(self.kind('triage')['candidate'])
        self.assertNotIn('triage', run_cli(self.root, 'kinds').stdout)
        self.assertIn('declined', run_cli(self.root, 'kinds', '--all').stdout)
        run_cli(self.root, 'kinds', 'mark', 'triage', 'proposed')
        self.assertTrue(self.kind('triage')['candidate'])
        runbook = self.root / '.agents/delegation/runbooks/triage.md'
        runbook.parent.mkdir(parents=True)
        runbook.write_text('triage runbook\n')
        git(self.root, 'add', str(runbook))
        write_overlay(self.root, '## Roles\ntriage: tier=execute, runbook=.agents/delegation/runbooks/triage.md, max-uses=3\n')
        self.assertTrue(self.kind('triage')['role'])
        self.assertFalse(self.kind('triage')['candidate'])

    def test_unlabeled_shapes_are_grouped(self):
        for index in range(3):
            self.cycle(f'u{index}', text=brief_text(f'mod{index}'))
        output = run_cli(self.root, 'patterns').stdout
        self.assertIn('Unlabeled shapes (>= 3 uses; give them a --kind):', output)
        self.assertEqual(self.summary()['unlabeled'][0]['count'], 3)

    def test_role_records_its_kind_and_continuations_keep_it(self):
        runbook = self.root / '.agents/delegation/runbooks/capture.md'
        runbook.parent.mkdir(parents=True)
        runbook.write_text('capture runbook\n')
        git(self.root, 'add', str(runbook))
        write_overlay(self.root, '## Roles\ncapture: tier=execute, runbook=.agents/delegation/runbooks/capture.md, max-uses=3\n')
        conflict = self.open('x', '--role', 'capture', '--kind', 'other')
        self.assertEqual(conflict.returncode, 2)
        self.assertIn('drop --kind', conflict.stderr)
        self.cycle('a', '--role', 'capture')
        self.cycle('b', '--continue', 'a')
        item = self.kind('capture')
        self.assertEqual((item['count'], item['role'], item['description']), (2, True, 'work done by the capture role'))

    def test_since_window_and_retention_fold_counts(self):
        self.cycle('a', '--kind', 'triage', '--new-kind', 'triage output')
        self.cycle('u', text=brief_text('mod9'))
        paths = state.Paths(self.root)
        future = datetime.now(timezone.utc) + timedelta(days=patterns.RETENTION_DAYS + 1)
        with state.mutex(paths.state_root):
            preview = patterns.prune(paths.repo, False, future)
            self.assertEqual(preview['entries'], 4)
            self.assertEqual(len(patterns.load_log(paths)), 4)
            patterns.prune(paths.repo, True, future.timestamp())
        self.assertEqual(patterns.load_log(paths), [])
        self.assertEqual(patterns.load_registry(paths)['kinds']['triage']['archived']['count'], 1)
        self.assertEqual(self.kind('triage')['count'], 1)
        self.assertEqual(self.summary(since_days=30)['kinds'][0]['count'], 0)
        self.assertIn('No active kinds (1 declined or idle', run_cli(self.root, 'kinds').stdout)

    def test_scratch_is_named_in_briefs_and_expires(self):
        self.assertEqual(self.open('a').returncode, 0)
        text = run_cli(self.root, 'brief', '--delegation', 'a').stdout
        scratch = Path(json.loads(run_cli(self.root, 'paths', '--json').stdout)['scratch_directory'])
        self.assertIn(str(scratch / 'a'), text)
        self.assertIn('Prefer a short script there', text)
        self.assertTrue(text.endswith('Return cap: 400 words\n'))
        run_cli(self.root, 'close', '--delegation', 'a', '--outcome', 'done')
        helper = scratch / 'a' / 'rename.py'
        helper.parent.mkdir(parents=True)
        helper.write_text('print(1)\n')
        fresh = scratch / 'b.txt'
        fresh.write_text('x')
        old = time.time() - 31 * 86400
        os.utime(helper, (old, old))
        result = state.gc(apply=True)
        self.assertFalse(helper.exists())
        self.assertFalse(helper.parent.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(any(e.get('reason') == 'scratch untouched for 30 days' for e in result['entries']))

    def test_tier_instructions_mention_scratch(self):
        from delegation_check.brief import tier_instructions
        for tier in ('execute', 'routine'):
            self.assertIn('plus its Scratch directory', tier_instructions(tier))
            self.assertIn('throwaway script in Scratch', tier_instructions(tier))


class AuthoringOverlayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        isolate_xdg(self, Path(tmp.name))
        self.root = git_repo(Path(tmp.name) / 'repo')

    def test_defaults_to_allowed(self):
        self.assertEqual(load_overlay(self.root).authoring, {'roles': 'allowed', 'scripts': 'allowed'})
        write_overlay(self.root, '## Return cap\n300\n')
        self.assertEqual(load_overlay(self.root).authoring, {'roles': 'allowed', 'scripts': 'allowed'})

    def test_parses_and_lints(self):
        write_overlay(self.root, '## Authoring\n- scripts: ask\n')
        overlay = load_overlay(self.root)
        self.assertEqual(overlay.problems, ())
        self.assertEqual(overlay.authoring, {'roles': 'allowed', 'scripts': 'ask'})
        self.assertIn('roles=allowed, scripts=ask', run_cli(self.root, 'patterns').stdout)
        write_overlay(self.root, '## Authoring\nroles: always\nagents: allowed\nroles: ask\nroles: ask\n')
        problems = load_overlay(self.root).problems
        self.assertEqual(len(problems), 3)
        self.assertIn('line 2: authoring needs', problems[0])
        self.assertIn('duplicate authoring entry "roles"', problems[2])


if __name__ == '__main__':
    unittest.main()
