import hashlib
import json
from long_horizon_support import RepoTest, GOALS, OVERLAY

# Milestone 2's criterion has no colon and sits after its tasks, so it once attached to task 2.1.
MALFORMED = GOALS.replace('## 2. Integrate\nDone when: observation:review\n- [ ] [2.1] Exercise the whole call. (any)\n',
                          '## 2. Integrate\n- [ ] [2.1] Exercise the whole call. (any)\nDone when observation:review passes\n')
FIXED = GOALS.replace('Done when: observation:review\n', 'Done when: observation:review passes\n')


def codes(output):
    return [x['code'] for x in output['findings']]


class DoneWhenFormatTests(RepoTest):
    def test_colonless_and_trailing_criteria_warn(self):
        self.write('docs/goals.md', MALFORMED)
        output = self.cli('lint')
        self.assertIn('criteria-format', codes(output))
        self.assertIn('missing-criteria', codes(output))
        self.assertTrue(any('task 2.1' in x['message'] for x in output['findings']))
        self.write('docs/goals.md', GOALS.replace('Done when: observation:review\n', ''))
        self.assertIn('missing-criteria', codes(self.cli('lint')))
        self.write('docs/goals.md', GOALS.replace('Done when: observation:review\n- [ ] [2.1] Exercise the whole call. (any)\n',
                                                  '- [ ] [2.1] Exercise the whole call. (any)\nDone when: observation:review\n'))
        self.assertIn('missing-criteria', codes(self.cli('lint')))

    def test_fix_moves_and_adds_colon_without_policy_approval(self):
        self.write('docs/goals.md', MALFORMED)
        self.commit('Malformed criteria')
        diff = self.cli('lint', '--fix')['diff']
        self.assertIn('+Done when: observation:review passes', diff)
        self.cli('lint', '--fix', '--apply')
        self.assertEqual((self.root / 'docs/goals.md').read_text(), FIXED)
        output = self.cli('lint')
        self.assertNotIn('criteria-format', codes(output))
        self.assertNotIn('missing-criteria', codes(output))
        self.assertNotIn('policy-approval', codes(self.cli('gate')))

    def test_whitespace_and_punctuation_are_not_policy_but_words_are(self):
        self.write('docs/goals.md', GOALS.replace('Done when: validator:unit\n- [ ] [1.1]', 'Done when:   validator:unit.\n- [ ] [1.1]'))
        self.assertNotIn('policy-approval', codes(self.cli('gate')))
        self.write('docs/goals.md', GOALS.replace('Done when: validator:unit\n- [ ] [1.1]', 'Done when: validator:unit twice\n- [ ] [1.1]'))
        self.assertIn('policy-approval', codes(self.cli('gate', code=1)))


class PendingAndHandoffStatusTests(RepoTest):
    def test_status_lists_pending_records_and_handoff_budget(self):
        output = self.record(self.prepare())
        status = self.cli('status')
        self.assertEqual([x['id'] for x in status['pending_evidence']], [output['record']['id']])
        unit = next(x for x in status['acceptance'] if x['check'] == 'validator:unit')
        self.assertEqual((unit['status'], unit['pending']), ('fresh', True))
        self.assertEqual((status['handoff']['lines'], status['handoff']['budget']), (3, 80))
        self.assertIn('missing', [x['status'] for x in self.cli('evidence', 'find')['checks']])
        self.carry(output)
        self.assertEqual(self.cli('status')['pending_evidence'], [])

    def test_text_status_prints_budget_and_pending(self):
        import subprocess, sys
        from long_horizon_support import SCRIPT
        self.record(self.prepare())
        text = subprocess.run([sys.executable, str(SCRIPT), 'status', '--root', str(self.root)], env=self.env,
                              capture_output=True, text=True).stdout
        self.assertIn('Handoff: 3/80 lines', text)
        self.assertIn('Pending evidence: validator:unit PASS', text)


class RecordFilesTests(RepoTest):
    def record_args(self, before, *extra):
        return ('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS',
                '--command', 'python -m unittest', '--exit', '0', '--log', 'regenerate:python -m unittest', *extra)

    def test_write_proposed_and_accumulating_trailers(self):
        trailers = self.base / 'trailers.txt'
        first = self.cli(*self.record_args(self.prepare('a'), '--write-proposed', '--trailers-file', str(trailers)))
        detail = self.root / first['record']['detail']
        self.assertEqual(first['written'], [first['record']['detail']])
        self.assertEqual(detail.read_text(), first['proposed_files'][first['record']['detail']])
        again = self.cli(*self.record_args(self.prepare('a'), '--write-proposed', '--trailers-file', str(trailers)))
        self.assertEqual(again['written'], [])
        second = self.cli(*self.record_args(self.prepare('b'), '--trailers-file', str(trailers)))
        self.assertEqual(trailers.read_text().splitlines(), [first['trailer'], second['trailer']])
        detail.write_text('{}\n')
        self.cli(*self.record_args(self.prepare('a'), '--write-proposed'), code=2)


class ClosureManifestTests(RepoTest):
    def test_manifest_command_matches_validate_and_commit(self):
        self.write('.agents/long-horizon.md', OVERLAY + '\n## Integration\nsteps: ["validate", "commit"]\nauthorization: "Fixture authorizes local commits."\n')
        base = self.commit('Authorize closure')
        stale = self.record(self.prepare('old'), 'FAIL')
        self.write('tiny.py', 'def tiny():\n    return 2\n')
        output = self.record(self.prepare())
        for path, content in output['proposed_files'].items():
            self.write(path, content)
        self.cli('closure', 'manifest', '--base', base, '--output', str(self.root / 'm.json'), code=2)
        built = self.cli('closure', 'manifest', '--base', base)
        self.assertEqual(built['manifest']['evidence_ids'], [output['record']['id']])
        self.assertEqual(built['unused_pending'], [stale['record']['id']])
        paths = {x['path']: x['digest'] for x in built['manifest']['paths']}
        self.assertEqual(set(paths), {'tiny.py', output['record']['detail']})
        self.assertEqual(paths['tiny.py'], hashlib.sha256(b'def tiny():\n    return 2\n').hexdigest())
        self.cli('closure', 'record', '--batch', built['batch'], '--step', 'validate', '--outcome', 'success', '--manifest', built['path'])
        commit = self.commit('Batch\n\n' + output['trailer'])
        self.cli('closure', 'record', '--batch', built['batch'], '--step', 'commit', '--outcome', 'success', '--commit', commit)
        self.assertEqual(self.cli('closure', 'verify')['state'], 'complete')
        only = self.cli('closure', 'manifest', '--base', commit, '--path', 'tiny.py', '--pending', output['record']['id'], code=2)
        self.assertIn('No changed paths', only['findings'][0]['message'])


class RerecordTests(RepoTest):
    def test_rerecord_after_criteria_change_replaces_pending_proposal(self):
        trailers = self.base / 'trailers.txt'
        old = self.cli('evidence', 'record', 'validator:unit', '--snapshot', self.prepare()['id'], '--outcome', 'PASS',
                       '--command', 'python -m unittest', '--exit', '0', '--log', 'regenerate:python -m unittest',
                       '--write-proposed', '--trailers-file', str(trailers))
        old_id = old['record']['id']
        self.cli('evidence', 'rerecord', old_id, code=2)  # nothing changed yet
        self.write('docs/goals.md', GOALS.replace('Done when: validator:unit\n- [ ] [1.1]', 'Done when: validator:unit on all fixtures\n- [ ] [1.1]'))
        self.assertEqual(self.cli('evidence', 'find', '--pending', old_id)['checks'][0]['status'], 'stale')
        new = self.cli('evidence', 'rerecord', old_id, '--write-proposed', '--trailers-file', str(trailers))
        new_id = new['record']['id']
        self.assertNotEqual(new_id, old_id)
        self.assertEqual(new['record']['rerecorded_from'], old_id)
        self.assertEqual(new['superseded'], {'id': old_id, 'committed': False, 'removed': [old['record']['detail']]})
        self.assertFalse((self.root / old['record']['detail']).exists())
        self.assertTrue((self.root / new['record']['detail']).exists())
        self.assertEqual(trailers.read_text().splitlines(), [new['trailer']])
        self.assertEqual(self.cli('evidence', 'find', '--pending', new_id)['checks'][0]['status'], 'fresh')
        self.assertEqual([x['id'] for x in self.cli('status')['pending_evidence']], [new_id])

    def test_rerecord_refuses_changed_scope_or_definition(self):
        output = self.record(self.prepare())
        self.carry(output)
        self.write('docs/goals.md', GOALS.replace('Done when: validator:unit\n- [ ] [1.1]', 'Done when: validator:unit, reworded\n- [ ] [1.1]'))
        self.write('tiny.py', 'changed\n')
        self.cli('evidence', 'rerecord', output['record']['id'], code=2)
        self.write('tiny.py', 'def tiny():\n    return 1\n')
        self.write('.agents/long-horizon.md', OVERLAY.replace('"unit-v1"', '"unit-v2"'))
        self.cli('evidence', 'rerecord', output['record']['id'], code=2)
        self.write('.agents/long-horizon.md', OVERLAY)
        new = self.cli('evidence', 'rerecord', output['record']['id'])
        self.assertEqual(new['superseded'], {'id': output['record']['id'], 'committed': True, 'removed': []})
        self.assertTrue((self.root / output['record']['detail']).exists())


class ReviewerKindTests(RepoTest):
    def review(self, kind, code=0):
        before = self.prepare(check='observation:review')
        self.write('docs/evidence/review.md', 'Reviewed the whole calling context, 2026-10-12.\n')
        args = ['evidence', 'record', 'observation:review', '--snapshot', before['id'], '--outcome', 'PASS',
                '--reviewer', 'reviewer', '--review-note', 'docs/evidence/review.md', '--log', 'docs/evidence/review.md']
        return self.cli(*args + (['--reviewer-kind', kind] if kind else []), code=code)

    def test_human_by_default_agent_only_when_allowed(self):
        self.review(None, code=2)
        self.review('agent', code=2)
        self.assertEqual(self.review('human')['record']['reviewer_kind'], 'human')
        self.write('.agents/long-horizon.md', OVERLAY.replace('"observation:review": {"domain": "review-v1"}',
                                                              '"observation:review": {"domain": "review-v1", "reviewer": "any"}'))
        self.assertEqual(self.review('agent')['record']['reviewer_kind'], 'agent')

    def test_reviewer_policy_only_on_observations(self):
        self.write('.agents/long-horizon.md', OVERLAY.replace('{"domain": "unit-v1"}', '{"domain": "unit-v1", "reviewer": "any"}'))
        self.cli('status', code=2)
