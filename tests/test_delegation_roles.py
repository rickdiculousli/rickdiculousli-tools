from delegation_support import isolate_xdg, state_payload
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from delegation_support import git_repo, run_cli, write_overlay
from delegation_check.ledger import read_events
from delegation_check.overlay import load_overlay


class RoleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        isolate_xdg(self, Path(tmp.name))
        self.root = git_repo(Path(tmp.name) / 'repo')
        self.context = state_payload(self.root) / 'context/capture.md'
        self.context.parent.mkdir(parents=True)
        self.context.write_text('capture runbook\n')
        self.brief = state_payload(self.root) / 'briefs/a.md'
        self.brief.parent.mkdir()
        self.brief.write_text('Goal: capture\n')
        self.overlay()

    def overlay(self, caps='max-uses=2'):
        write_overlay(self.root, f'''## Roles
capture: tier=execute, runbook=state:context/capture.md, {caps}
## Rote scripts
capture: python scripts/capture.py; replaces launch, verify, import, index
## Host side effects
~/Library/Application Support/settings.nogg
## Tier hints
execute [needs-human]: native launch may prompt
## Validators
ok [needs-human]: echo ok
## Locks
games: slots=6, wait=2
''')

    def open(self, name, prior=None, role='capture', tier='execute'):
        args = ['open', '--delegation', name, '--tier', tier, '--brief', str(self.brief)]
        if role:
            args += ['--role', role]
        if prior:
            args += ['--continue', prior]
        return run_cli(self.root, *args)

    def close(self, name):
        self.assertEqual(run_cli(self.root, 'close', '--delegation', name, '--outcome', 'done').returncode, 0)

    def test_optional_sections_and_safety_footer(self):
        self.assertEqual(run_cli(self.root, 'lint').returncode, 0)
        self.assertTrue(load_overlay(self.root).validators['ok'].needs_human)
        self.assertEqual(self.open('a').returncode, 0)
        text = run_cli(self.root, 'brief', '--delegation', 'a').stdout
        for expected in ['Do not commit unless the brief says so', 'No first person in committed files.',
                         'Never write these', '~/Library/Application Support/settings.nogg',
                         'needs-human', 'state:context/capture.md', 'validator=null',
                         'registered validator']:
            self.assertIn(expected, text)
        self.context.write_text('changed')
        self.assertEqual(run_cli(self.root, 'brief', '--delegation', 'a').returncode, 2)

    def test_defaults_apply_without_overlay_and_role_runbook_is_recorded(self):
        (self.root / '.agents/delegation.md').unlink()
        self.assertEqual(self.open('plain', role=None).returncode, 0)
        text = run_cli(self.root, 'brief', '--delegation', 'plain').stdout
        self.assertIn('Do not commit unless the brief says so.', text)
        self.assertIn('No first person in committed files.', text)
        self.close('plain')
        self.overlay()
        self.assertEqual(self.open('a').returncode, 0)
        # Overlay edits cannot silently change the recorded role runbook.
        write_overlay(self.root, '## Roles\n')
        r = run_cli(self.root, 'brief', '--delegation', 'a')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('state:context/capture.md', r.stdout)

    def test_reuse_preserves_writer_and_parallel_rules(self):
        self.assertEqual(self.open('a').returncode, 0)
        self.close('a')
        self.assertEqual(self.open('reader', role=None).returncode, 0)
        r = run_cli(self.root, 'open', '--delegation', 'writer', '--tier', 'execute',
                    '--brief', str(self.brief), '--continue', 'a', '--writes')
        self.assertEqual(r.returncode, 2)
        self.assertIn('writer needs the worktree', r.stderr)

    def test_role_requires_present_contained_runbook(self):
        self.context.unlink()
        self.assertEqual(self.open('a').returncode, 2)
        outside = self.root.parent / 'external.md'
        outside.write_text('external')
        self.context.symlink_to(outside)
        self.assertEqual(self.open('a').returncode, 2)

    def test_continue_hashes_brief_links_chain_and_enforces_count(self):
        self.assertEqual(self.open('a').returncode, 0)
        self.close('a')
        self.brief.write_text('Goal: another capture\n')
        r = self.open('b', 'a', role=None)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('follow-up:', r.stdout)
        self.assertIn('SendMessage', r.stdout)
        self.assertIn('followup_task', r.stdout)
        b = [e for e in read_events(self.root) if e['delegation'] == 'b'][0]
        self.assertEqual((b['continued_from'], b['agent_session'], b['role'], b['uses']), ('a', 'a', 'capture', 2))
        self.assertEqual(b['brief_sha256'], hashlib.sha256(self.brief.read_bytes()).hexdigest())
        self.close('b')
        # An old ancestor cannot fork the same agent's reuse counter.
        r = self.open('c', 'a', role=None)
        self.assertEqual(r.returncode, 2)
        self.assertIn('refresh', r.stderr)
        self.assertIn('fresh agent', r.stderr)

    def test_continue_refuses_open_missing_and_changed_tier(self):
        self.assertEqual(self.open('a').returncode, 0)
        self.assertEqual(self.open('b', 'a', role=None).returncode, 2)
        self.close('a')
        self.assertEqual(self.open('b', 'missing', role=None).returncode, 2)
        self.assertEqual(self.open('b', 'a', role=None, tier='routine').returncode, 2)
        self.assertEqual(self.open('b', role='missing').returncode, 2)

    def test_context_byte_cap_and_fresh_start(self):
        size = len(self.brief.read_bytes()) + len(self.context.read_bytes())
        self.overlay(f'max-context-bytes={size}')
        self.assertEqual(self.open('a').returncode, 0)
        self.close('a')
        self.assertEqual(self.open('b', 'a', role=None).returncode, 2)
        self.assertEqual(self.open('fresh').returncode, 0)

    def test_lint_rejects_bad_roles_and_rote_scripts(self):
        cases = ['capture: tier=wrong, runbook=state:context/a.md, max-uses=2',
                 'capture: tier=execute, runbook=../a.md, max-uses=2',
                 'capture: tier=execute, runbook=state:context/a.md',
                 'capture: tier=execute, runbook=state:context/a.md, max-uses=0',
                 'capture: tier=execute, tier=routine, runbook=state:context/a.md, max-uses=2',
                 'capture: tier=execute, runbook=state:context/a.md, max-uses=²',
                 'capture: tier=execute, runbook=state:context/a.md, max-context-bytes=nan']
        for row in cases:
            with self.subTest(row=row):
                write_overlay(self.root, '## Roles\n' + row + '\n')
                result = run_cli(self.root, 'lint')
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, '')
                self.assertIn('line 2:', result.stdout)
        write_overlay(self.root, '## Rote scripts\ncapture\n')
        self.assertEqual(run_cli(self.root, 'lint').returncode, 1)

    def test_needs_human_tier_only_and_invalid_validator_marker(self):
        write_overlay(self.root, '## Tier hints\nexecute [needs-human]: game prompt\n')
        self.assertEqual(self.open('plain', role=None).returncode, 0)
        text = run_cli(self.root, 'brief', '--delegation', 'plain').stdout
        self.assertIn('execute [needs-human]: game prompt', text)
        self.assertIn('early while the user is present', text)
        for attributes in ('needs-human=yes', 'needs-human, needs-human'):
            write_overlay(self.root, f'## Validators\nok [{attributes}]: true\n')
            self.assertEqual(run_cli(self.root, 'lint').returncode, 1)

    def test_exec_caller_evidence_is_not_validator_evidence(self):
        self.assertEqual(self.open('caller').returncode, 0)
        r = run_cli(self.root, 'exec', '--lock', 'games', '--timeout', '2', '--delegation', 'caller',
                    '--', sys.executable, '-c', "print('capture')")
        self.assertEqual(r.returncode, 0, r.stderr)
        events = [e for e in read_events(self.root) if e['event'] == 'result']
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]['validator'])
        self.assertEqual(events[0]['delegation'], 'caller')
        self.assertEqual(events[0]['lock'], 'games')
        self.assertEqual((state_payload(self.root) / events[0]['log']).read_text(), 'capture\n')
        run_cli(self.root, 'run', 'ok', '--delegation', 'caller')
        q = json.loads(run_cli(self.root, 'query', '--delegation', 'caller', '--json').stdout)
        self.assertEqual([e['id'] for e in q['results']], ['caller#1', 'caller#2'])
        self.close('caller')
        r = run_cli(self.root, 'exec', '--lock', 'games', '--timeout', '2', '--delegation', 'caller', '--', 'true')
        self.assertEqual(r.returncode, 2)

    def test_exec_failure_timeout_and_unattributed_compatibility(self):
        self.assertEqual(self.open('caller').returncode, 0)
        for args, expected in [(['sh', '-c', 'exit 7'], 7),
                               ([sys.executable, '-c', 'import time; time.sleep(1)'], 124)]:
            r = run_cli(self.root, 'exec', '--lock', 'games', '--timeout', '0.1', '--delegation', 'caller', '--', *args)
            self.assertEqual(r.returncode, expected)
        results = [e for e in read_events(self.root) if e['event'] == 'result']
        self.assertFalse(results[0]['ok'])
        self.assertTrue(results[1]['timed_out'])
        r = run_cli(self.root, 'exec', '--lock', 'games', '--timeout', '2', '--', 'true')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len([e for e in read_events(self.root) if e['event'] == 'result']), 2)
