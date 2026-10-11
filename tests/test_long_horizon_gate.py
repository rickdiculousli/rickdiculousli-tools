from long_horizon_support import RepoTest, GOALS


class GateTests(RepoTest):
    def test_new_task_requires_evidence_and_pending_is_explicit(self):
        self.write('docs/goals.md', GOALS.replace('- [ ] [1.1]', '- [x] [1.1]'))
        self.cli('gate', code=1)
        output = self.record(self.prepare())
        self.write('docs/goals.md', (self.root / 'docs/goals.md').read_text().replace('- [x] [1.1] Implement tiny function. (any)', '- [x] [1.1] Implement tiny function. (any)\nEvidence: 1.1=' + output['record']['id']))
        self.cli('gate', code=1)
        self.cli('gate', '--pending', output['record']['id'])

    def test_milestone_whole_call_not_task_only(self):
        commit = self.git('rev-parse', 'HEAD')
        text = GOALS.replace('- [ ] [1.1]', '- [x] [1.1]').replace('- [ ] [1.2]', '- [x] [1.2]')
        text = text.replace('## 1. Build — current', '## 1. Build — done')
        text = text.replace(' (any)\n', ' (any)\nEvidence: 1.1=' + commit + '\n', 1)
        text = text.replace('- [x] [1.2] Review tiny function. (any)', '- [x] [1.2] Review tiny function. (any)\nEvidence: 1.2=' + commit)
        self.write('docs/goals.md', text)
        result = self.cli('gate', code=1)
        self.assertIn('missing-acceptance', [x['code'] for x in result['findings']])
        output = self.record(self.prepare())
        self.cli('gate', '--pending', output['record']['id'])

    def test_criteria_policy_requires_approval(self):
        self.write('docs/goals.md', GOALS.replace('Done when: validator:unit', 'Done when: validator:unit on new corpus', 1))
        self.assertIn('policy-approval', [x['code'] for x in self.cli('gate', code=1)['findings']])
        self.write('docs/goals.md', (self.root / 'docs/goals.md').read_text().replace('ID: tiny', 'ID: tiny\nPolicy-Approval: user approved new corpus on 2026-10-11'))
        self.cli('gate')

    def test_exception_target_and_signoff_not_waived(self):
        self.cli('evidence', 'record', 'validator:unit', '--exception', '--target', 'nonexistent', '--reason', 'explicit limited acceptance', '--by', 'user', code=2)
        result = self.cli('evidence', 'record', 'validator:unit', '--exception', '--target', 'tiny', '--reason', 'explicit limited acceptance', '--by', 'user')
        self.assertTrue(result['record']['exception'])
        self.write('docs/goals.md', GOALS.replace('— current', '— done').replace('## 2. Integrate', '## 2. Integrate — done').replace('- [ ]', '- [x]'))
        data = self.cli('gate', '--pending', result['record']['id'], code=1)
        self.assertIn('missing-signoff', [x['code'] for x in data['findings']])

    def test_base_checks_committed_completion(self):
        base = self.git('rev-parse', 'HEAD')
        self.write('docs/goals.md', GOALS.replace('- [ ] [1.1]', '- [x] [1.1]'))
        self.commit('Unproven completion')
        self.cli('gate')
        self.cli('gate', '--base', base, code=1)
