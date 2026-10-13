"""The lanes contract: overlay section, goals metadata, lint findings, lane selection and the judge view."""
import json
from pathlib import Path
import shutil
from unittest.mock import patch
from long_horizon_support import RepoTest, OVERLAY, GOALS, HANDOFF
from long_horizon import overlay, lanes
from long_horizon.model import Invalid

LANES_OVERLAY = OVERLAY + '## Lanes\nconfig: ".agents/lanes.toml"\n'
CONFIG = '''[run]
project = "example"
stop_at = 92

[lanes.core]
owns = ["crates/app-core/**"]
validators = ["core-tests"]
host = "any"

[lanes.ui]
owns = ["crates/app-ui/**"]
validators = ["ui-tests"]

[lanes.native]
owns = ["probes/**"]
host = "native"
'''
LANE_GOALS = '''# Goal: Example — current
ID: ex
Parallel: lanes, user, 2026-10-13
Done when: validator:unit
## 1. Build — current
Done when: validator:unit
- [ ] [1.1] Core parser. (any)
  Lane: core
- [ ] [1.2] UI wiring. (any)
  Lane: ui
  After: 1.1
- [x] [1.3] Scaffold. (any)
  Lane: ui
## 2. Polish
Done when: observation:review
- [ ] [2.1] Polish UI. (any)
  Lane: ui
  After: 1.2
- [ ] [2.2] Capture frames. (native)
  Lane: native
## Parked
- Later
'''
LANE_HANDOFF = '''# Handoff
Next: 1.1 Core parser.
Lanes: 3 lanes, run run-1
## Blockers
## Pending decisions
## Context
- [core](lanes/core.md)
- [ui](lanes/ui.md)
- [native](lanes/native.md)
'''


class LanesRepo(RepoTest):
    def setUp(self):
        super().setUp()
        self.write('.agents/long-horizon.md', LANES_OVERLAY)
        self.write('.agents/lanes.toml', CONFIG)
        self.write('docs/goals.md', LANE_GOALS)
        self.write('docs/handoff.md', LANE_HANDOFF)
        for name in ('core', 'ui', 'native'):
            self.write('docs/lanes/' + name + '.md', '# Lane ' + name + '\n## Status\n## Next\n## Asks\n')
        self.commit('Adopt lanes')

    def codes(self, *args, code=0):
        return {x['code']: x for x in self.cli(*args, code=code)['findings']}


class OverlayTests(LanesRepo):
    def test_section_keys_defaults_and_mode(self):
        data = overlay.parse(LANES_OVERLAY)
        self.assertEqual(data['lanes'], {'config': '.agents/lanes.toml', 'assignment': 'goals', 'task-completion': 'lane',
                                         'milestone-completion': 'judge', 'landing': 'lander', 'lane-files': 'docs/lanes'})
        self.assertNotIn('config', overlay.parse(OVERLAY)['lanes'])
        self.assertNotIn('config', overlay.parse(OVERLAY + '## Lanes\n<!-- Lanes are off. -->\n')['lanes'])
        for text in ('assignment: "manual"', 'task-completion: "agent"', 'milestone-completion: "lane"', 'landing: "both"', 'config: ""'):
            with self.subTest(text=text), self.assertRaises(Invalid):
                overlay.parse(OVERLAY + '## Lanes\n' + text + '\n')

    def test_without_config_nothing_changes(self):
        self.write('.agents/long-horizon.md', OVERLAY + '## Lanes\n<!-- off -->\n')
        result = self.cli('status')
        self.assertEqual(result['selection']['task']['id'], '1.1')
        self.assertNotIn('lanes', result)
        self.assertFalse({x['code'] for x in result['findings']} & {'lane-missing', 'lane-unknown', 'parallel-approval-missing', 'lane-file-missing'})
        self.cli('status', '--lane', 'core', code=2)

    def test_metadata_parses_but_is_ignored_outside_lanes_mode(self):
        self.write('.agents/long-horizon.md', OVERLAY)
        self.write('docs/goals.md', LANE_GOALS.replace('Lane: core', 'Lane: nowhere').replace('After: 1.1', 'After: 9.9'))
        result = self.cli('lint')
        self.assertEqual(result['selection']['task']['id'], '1.1')
        self.assertFalse({x['code'] for x in result['findings']} & {'lane-unknown', 'after-missing', 'parallel-approval-missing'})
        self.assertFalse(list((self.base / 'cache').rglob('evidence')))


class SelectionTests(LanesRepo):
    def test_lane_selection_walks_milestones_and_after(self):
        core = self.cli('status', '--lane', 'core')
        self.assertEqual((core['selection']['mode'], core['selection']['task']['id'], core['selection']['lane']), ('selected', '1.1', 'core'))
        ui = self.cli('status', '--lane', 'ui')
        self.assertEqual(ui['selection']['mode'], 'all-blocked')
        self.assertEqual([x['task'] for x in ui['selection']['blocked']], ['1.2', '2.1'])
        self.assertIn('Waits for 1.1 (open, lane core).', ui['selection']['blocked'][0]['reasons'])
        self.write('docs/goals.md', LANE_GOALS.replace('- [ ] [1.1]', '- [x] [1.1]'))
        ui = self.cli('status', '--lane', 'ui')
        self.assertEqual((ui['selection']['task']['id'], ui['selection']['milestone']), ('1.2', 'ex:1'))
        self.write('docs/goals.md', LANE_GOALS.replace('- [ ] [1.1]', '- [x] [1.1]').replace('- [ ] [1.2]', '- [x] [1.2]'))
        ui = self.cli('status', '--lane', 'ui')
        self.assertEqual((ui['selection']['task']['id'], ui['selection']['milestone']), ('2.1', 'ex:2'))
        self.assertEqual(self.cli('status', '--lane', 'core')['selection']['mode'], 'lane-done')

    def test_capability_tags_and_handoff_blockers_apply_per_task(self):
        self.write('.agents/long-horizon.md', LANES_OVERLAY + '## Capabilities\ntags: {"any": [], "native": ["native"]}\n## Startup\nreadiness: "cache:readiness.json"\n')
        self.write_readiness('{"version":1,"levels":{"native":{"ready":false,"strength":"exists"}}}')
        native = self.cli('status', '--lane', 'native')
        self.assertEqual(native['selection']['mode'], 'all-blocked')
        self.assertTrue(any('Missing readiness native' in reason for reason in native['selection']['blocked'][0]['reasons']))
        self.write_readiness('{"version":1,"levels":{"native":{"ready":true,"strength":"probed"}}}')
        self.assertEqual(self.cli('status', '--lane', 'native')['selection']['task']['id'], '2.2')
        self.write('docs/handoff.md', LANE_HANDOFF + '- [1.1] Waiting on a decision; recover: ask; 2026-10-13\n'.replace('- [1.1]', '## Blockers\n- [1.1]'))
        self.assertEqual(self.cli('status', '--lane', 'core')['selection']['mode'], 'all-blocked')

    def test_unknown_lane_and_judge_view(self):
        result = self.cli('status', '--lane', 'nope', code=2)
        self.assertIn('core, native, ui', result['findings'][0]['message'])
        judge = self.cli('status')
        self.assertEqual((judge['selection']['mode'], judge['selection']['task']), ('judge', None))
        view = judge['lanes']
        self.assertEqual(view['names'], ['core', 'native', 'ui'])
        self.assertEqual(view['hosts'], {'core': 'any', 'native': 'native', 'ui': 'any'})
        self.assertEqual(view['run'], {'project': 'example', 'stop_at': 92})
        self.assertEqual((view['done'], view['open'], view['eligible']), (['1.3'], ['1.1', '1.2', '2.1', '2.2'], ['1.1']))
        self.assertEqual(view['critical_path'], ['1.1', '1.2', '2.1'])
        self.assertEqual(view['per_lane']['ui'], {'open': ['1.2', '2.1'], 'eligible': [], 'blocked': ['1.2', '2.1'], 'done': ['1.3']})
        self.assertEqual(view['per_lane']['native']['blocked'], ['2.2'])
        self.assertEqual(view['policy']['landing'], 'lander')
        self.assertIn('Lanes: ', self.cli_text('status', '--brief'))

    def test_shared_early_modes(self):
        self.write('.agents/long-horizon.md', LANES_OVERLAY + '## State\nstate: "dormant"\n')
        self.assertEqual(self.cli('status', '--lane', 'core')['selection']['mode'], 'dormant')
        self.write('.agents/long-horizon.md', LANES_OVERLAY)
        done = LANE_GOALS.replace('- [ ]', '- [x]').replace('## 1. Build — current', '## 1. Build — done').replace('## 2. Polish', '## 2. Polish — done')
        self.write('docs/goals.md', done)
        self.assertEqual(self.cli('status', '--lane', 'core')['selection']['mode'], 'awaiting-signoff')
        self.assertEqual(self.cli('status')['selection']['mode'], 'awaiting-signoff')

    def cli_text(self, *args):
        import subprocess
        import sys
        from long_horizon_support import SCRIPT
        result = subprocess.run([sys.executable, str(SCRIPT), *args, '--root', str(self.root)], env=self.env, capture_output=True, text=True, timeout=30)
        return result.stdout


class LintTests(LanesRepo):
    def test_clean_adoption_has_no_lane_findings(self):
        codes = set(self.codes('lint'))
        self.assertFalse({x for x in codes if x.startswith(('lane', 'after-', 'parallel-', 'handoff-lane', 'handoff-lanes', 'mac-'))}, codes)

    def test_lane_missing_unknown_and_unassigned(self):
        self.write('docs/goals.md', LANE_GOALS.replace('  Lane: core\n', '').replace('Lane: native', 'Lane: mac'))
        codes = self.codes('lint', code=1)
        self.assertEqual(codes['lane-missing']['line'], 7)
        self.assertIn('mac', codes['lane-unknown']['message'])
        self.assertIn('core, native, ui', codes['lane-unknown']['remedy'])
        self.write('docs/goals.md', LANE_GOALS.replace('Lane: core', 'Lane: unassigned'))
        codes = self.codes('lint')
        self.assertNotIn('lane-unknown', codes)
        self.assertEqual(self.cli('status')['lanes']['per_lane']['unassigned']['eligible'], ['1.1'])

    def test_done_milestones_and_done_tasks_need_no_lane(self):
        text = LANE_GOALS.replace('- [x] [1.3] Scaffold. (any)\n  Lane: ui\n', '- [x] [1.3] Scaffold. (any)\n')
        self.write('docs/goals.md', text)
        self.assertNotIn('lane-missing', self.codes('lint'))

    def test_after_missing_and_cycle(self):
        self.write('docs/goals.md', LANE_GOALS.replace('After: 1.1', 'After: 1.1, 7.7'))
        codes = self.codes('lint', code=1)
        self.assertIn('7.7', codes['after-missing']['message'])
        self.write('docs/goals.md', LANE_GOALS.replace('  Lane: core\n', '  Lane: core\n  After: 2.1\n'))
        codes = self.codes('lint', code=1)
        self.assertIn('1.1 -> 2.1 -> 1.2 -> 1.1', codes['after-cycle']['message'])
        self.assertEqual(self.cli('status', code=1)['lanes']['critical_path'], [])

    def test_parallel_approval_and_config_changed(self):
        self.write('docs/goals.md', LANE_GOALS.replace('Parallel: lanes, user, 2026-10-13\n', ''))
        self.assertEqual(self.codes('lint', code=1)['parallel-approval-missing']['severity'], 'error')
        self.write('docs/goals.md', LANE_GOALS.replace('Parallel: lanes, user, 2026-10-13', 'Parallel: yes please'))
        self.assertIn('parallel-approval-missing', self.codes('lint', code=1))
        self.write('docs/goals.md', LANE_GOALS)
        self.write('.agents/lanes.toml', CONFIG + '\n[lanes.extra]\n')
        self.assertIn('lanes-config-changed', self.codes('lint', code=1))
        # Any config commit after the commit that recorded the approval needs re-approval, same day or not.
        self.commit('Add a lane')
        self.assertIn('lanes-config-changed', self.codes('lint', code=1))
        self.write('docs/goals.md', LANE_GOALS.replace('user, 2026-10-13', 'user, 2026-10-14'))
        self.assertNotIn('lanes-config-changed', self.codes('lint'))
        self.commit('Re-approve the lane plan')
        self.assertNotIn('lanes-config-changed', self.codes('lint'))

    def test_host_tag_versus_lane_host(self):
        self.write('docs/goals.md', LANE_GOALS.replace('(native)\n  Lane: native', '(native)\n  Lane: core'))
        found = self.codes('lint', code=1)['mac-task-on-non-native-lane']
        self.assertIn('needs host native but lane core runs on any', found['message'])
        self.write('docs/goals.md', LANE_GOALS.replace('(native)\n  Lane: native', '(fixtures)\n  Lane: core'))
        self.assertNotIn('mac-task-on-non-native-lane', self.codes('lint'))

    def test_lane_files_and_handoff_expectations(self):
        (self.root / 'docs/lanes/native.md').unlink()
        self.write('docs/lanes/ui.md', '# Lane ui\n## Status\n')
        self.write('docs/handoff.md', HANDOFF)
        codes = self.codes('lint')
        self.assertTrue(codes['lane-file-missing']['path'].endswith('native.md'))
        self.assertIn('## Next, ## Asks', codes['lane-file-template']['message'])
        self.assertIn('3 lanes', codes['handoff-lanes-line']['message'])
        self.assertIn('handoff-lane-link', codes)
        self.assertTrue(all(codes[x]['severity'] == 'warning' for x in ('lane-file-missing', 'lane-file-template', 'handoff-lanes-line', 'handoff-lane-link')))

    def test_config_missing_invalid_and_fallback_parser(self):
        (self.root / '.agents/lanes.toml').unlink()
        codes = self.codes('status', code=1)
        self.assertIn('lanes-config-missing', codes)
        self.assertEqual(self.cli('status', code=1)['selection']['mode'], 'manual')
        self.write('.agents/lanes.toml', '[run]\nproject = "x"\n')
        self.assertIn('at least one [lanes.<name>]', self.codes('status', code=1)['lanes-config-invalid']['message'])
        self.write('.agents/lanes.toml', '[lanes.core]\nhost = 3\n')
        self.assertIn('host', self.codes('status', code=1)['lanes-config-invalid']['message'])
        self.write('.agents/lanes.toml', '[lanes.core]\nowns = {a = 1}\n')
        self.assertIn('lanes-config-invalid', self.codes('status', code=1))
        self.write('.agents/lanes.toml', CONFIG + '\n[run.extra]\nstarted = 2026-10-01\n')
        # Both readers reject a date: tomllib through normalize, the subset parser at the line.
        message = self.codes('status', code=1)['lanes-config-invalid']['message']
        self.assertTrue('run.extra.started' in message or '2026-10-01' in message, message)
        self.write('.agents/lanes.toml', CONFIG)
        from long_horizon import toml_subset
        with patch.object(toml_subset, 'USING_TOMLLIB', False):
            self.assertEqual(lanes.normalize(toml_subset.load_text(CONFIG))['lanes']['native']['host'], 'native')
        self.assertEqual(lanes.normalize(toml_subset.loads(CONFIG)), lanes.normalize(toml_subset.load_text(CONFIG)))

    def test_scaffold_round_trips(self):
        text = lanes.scaffold({'run': {'project': 'example', 'stop_at': 92},
                               'lanes': [{'name': 'core', 'owns': ['crates/app-core/**'], 'validators': ['core-tests']},
                                         {'name': 'native', 'owns': ['probes/**'], 'host': 'native'}]})
        from long_horizon import toml_subset
        data = toml_subset.loads(text)
        self.assertEqual(data['run'], {'project': 'example', 'stop_at': 92})
        self.assertEqual(lanes.normalize(data)['lanes']['native'], {'host': 'native', 'owns': ['probes/**'], 'validators': []})
        with self.assertRaises(Invalid):
            lanes.scaffold({'lanes': [{'name': 'unassigned'}]})


class EvidenceIndexTests(LanesRepo):
    def test_commit_in_landing_checkout_resolves_everywhere(self):
        landing = self.base / 'landing checkout'
        self.git('worktree', 'add', '-b', 'landing', str(landing))
        before = self.cli('evidence', 'prepare', 'validator:unit', root=landing)['snapshot']
        output = self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS', '--command', 'core-tests',
                          '--exit', '0', '--log', 'regenerate:core-tests at this commit', '--commit-in', str(landing), root=landing)
        committed = output['committed']
        self.assertFalse(output['pending'])
        self.assertFalse(committed['already_committed'])
        self.assertEqual(committed['cleanup']['removed'], [output['record']['id']])
        self.assertEqual(self.git('rev-parse', 'HEAD', root=landing), committed['commit'])
        self.assertEqual(self.git('status', '--porcelain', root=landing), '')
        self.assertIn(output['trailer'], self.git('log', '-1', '--format=%B', root=landing))
        self.assertEqual(self.git('diff', '--name-only', 'HEAD~1', 'HEAD', root=landing), output['record']['detail'])
        self.assertFalse(list((self.base / 'state').rglob('evidence/*.json')))
        self.assertEqual(self.cli('evidence', 'find', 'validator:unit')['checks'][0]['status'], 'missing')
        self.git('merge', '--ff-only', 'landing')
        self.assertEqual(self.cli('evidence', 'find', 'validator:unit')['checks'][0]['status'], 'fresh')
        index = list((self.base / 'cache').rglob('evidence/*.json'))
        self.assertEqual({x.name for x in index}, {committed['commit'] + '.json', 'identity.json'})
        # The index is a cache: removing it changes nothing but speed.
        shutil.rmtree(index[0].parent)
        self.assertEqual(self.cli('evidence', 'find', 'validator:unit')['checks'][0]['status'], 'fresh')

    def test_commit_in_is_idempotent_and_confined(self):
        # Staged, unrelated work in the checkout stays staged and out of the evidence commit.
        self.write('scratch.txt', 'unrelated staged work\n')
        self.git('add', 'scratch.txt')
        before = self.prepare('landing-attempt')
        args = ['evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS', '--command', 'core-tests',
                '--exit', '0', '--log', 'regenerate:core-tests at this commit']
        output = self.cli(*args, '--commit-in', str(self.root))
        self.assertEqual(self.git('diff', '--cached', '--name-only'), 'scratch.txt')
        head = self.git('rev-parse', 'HEAD')
        self.assertEqual(output['committed']['commit'], head)
        # The same attempt prepares the same snapshot, so a retried record is the same record and makes no commit.
        again = self.prepare('landing-attempt')
        self.assertEqual(again['id'], before['id'])
        output = self.cli(*args, '--commit-in', str(self.root))
        self.assertTrue(output['committed']['already_committed'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        other = self.base / 'other repo'
        other.mkdir()
        self.git('init', '-b', 'main', root=other)
        self.cli(*args[:4], self.cli('evidence', 'prepare', 'validator:unit')['snapshot']['id'], *args[5:], '--commit-in', str(other), code=2)

    def test_commit_in_refuses_records_that_need_other_files(self):
        self.write('docs/unit.log', 'passed\n')
        before = self.prepare()
        result = self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS', '--command', 'core-tests',
                          '--exit', '0', '--log', 'docs/unit.log', '--commit-in', str(self.root), code=2)
        self.assertIn('persistent --log route', result['findings'][0]['message'])
        self.assertEqual(self.git('log', '--oneline').count('\n'), 1)
        self.assertNotIn('evidence-corrupt', self.codes('lint'))

    def test_index_entry_is_tampered_or_stale_safe(self):
        output = self.record(self.prepare())
        commit = self.carry(output)
        self.assertEqual(self.cli('evidence', 'find', 'validator:unit')['checks'][0]['status'], 'fresh')
        entry = next(x for x in (self.base / 'cache').rglob('evidence/*.json') if x.stem == commit)
        value = json.loads(entry.read_text())
        value['commit'] = 'f' * 40
        entry.write_text(json.dumps(value))
        self.assertEqual(self.cli('evidence', 'find', 'validator:unit')['checks'][0]['status'], 'fresh')
        self.assertEqual(json.loads(entry.read_text())['commit'], commit)

    def test_gc_prunes_entries_for_vanished_commits_and_missing_repositories(self):
        output = self.record(self.prepare())
        commit = self.carry(output)
        self.cli('evidence', 'find', 'validator:unit')
        folder = next((self.base / 'cache').rglob('evidence'))
        (folder / ('0' * 40 + '.json')).write_text(json.dumps({'version': 1, 'commit': '0' * 40, 'common': str(self.root / '.git'), 'records': [], 'corrupt': 0}))
        result = self.cli('state', 'gc', '--apply')
        actions = {Path(x['path']).name: x['action'] for x in result['entries']}
        self.assertEqual(actions.get('0' * 40 + '.json'), 'remove')
        self.assertTrue((folder / (commit + '.json')).is_file())
        from long_horizon import state
        with patch.dict('os.environ', self.env):
            state.gc(apply=True, location_root=str(self.root))
            identity = json.loads((folder / 'identity.json').read_text())
            self.assertIsNone(identity['missing_since'])
            shutil.rmtree(self.root)
            state.gc(apply=True, now=1e10)
            self.assertIsNotNone(json.loads((folder / 'identity.json').read_text())['missing_since'])
            state.gc(apply=True, now=1e10 + 8 * 86400)
            self.assertFalse(folder.exists())


class UnchangedWithoutLanesTests(RepoTest):
    """Repositories without a lanes config keep their behaviour."""

    def test_wrapped_criteria_keep_lines_that_look_like_lane_keys(self):
        self.write('docs/goals.md', GOALS.replace('## 1. Build — current\nDone when: validator:unit\n',
                   '## 1. Build — current\nDone when: validator:unit passes;\nAfter: that, observation:review signs it off.\n'))
        from long_horizon import goals, overlay
        parsed = goals.parse((self.root / 'docs/goals.md').read_text(), overlay.DEFAULTS)
        milestone = parsed['goals'][0]['children'][0]
        self.assertEqual(milestone['checks'], ['observation:review', 'validator:unit'])
        self.assertEqual(milestone['after'], [])

    def test_repeated_trailer_without_details_is_not_corrupt(self):
        output = self.record(self.prepare())
        self.carry(output)
        shutil.rmtree(self.root / 'docs/evidence')
        self.commit('Repeat the trailer without its detail file\n\n' + output['trailer'])
        result = self.cli('evidence', 'find', 'validator:unit')
        self.assertNotIn('evidence-corrupt', [x['code'] for x in result['findings']])
        self.assertEqual(result['checks'][0]['status'], 'fresh')
        self.assertFalse(list((self.base / 'cache').rglob('evidence')))

    def test_signature_display_does_not_reach_history_parsing(self):
        self.git('config', 'log.showSignature', 'true')
        output = self.record(self.prepare())
        commit = self.carry(output)
        result = self.cli('evidence', 'find', 'validator:unit')
        self.assertEqual(result['checks'][0]['record']['carrying_commit'], commit)
