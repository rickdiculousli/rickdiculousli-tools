import json
from long_horizon_support import RepoTest, GOALS
from long_horizon.goals import parse, flatten
from long_horizon import overlay
from long_horizon.git import Git


class LifecycleTests(RepoTest):
    def test_complete_archive_compression_and_forgery(self):
        # One milestone/goal with the same unit acceptance keeps the pilot focused.
        text = '# Goal: Tiny — current\nID: tiny\nDone when: validator:unit\n## 1. Build — current\nDone when: validator:unit\n- [ ] [1.1] Implement tiny function. (any)\n'
        self.write('docs/goals.md', text)
        base = self.commit('Bounded one-milestone fixture')
        proof = self.record(self.prepare())
        id_ = proof['record']['id']
        self.carry(proof)
        done = text.replace('— current', '— done').replace('- [ ]', '- [x]')
        done = done.replace('ID: tiny', 'ID: tiny\nSigned-off: user, 2026-10-11\nArchive: docs/goals-archive/tiny.md')
        done += 'Evidence: 1.1=' + id_ + '\n'
        archive = {'version': 1, 'goal_id': 'tiny', 'status': 'done', 'outcome': 'Bounded fixture accepted',
                   'milestones': [{'id': 'tiny:1', 'criteria': 'validator:unit', 'checks': ['validator:unit'], 'evidence': [id_], 'exceptions': []}],
                   'goal_checks': ['validator:unit'], 'signoff': 'user, 2026-10-11',
                   'limitations': [], 'refuted': [], 'followups': []}
        self.write('docs/goals-archive/tiny.md', '# Tiny completion\n```json\n' + json.dumps(archive) + '\n```\n')
        self.write('docs/goals.md', done)
        self.cli('gate', '--base', base)
        compressed = done.split('## 1.')[0]
        self.write('docs/goals.md', compressed)
        self.cli('gate', '--base', base)
        self.assertEqual(self.cli('status')['selection']['mode'], 'no-active-goal')
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'fresh')
        archive['milestones'][0]['criteria'] = 'validator:unit against invented broader claims'
        self.write('docs/goals-archive/tiny.md', '# Forged completion\n```json\n' + json.dumps(archive) + '\n```\n')
        self.cli('status', code=1)
        self.cli('gate', '--base', base, code=1)

    def test_pending_cleanup_and_wind_down_are_exact(self):
        proof = self.record(self.prepare())
        id_ = proof['record']['id']
        self.cli('evidence', 'cleanup', '--commit', 'HEAD', '--id', id_, code=2)
        commit = self.carry(proof)
        removed = self.cli('evidence', 'cleanup', '--commit', commit, '--id', id_)
        self.assertEqual(removed['removed'], [id_])
        self.assertEqual(self.cli('evidence', 'cleanup', '--commit', commit, '--id', id_)['removed'], [])
        location = self.cli('status')['state_directory']
        self.cli('state', 'clear', '--state-directory', str(self.base), code=2)
        self.cli('state', 'clear', '--state-directory', location)
        self.assertTrue((self.root / proof['record']['detail']).exists())
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'fresh')

    def test_human_observation_needs_dated_durable_note(self):
        before = self.prepare(check='observation:review')
        self.write('docs/evidence/review.md', 'User reviewed the whole calling context, 2026-10-11.\n')
        output = self.cli('evidence', 'record', 'observation:review', '--snapshot', before['id'], '--outcome', 'PASS',
                          '--reviewer', 'user', '--reviewer-kind', 'human', '--review-note', 'docs/evidence/review.md',
                          '--log', 'docs/evidence/review.md')
        self.carry(output)
        self.assertEqual(self.cli('evidence', 'find', 'observation:review')['checks'][0]['status'], 'fresh')
