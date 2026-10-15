from long_horizon_support import RepoTest, HANDOFF


class HandoffTests(RepoTest):
    def test_staleness_and_dirty(self):
        self.write('tiny.py', 'changed\n')
        self.commit('Code change')
        self.assertEqual(self.cli('status')['handoff']['state'], 'stale')
        self.write('docs/handoff.md', HANDOFF + 'Updated\n')
        self.assertEqual(self.cli('status')['handoff']['state'], 'dirty')

    def test_unrelated_docs_do_not_stale(self):
        self.write('docs/goals.md', (self.root / 'docs/goals.md').read_text() + '\n')
        self.commit('Roadmap whitespace')
        self.assertEqual(self.cli('status')['handoff']['state'], 'current')

    def test_redaction_budget(self):
        secret = 'ghp_' + 'a' * 35
        self.write('docs/handoff.md', HANDOFF + secret + '\n' + 'Line\n' * 85)
        result = self.cli('lint', code=1)
        self.assertNotIn(secret, str(result))
        self.assertIn('handoff-budget', [x['code'] for x in result['findings']])

    def test_pointer_cycle_and_repair_idempotence(self):
        self.write('CLAUDE.md', '@other.md\n')
        self.write('other.md', '@CLAUDE.md\n')
        self.assertIn('pointer-cycle', [x['code'] for x in self.cli('lint', code=1)['findings']])
        self.write('CLAUDE.md', '@AGENTS.md\n')
        self.write('docs/goals.md', '# Goal: Roadmap\r\nID: roadmap\r\n## 1. Work\r\n- [ ] Task without ID\r\n')
        before = (self.root / 'docs/goals.md').read_bytes()
        preview = self.cli('lint', '--fix')
        self.assertTrue(preview['diff'])
        self.assertEqual(before, (self.root / 'docs/goals.md').read_bytes())
        self.cli('lint', '--fix', '--apply')
        self.assertEqual(self.cli('lint', '--fix')['diff'], '')
        self.assertIn(b'\r\n', (self.root / 'docs/goals.md').read_bytes())
