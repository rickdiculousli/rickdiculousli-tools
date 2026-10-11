from long_horizon_support import RepoTest, GOALS, OVERLAY


class GoalTests(RepoTest):
    def test_blocked_first_and_all_blocked(self):
        self.write('docs/handoff.md', '# Handoff\n## Blockers\n- [1.1] Input missing; recover: capture.md; 2026-10-11\n## Pending decisions\n')
        self.assertEqual(self.cli('status')['selection']['task']['id'], '1.2')
        with (self.root / 'docs/handoff.md').open('a') as handle:
            handle.write('## Blockers\n- [1.2] Ask user; recover: user; 2026-10-11\n')
        result = self.cli('status')
        self.assertEqual(result['selection']['mode'], 'all-blocked')
        self.assertTrue(result['needs_you'])

    def test_duplicate_current_and_ids(self):
        self.write('docs/goals.md', GOALS.replace('[1.2]', '[1.1]'))
        self.cli('status', code=1)
        self.write('docs/goals.md', GOALS.replace('## 2. Integrate', '## 2. Integrate — current'))
        self.cli('status', code=1)

    def test_fenced_and_parked(self):
        self.write('docs/goals.md', GOALS + '\n```md\n## 8. False — current\n- [ ] [1.1] False\n```\n')
        self.assertEqual(self.cli('status')['selection']['task']['id'], '1.1')

    def test_capabilities_all_of_and_unknown(self):
        self.write('docs/goals.md', GOALS.replace('(any)', '(fixtures, native)', 1))
        self.write('.agents/long-horizon.md', OVERLAY + '\n## Capabilities\ntags: {"any": [], "fixtures": ["fixtures"], "native": ["native"]}\n## Startup\nreadiness: "readiness.json"\n')
        self.write('readiness.json', '{"version":1,"levels":{"fixtures":{"ready":true,"strength":"sha256"},"native":{"ready":false,"strength":"exists"}}}')
        self.assertEqual(self.cli('status')['selection']['task']['id'], '1.2')
        self.write('readiness.json', '{"version":1,"levels":{"fixtures":{"ready":true,"strength":"sha256"},"native":{"ready":true,"strength":"exists"}}}')
        self.assertEqual(self.cli('status')['selection']['task']['id'], '1.1')
        self.write('docs/goals.md', GOALS.replace('(any)', '(unknown)', 1))
        self.assertEqual(self.cli('status')['selection']['task']['id'], '1.2')

    def test_manual_and_implicit(self):
        self.write('docs/goals.md', 'A prose-only roadmap')
        self.assertEqual(self.cli('status')['selection']['mode'], 'manual')
        self.cli('gate', code=1)
        self.write('docs/goals.md', '# Legacy\n## 1. Work\n- [ ] A task\n')
        self.assertTrue(self.cli('status')['selection']['task']['id'].startswith('1-'))

    def test_done_with_open_task(self):
        self.write('docs/goals.md', GOALS.replace('## 1. Build — current', '## 1. Build — done'))
        self.cli('lint', code=1)

    def test_shelved_earlier_goal_and_signoff(self):
        self.write('docs/goals.md', GOALS.replace('— current', '— shelved', 1).replace('ID: tiny', 'ID: tiny\nReason: user requested pause\nArchive: docs/stop.md') + '\n# Goal: Second — current\nID: second\n## 1. Work\n- [ ] [second.1] Work\n')
        self.assertEqual(self.cli('status')['selection']['task']['id'], 'second.1')
        self.write('docs/goals.md', GOALS.replace('- [ ]', '- [x]').replace('## 1. Build — current', '## 1. Build — done').replace('## 2. Integrate', '## 2. Integrate — done'))
        self.assertEqual(self.cli('status')['selection']['mode'], 'awaiting-signoff')

    def test_any_is_always_unprepared_and_readiness_checkout_stale(self):
        self.write('.agents/long-horizon.md', OVERLAY + '\n## Capabilities\ntags: {"native": ["native"]}\n## Startup\nreadiness: "readiness.json"\n')
        self.assertEqual(self.cli('status')['selection']['task']['id'], '1.1')
        self.write('readiness.json', '{"version":1,"checkout":"/other","levels":{"native":{"ready":true,"strength":"probed"}}}')
        result = self.cli('status')
        self.assertIn('readiness-unknown', [x['code'] for x in result['findings']])
        self.write('readiness.json', '{"version":1,"generated_at":"2000-01-01T00:00:00Z","levels":{"native":{"ready":true,"strength":"probed"}}}')
        self.assertIn('readiness-unknown', [x['code'] for x in self.cli('status')['findings']])

    def test_missing_id_uses_plain_normalized_text_sha256(self):
        import hashlib
        text = 'Task  with   whitespace'
        self.write('docs/goals.md', '# Legacy — current\n## 1. Work\n- [ ] ' + text + '\n')
        result = self.cli('status')
        expected = '1-' + hashlib.sha256(' '.join(text.split()).encode()).hexdigest()[:12]
        self.assertEqual(result['selection']['task']['id'], expected)
