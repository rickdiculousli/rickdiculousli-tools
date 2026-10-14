"""Closing a long goal: early warnings, the sign-off pre-check, archive prepare and legacy acceptance.

The fixture has the shape of a real goal closed under 0.6.1: two milestones closed before Checks
existed (prose and commit citations), one proved by a recorded check cited as `3.1=<id>`, one
whose Checks were added after its only run (prose proof), and a goal with no criteria of its own
until sign-off. Names are invented.
"""
import json
from pathlib import Path
import re
from long_horizon_support import RepoTest

MILESTONES = '''
## 1. Oracles — done
Done when: every ported helper reproduces its cached fixture.

- [x] [1.1] Port the helpers. (any)
      Evidence: 1.1={base}

## 2. Traces — done
Done when: the reader replays the whole corpus.

- [x] [2.1] Write the reader. (any)
      Evidence: 2.1={base}
'''
SPEC = '''
## 3. Spec{s3}
Done when: validator:unit passes on the spec.

- [{x3}] [3.1] Write the spec. (any){e3}
'''
AUDIO = '''
## 4. Audio{s4}
Done when: live audio matches the capture.{k4}

- [{x4}] [4.1] Match the capture. (any){e4}
'''
FRONTEND = '''
## 5. Frontend{s5}
Done when: the user has reviewed the running app.
Checks: ["observation:review"]

- [{x5}] [5.1] Review the app. (any){e5}
'''
GOAL_CRITERIA = ('Done when: every milestone is done and the user accepted the running app.\n'
                 'Checks: ["observation:review"]\n'
                 'Policy-Approval: user approved the goal\'s Done when and Checks at sign-off, 2026-10-13\n')


class CompletionTests(RepoTest):
    def goals(self, head='— current', top='', spec=('', ' ', ''), audio=('', ' ', '', ''), frontend=('', ' ', '')):
        text = '# Goal: Engine rewrite ' + head + '\nID: engine-rewrite\n' + top
        text += MILESTONES.format(base=self.base_commit)
        text += SPEC.format(s3=spec[0], x3=spec[1], e3=spec[2])
        text += AUDIO.format(s4=audio[0], x4=audio[1], e4=audio[2], k4=audio[3])
        text += FRONTEND.format(s5=frontend[0], x5=frontend[1], e5=frontend[2])
        self.write('docs/goals.md', text)

    def evidence(self, task, id_):
        return '\n      Evidence: ' + task + '=' + id_

    def build_history(self):
        """Milestones 1-4 done the way the real goal closed them; 5 open with its review pending."""
        self.base_commit = self.git('rev-parse', 'HEAD')
        self.goals(spec=(' — current', ' ', ''))
        self.commit('Roadmap with pre-Checks milestones')
        unit = self.record(self.prepare())
        self.carry(unit)
        self.unit = unit['record']['id']
        self.goals(spec=(' — done', 'x', self.evidence('3.1', self.unit)), audio=(' — current', ' ', '', ''))
        self.commit('Close milestone 3 on its recorded check')
        # Checks arrive after the only run: milestone 4's proof stays prose.
        checks = '\nChecks: ["validator:unit"]\nPolicy-Approval: user added Checks, 2026-10-12'
        self.goals(spec=(' — done', 'x', self.evidence('3.1', self.unit)),
                   audio=(' — done', 'x', self.evidence('4.1', self.base_commit), checks),
                   frontend=(' — current', ' ', ''))
        self.commit('Close milestone 4 on prose acceptance')
        self.checks4 = checks

    def close_frontend(self):
        before = self.prepare(check='observation:review')
        review = self.cli('evidence', 'record', 'observation:review', '--snapshot', before['id'], '--outcome', 'PASS',
                          '--reviewer', 'user', '--reviewer-kind', 'human', '--review-text', 'Played it against the original; parity accepted.',
                          '--write-proposed')
        self.review = review['record']['id']
        self.goals(spec=(' — done', 'x', self.evidence('3.1', self.unit)),
                   audio=(' — done', 'x', self.evidence('4.1', self.base_commit), self.checks4),
                   frontend=(' — done', 'x', self.evidence('5.1', self.review)))
        return self.commit('Close milestone 5\n\n' + review['trailer'])

    def codes(self, data):
        return [x['code'] for x in data['findings']]

    def test_status_and_lint_warn_as_soon_as_a_goal_would_stall(self):
        self.build_history()
        status = self.cli('status')
        warned = [x for x in status['findings'] if x['code'] == 'milestone-proof-missing']
        self.assertEqual([re.search(r'engine-rewrite:\d', x['message'])[0] for x in warned],
                         ['engine-rewrite:1', 'engine-rewrite:2', 'engine-rewrite:4'])
        self.assertTrue(all(x['severity'] == 'warning' for x in warned))
        self.assertIn('goal-criteria-missing', self.codes(status))
        self.assertTrue(status['ok'])
        self.assertIn('goal-criteria-missing', self.codes(self.cli('lint')))
        self.assertNotIn('signoff', status)

    def test_awaiting_signoff_lists_every_gap_and_approval_once(self):
        self.build_history()
        self.close_frontend()
        status = self.cli('status')
        self.assertEqual(status['selection']['mode'], 'awaiting-signoff')
        signoff = status['signoff']
        self.assertEqual([x['kind'] for x in signoff['approvals']], ['goal-criteria', 'legacy-acceptance', 'signoff'])
        legacy = signoff['approvals'][1]
        self.assertEqual(sorted(legacy['milestones']), ['engine-rewrite:1', 'engine-rewrite:2', 'engine-rewrite:4'])
        self.assertTrue(all(x['reserved'] for x in signoff['approvals'][1:]))
        criteria = signoff['approvals'][0]['proposal']
        self.assertTrue(criteria[0].startswith('Done when: <fill:') and criteria[2].startswith('Policy-Approval:'))
        self.assertIn('archive-unwritten', [x['code'] for x in signoff['gaps']])
        asks = [x for x in status['needs_you'] if x.startswith('sign off the completed goal')]
        self.assertEqual(len(asks), 1)
        self.assertIn('Done when/Checks', asks[0])
        self.assertIn('engine-rewrite:1, engine-rewrite:2, engine-rewrite:4', asks[0])
        self.assertIn('signoff-precheck', self.codes(status))

    def test_prepare_signoff_and_gate_with_legacy_acceptance(self):
        self.build_history()
        signoff_base = self.close_frontend()
        prepared = self.cli('archive', 'prepare', '--write')
        path = prepared['path']
        self.assertTrue(re.fullmatch(r'docs/goals-archive/\d{4}-\d{2}-\d{2}-engine-rewrite\.md', path), path)
        self.assertTrue(prepared['written'])
        value = prepared['value']
        by_id = {x['id']: x for x in value['milestones']}
        self.assertIn(self.unit, by_id['engine-rewrite:3']['evidence'])
        self.assertIn(self.review, by_id['engine-rewrite:5']['evidence'])
        self.assertEqual(by_id['engine-rewrite:1']['evidence'], ['1.1=' + self.base_commit])
        self.assertEqual(value['legacy_acceptance']['milestones'], ['engine-rewrite:1', 'engine-rewrite:2', 'engine-rewrite:4'])
        self.assertIn('archive-pointer', [x['code'] for x in prepared['gaps']])
        self.assertEqual(prepared['goal_lines'], ['Archive: ' + path])
        # The user answers once: sign-off, goal criteria and legacy acceptance together.
        self.goals(head='— done', top='Signed-off: user, 2026-10-13\nArchive: ' + path + '\n' + GOAL_CRITERIA,
                   spec=(' — done', 'x', self.evidence('3.1', self.unit)),
                   audio=(' — done', 'x', self.evidence('4.1', self.base_commit), self.checks4),
                   frontend=(' — done', 'x', self.evidence('5.1', self.review)))
        rerecorded = self.cli('evidence', 'rerecord', self.review, '--write-proposed')['record']['id']
        archive = self.root / path
        text = archive.read_text()
        for slot, answer in [('"<fill: one line on what the goal delivered>"', '"Rewrite accepted"'),
                             ('"<fill: who signed off, after they actually did>"', '"user"'),
                             ('"<fill: YYYY-MM-DD>"', '"2026-10-13"'),
                             ('"<fill: the user who approved accepting these milestones on their cited evidence>"', '"user"'),
                             ('"<fill: YYYY-MM-DD of that approval>"', '"2026-10-13"'),
                             ('"<fill: why their proof is legacy, e.g. closed before Checks existed or proved in prose>"', '"Closed before Checks existed; accepted at sign-off without rerunning old validators"')]:
            self.assertIn(slot, text)
            text = text.replace(slot, answer)
        text = re.sub(r'\[\s*"<fill: [^"]*"\s*\]', '[]', text)
        archive.write_text(text)
        again = self.cli('archive', 'prepare', '--write', '--pending', rerecorded)
        self.assertEqual(again['gaps'], [])
        self.assertEqual(again['approvals'], [])
        self.assertEqual(again['value']['signoff']['by'], 'user')
        self.assertEqual(again['value']['goal_checks'], ['observation:review'])
        checked = self.cli('archive', 'check', '--goal', 'engine-rewrite', '--pending', rerecorded)
        self.assertEqual(checked['legacy'], ['engine-rewrite:1', 'engine-rewrite:2', 'engine-rewrite:4'])
        gate = self.cli('gate', '--base', signoff_base, '--pending', rerecorded)
        self.assertEqual(gate['completed'], ['engine-rewrite'])
        # Legacy acceptance must be explicit and exact.
        value = json.loads(re.search(r'```json\n(.*?)\n```', archive.read_text(), re.S)[1])
        for change, expected in [(lambda v: v['legacy_acceptance'].pop('approved_by'), 'who approved it'),
                                 (lambda v: v['legacy_acceptance'].update(date='yesterday'), 'YYYY-MM-DD'),
                                 (lambda v: v['legacy_acceptance']['milestones'].remove('engine-rewrite:4'), 'engine-rewrite:4 has no recorded PASS'),
                                 (lambda v: v['legacy_acceptance']['milestones'].append('engine-rewrite:3'), 'engine-rewrite:3 already has recorded proof'),
                                 (lambda v: v.pop('legacy_acceptance'), 'engine-rewrite:1 has no named checks')]:
            changed = json.loads(json.dumps(value))
            change(changed)
            archive.write_text(re.sub(r'```json\n.*?\n```', lambda _: '```json\n' + json.dumps(changed, indent=2) + '\n```', text, flags=re.S))
            with self.subTest(expected=expected):
                failed = self.cli('archive', 'check', '--goal', 'engine-rewrite', '--pending', rerecorded, code=1)
                self.assertTrue(any(expected in x['message'] for x in failed['findings']), failed['findings'])
                self.assertIn('archive-invalid', self.codes(self.cli('gate', '--base', signoff_base, '--pending', rerecorded, code=1)))

    def test_hand_written_archive_validates_after_one_mechanical_edit(self):
        """The 0.6.1 case: task=ID citations, prose proof and no legacy block; adding the block suffices."""
        self.build_history()
        self.close_frontend()
        path = 'docs/goals-archive/2026-10-14-engine-rewrite.md'
        self.goals(head='— done', top='Signed-off: user, 2026-10-13\nArchive: ' + path + '\n' + GOAL_CRITERIA,
                   spec=(' — done', 'x', self.evidence('3.1', self.unit)),
                   audio=(' — done', 'x', self.evidence('4.1', self.base_commit), self.checks4),
                   frontend=(' — done', 'x', self.evidence('5.1', self.review)))
        rerecorded = self.cli('evidence', 'rerecord', self.review, '--write-proposed')
        criteria = {'1': ('every ported helper reproduces its cached fixture.', []),
                    '2': ('the reader replays the whole corpus.', []),
                    '3': ('validator:unit passes on the spec.', ['validator:unit']),
                    '4': ('live audio matches the capture.', ['validator:unit']),
                    '5': ('the user has reviewed the running app.', ['observation:review'])}
        proof = {'1': ['Helpers reproduce their fixtures; see the compat notes.'], '2': ['Reader replays the corpus (2026-10-11).'],
                 '3': ['3.1=' + self.unit], '4': ['unit PASS at tree 0123456789ab (2026-10-12).'], '5': ['5.1=' + self.review]}
        archive = {'version': 1, 'goal_id': 'engine-rewrite', 'status': 'done', 'outcome': 'completed',
                   'milestones': [{'id': 'engine-rewrite:' + n, 'criteria': c, 'checks': k, 'evidence': proof[n], 'exceptions': []}
                                  for n, (c, k) in criteria.items()],
                   'goal_checks': ['observation:review'], 'signoff': {'by': 'user', 'date': '2026-10-13'},
                   'limitations': [], 'refuted': [], 'followups': []}
        self.write(path, '# Completion archive\n\n```json\n' + json.dumps(archive, indent=2) + '\n```\n')
        self.commit('Goal signed off\n\n' + rerecorded['trailer'])
        failed = self.cli('archive', 'check', code=1)
        self.assertEqual(sorted(re.search(r'engine-rewrite:\d', x['message'])[0] for x in failed['findings']),
                         ['engine-rewrite:1', 'engine-rewrite:2', 'engine-rewrite:4'])
        self.cli('gate', '--base', 'HEAD~1', code=1)
        archive['legacy_acceptance'] = {'milestones': ['engine-rewrite:1', 'engine-rewrite:2', 'engine-rewrite:4'],
                                        'approved_by': 'user', 'date': '2026-10-13', 'reason': 'Closed before Checks existed or proved in prose.'}
        self.write(path, '# Completion archive\n\n```json\n' + json.dumps(archive, indent=2) + '\n```\n')
        self.assertEqual(self.cli('archive', 'check')['problems'], [])
        self.commit('Record the user-approved legacy acceptance')
        self.cli('gate', '--base', 'HEAD~2')
        self.assertNotIn('archive-invalid', self.codes(self.cli('lint')))

    def test_legacy_acceptance_never_covers_a_claim_made_in_this_batch(self):
        self.build_history()
        base = self.git('rev-parse', 'HEAD')
        # Milestone 5 completes in the same batch as the goal, with no review recorded.
        path = 'docs/goals-archive/engine-rewrite.md'
        self.goals(head='— done', top='Signed-off: user, 2026-10-13\nArchive: ' + path + '\n' + GOAL_CRITERIA,
                   spec=(' — done', 'x', self.evidence('3.1', self.unit)),
                   audio=(' — done', 'x', self.evidence('4.1', self.base_commit), self.checks4),
                   frontend=(' — done', 'x', self.evidence('5.1', base)))
        prepared = self.cli('archive', 'prepare', '--goal', 'engine-rewrite')
        value = prepared['value']
        self.assertIn('engine-rewrite:5', value['legacy_acceptance']['milestones'])
        value.update(outcome='done', signoff='user, 2026-10-13', limitations=[], refuted=[], followups=[])
        value['legacy_acceptance'].update(approved_by='user', date='2026-10-13', reason='Forged attempt to skip the review.')
        self.write(path, '```json\n' + json.dumps(value) + '\n```\n')
        self.assertEqual(self.cli('archive', 'check', '--goal', 'engine-rewrite')['problems'], [])
        missing = [x for x in self.cli('gate', '--base', base, code=1)['findings'] if x['code'] == 'missing-acceptance']
        self.assertEqual({x['message'] for x in missing},
                         {'Missing fresh observation:review for engine-rewrite:5', 'Missing fresh observation:review for engine-rewrite'})

    def test_prepare_refuses_shelved_goals_and_foreign_archives(self):
        self.build_history()
        self.cli('archive', 'prepare', code=2)
        output = self.cli('archive', 'prepare', '--goal', 'engine-rewrite')
        self.assertFalse(output['written'])
        self.assertFalse((self.root / output['path']).exists())
        self.write(output['path'], '```json\n{"goal_id": "another-goal"}\n```\n')
        self.goals(top='Archive: ' + output['path'] + '\n', spec=(' — done', 'x', self.evidence('3.1', self.unit)),
                   audio=(' — done', 'x', self.evidence('4.1', self.base_commit), self.checks4), frontend=(' — current', ' ', ''))
        self.assertIn('belongs to another goal', self.cli('archive', 'prepare', '--goal', 'engine-rewrite', code=2)['findings'][0]['message'])
