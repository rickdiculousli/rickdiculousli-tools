from long_horizon_support import RepoTest, OVERLAY
from long_horizon import overlay
from long_horizon.model import Invalid


class OverlayTests(RepoTest):
    def test_defaults_and_read_only(self):
        index = (self.root / '.git/index').read_bytes()
        before = self.git('status', '--porcelain')
        result = self.cli('status')
        self.assertEqual(result['selection']['task']['id'], '1.1')
        self.assertFalse((self.base / 'state').exists())
        self.assertEqual((self.root / '.git/index').read_bytes(), index)
        self.assertEqual(self.git('status', '--porcelain'), before)

    def test_strict_grammar(self):
        for text in [OVERLAY + '\n## Evidence\n', OVERLAY.replace('path:', 'paht:'),
                     OVERLAY.replace('path: "docs/goals.md"', 'path: true'),
                     OVERLAY + '\n## State\nstate: "active"\nstate: "dormant"',
                     OVERLAY + '\n## Integration\nsteps: ["commit"]']:
            with self.subTest(text=text), self.assertRaises(Invalid):
                overlay.parse(text)

    def test_case_crlf_and_comments(self):
        value = overlay.parse(OVERLAY.replace('Goals and ownership', 'GOALS AND OWNERSHIP').replace('\n', '\r\n') + '<!-- comment -->\r\n')
        self.assertEqual(value['goals and ownership']['path'], 'docs/goals.md')

    def test_escape_and_symlink(self):
        self.write('.agents/long-horizon.md', OVERLAY.replace('docs/goals.md', '../escape'))
        self.cli('status', code=2)
        (self.root / 'external').symlink_to(self.base, target_is_directory=True)
        self.write('.agents/long-horizon.md', OVERLAY.replace('docs/goals.md', 'external/goals.md'))
        self.cli('status', code=2)

    def test_draft_and_dormant(self):
        draft = self.base / 'draft'
        draft.mkdir()
        (draft / 'overlay.md').write_text(OVERLAY)
        (draft / 'docs').mkdir()
        (draft / 'docs/goals.md').write_text('# Goal: Draft\nID: draft\n## 1. Draft\n- [ ] [d.1] Draft task\n')
        result = self.cli('status', '--overlay', str(draft / 'overlay.md'), '--draft-root', str(draft))
        self.assertEqual(result['selection']['task']['id'], 'd.1')
        result = self.cli('lint', '--overlay', str(draft / 'overlay.md'), '--draft-root', str(draft))
        self.assertNotIn('activation-unreachable', [x['code'] for x in result['findings']])
        self.write('.agents/long-horizon.md', OVERLAY + '\n## State\nstate: "dormant"\n')
        self.assertEqual(self.cli('status')['selection']['mode'], 'dormant')

    def test_linked_worktree_and_subdirectory(self):
        linked = self.base / 'linked worktree'
        self.git('worktree', 'add', '-b', 'linked', str(linked))
        result = self.cli('status', root=linked / 'docs')
        self.assertEqual(result['selection']['task']['id'], '1.1')
        self.assertEqual(result['git']['common_dir'], str(self.root / '.git'))
        self.assertNotEqual(result['state_directory'], self.cli('status')['state_directory'])

    def test_detached_unborn_and_script_path_resolution(self):
        self.git('checkout', '--detach')
        result = self.cli('status')
        self.assertIsNone(result['git']['branch'])
        self.git('checkout', '--orphan', 'unborn')
        self.assertIsNone(self.cli('status')['git']['head'])
        self.write('.agents/long-horizon.md', OVERLAY + '\n## Batch\nquota: true\nquota-env: "LONG_HORIZON_TEST_MISSING_QUOTA"\n')
        result = self.cli('status')
        self.assertIn('script-missing', [x['code'] for x in result['findings']])
        self.assertFalse((self.base / 'state').exists())
