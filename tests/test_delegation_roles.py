from delegation_support import isolate_xdg, state_payload
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from delegation_support import git, git_repo, run_cli, write_overlay
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

    def source_role(self, path='.agents/delegation/runbooks/capture.md'):
        source = self.root / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('tracked runbook\n')
        git(self.root, 'add', path)
        write_overlay(self.root, f'## Roles\ncapture: tier=execute, runbook={path}, max-uses=2\n')
        return source

    def test_source_materializes_shares_and_refreshes_after_all_pins_close(self):
        source = self.source_role()
        self.assertEqual(self.open('a').returncode, 0)
        event = read_events(self.root)[0]
        target = state_payload(self.root) / event['role_runbook'][6:]
        self.assertEqual(target.read_text(), 'tracked runbook\n')
        self.assertEqual(self.open('b').returncode, 0)
        self.close('a')
        source.write_text('refreshed source\n')
        before = target.read_bytes()
        result = self.open('c')
        self.assertEqual(result.returncode, 2)
        self.assertIn('pinned', result.stderr)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(run_cli(self.root, 'brief', '--delegation', 'b').returncode, 0)
        self.close('b')
        self.assertEqual(self.open('fresh').returncode, 0)
        self.assertEqual(target.read_text(), 'refreshed source\n')
        text = run_cli(self.root, 'brief', '--delegation', 'fresh').stdout
        self.assertIn(str(source), text)

    def test_nonrole_context_pin_prevents_source_overwrite(self):
        source = self.source_role()
        self.assertEqual(self.open('seed').returncode, 0)
        ref = read_events(self.root)[0]['role_runbook']
        self.close('seed')
        self.brief.write_text('Read ' + ref + '\n')
        self.assertEqual(self.open('plain', role=None).returncode, 0)
        source.write_text('updated\n')
        result = self.open('role')
        self.assertEqual(result.returncode, 2)
        self.assertIn('pinned', result.stderr)

    def test_alias_nonrole_context_pin_prevents_overwrite(self):
        source = self.source_role()
        self.assertEqual(self.open('seed').returncode, 0)
        self.close('seed')
        self.brief.write_text('Read state:context/./.agents/delegation/runbooks/capture.md\n')
        self.assertEqual(self.open('plain', role=None).returncode, 0)
        source.write_text('updated\n')
        self.assertEqual(self.open('role').returncode, 2)
        self.assertEqual(run_cli(self.root, 'brief', '--delegation', 'plain').returncode, 0)

    def test_tree_extra_context_digest_reflects_new_materialization(self):
        self.source_role()
        with (self.root / '.agents/delegation.md').open('a') as handle:
            handle.write('## Extra inputs\nstate:context/.agents/delegation/runbooks/\n')
        self.assertEqual(self.open('a').returncode, 0)
        self.assertEqual(read_events(self.root)[0]['tree'], run_cli(self.root, 'tree').stdout.strip())

    def test_role_brief_alias_reads_first_materialization(self):
        self.source_role()
        self.brief.write_text('Read state:context/./.agents/delegation/runbooks/capture.md\n')
        result = self.open('first')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_cli(self.root, 'brief', '--delegation', 'first').returncode, 0)

    def test_role_brief_alias_reads_refreshed_materialization(self):
        source = self.source_role()
        self.assertEqual(self.open('seed').returncode, 0)
        self.close('seed')
        source.write_text('refreshed runbook\n')
        self.brief.write_text('Read state:context/./.agents/delegation/runbooks/capture.md\n')
        result = self.open('fresh')
        self.assertEqual(result.returncode, 0, result.stderr)
        loaded = run_cli(self.root, 'brief', '--delegation', 'fresh')
        self.assertEqual(loaded.returncode, 0, loaded.stderr)

    def test_context_symlink_pin_prevents_source_overwrite(self):
        source = self.source_role()
        self.assertEqual(self.open('seed').returncode, 0)
        target = state_payload(self.root) / read_events(self.root)[0]['role_runbook'][6:]
        self.close('seed')
        (state_payload(self.root) / 'context/alias.md').symlink_to(target)
        self.brief.write_text('Read state:context/alias.md\n')
        self.assertEqual(self.open('plain', role=None).returncode, 0)
        source.write_text('changed source\n')
        result = self.open('role')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(run_cli(self.root, 'brief', '--delegation', 'plain').returncode, 0)

    def test_role_brief_symlink_reads_first_and_refreshed_materialization(self):
        source = self.source_role()
        target = state_payload(self.root) / 'context/.agents/delegation/runbooks/capture.md'
        (state_payload(self.root) / 'context/alias.md').symlink_to(target)
        self.brief.write_text('Read state:context/alias.md\n')
        for name in ('first', 'fresh'):
            result = self.open(name)
            self.assertEqual(result.returncode, 0, result.stderr)
            loaded = run_cli(self.root, 'brief', '--delegation', name)
            self.assertEqual(loaded.returncode, 0, loaded.stderr)
            self.close(name)
            source.write_text('refreshed source\n')

    def test_materialization_refuses_symlink_destination(self):
        self.source_role()
        target = state_payload(self.root) / 'context/.agents/delegation/runbooks/capture.md'
        target.parent.mkdir(parents=True)
        target.symlink_to(self.context)
        before = self.context.read_bytes()
        result = self.open('role')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(self.context.read_bytes(), before)

    def test_source_must_be_tracked_contained_and_safe_on_windows(self):
        source = self.source_role()
        git(self.root, 'reset', '--', str(source))
        self.assertEqual(self.open('untracked').returncode, 2)
        git(self.root, 'add', str(source))
        source.unlink()
        outside = self.root.parent / 'outside.md'
        outside.write_text('outside')
        source.symlink_to(outside)
        self.assertEqual(self.open('symlink').returncode, 2)
        for path in ('../x.md', r'..\x.md', r'C:\x.md', r'C:x.md', '/x.md'):
            write_overlay(self.root, f'## Roles\ncapture: tier=execute, runbook={path}, max-uses=2\n')
            self.assertEqual(run_cli(self.root, 'lint').returncode, 1, path)

    def test_tracked_symlink_cannot_load_untracked_target(self):
        source = self.source_role()
        source.unlink()
        target = self.root / 'untracked.md'
        target.write_text('untracked secret')
        source.symlink_to(target)
        git(self.root, 'add', str(source))
        result = self.open('a')
        self.assertEqual(result.returncode, 2)

    def test_literal_source_name_cannot_match_other_tracked_files(self):
        self.source_role()
        source = self.root / '.agents/delegation/runbooks/capt*.md'
        source.write_text('untracked')
        write_overlay(self.root, '## Roles\ncapture: tier=execute, runbook=.agents/delegation/runbooks/capt*.md, max-uses=2\n')
        self.assertEqual(self.open('a').returncode, 2)

    def test_layout_warnings_do_not_block_and_ignore_interpreter_arguments(self):
        self.source_role('docs/capture.md')
        with (self.root / '.agents/delegation.md').open('a') as handle:
            handle.write('## Rote scripts\nlocal: python3 ".agents/delegation/scripts/a b.py" --output docs/result.md; approved\ngeneral: python3 "tools/a b.py" --flag; general tool\n')
        result = run_cli(self.root, 'lint')
        self.assertEqual(result.returncode, 0)
        self.assertIn('warning:', result.stdout)
        self.assertIn('docs/capture.md', result.stdout)
        self.assertIn('tools/a b.py', result.stdout)
        self.assertNotIn('docs/result.md', result.stdout)
        self.assertEqual(self.open('a').returncode, 0)

    def test_rote_warning_detects_uv_and_bare_scripts_without_dot_prefix_false_positive(self):
        write_overlay(self.root, '## Rote scripts\nbare: python3 capture.py; approved\nuv: uv run --script "tools/a b.py" --flag; approved\nlocal: python3 "./.agents/delegation/scripts/a b.py"; approved\n')
        result = run_cli(self.root, 'lint')
        self.assertEqual(result.returncode, 0)
        self.assertIn('capture.py', result.stdout)
        self.assertIn('tools/a b.py', result.stdout)
        self.assertNotIn('./.agents/delegation/scripts/a b.py', result.stdout)

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
