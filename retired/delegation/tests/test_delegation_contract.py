"""Current-contract lint: layout drift and the overlay's version tag."""
import json
from pathlib import Path
import tempfile
import unittest

from delegation_support import ROOT, git, git_repo, isolate_xdg, run_cli, write_overlay
from delegation_check import contract
from delegation_check.overlay import load_overlay

INSTALLED = json.loads((ROOT / 'plugins/delegation/plugin.json').read_text())['version']
POINTER = "Delegation: follow the delegation skill; this repo's overlay is .agents/delegation.md.\n"


def bumped(version, index, delta):
    parts = [int(x) for x in version.split('.')]
    parts[index] += delta
    return '.'.join(str(x) for x in parts)


class ContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        isolate_xdg(self, Path(temp.name))
        self.root = git_repo(Path(temp.name) / 'repo')
        (self.root / 'AGENTS.md').write_text(POINTER)

    def lint(self):
        result = run_cli(self.root, 'lint', '--json')
        return result.returncode, json.loads(result.stdout)

    def test_installed_version_comes_from_the_plugin_manifest(self):
        self.assertEqual(contract.installed_version(), INSTALLED)

    def test_version_status(self):
        cases = [(None, 'mismatch'), (INSTALLED, 'current'), (bumped(INSTALLED, 2, 7), 'current'),
                 (bumped(INSTALLED, 1, 1), 'newer'), ('0.0.1', 'mismatch')]
        for tagged, expected in cases:
            with self.subTest(tagged=tagged):
                write_overlay(self.root, f'## Version\n{tagged}\n' if tagged else '## Parallel limit\n2\n')
                code, data = self.lint()
                self.assertEqual(code, 0)
                self.assertEqual(data['version'], {'installed': INSTALLED, 'tagged': tagged, 'status': expected})

    def test_text_lint_offers_migration_without_failing(self):
        write_overlay(self.root, '## Version\n0.0.1\n')
        result = run_cli(self.root, 'lint')
        self.assertEqual(result.returncode, 0)
        self.assertIn('version-mismatch', result.stdout)
        self.assertIn('delegation:migrate', result.stdout)
        self.assertIn('Overlay OK', result.stdout)

    def test_unknown_installed_version_and_no_overlay_skip_the_check(self):
        overlay = load_overlay(self.root)
        self.assertEqual(contract.version_status(overlay, INSTALLED)['status'], 'none')
        write_overlay(self.root, '## Version\n0.1.0\n')
        self.assertEqual(contract.version_status(load_overlay(self.root), None)['status'], 'unknown')

    def test_malformed_version_is_a_problem(self):
        write_overlay(self.root, '## Version\nlatest\n')
        code, data = self.lint()
        self.assertEqual(code, 1)
        self.assertIn('Version needs one plugin version', data['problems'][0])

    def test_layout_reports_unexpected_and_missing_paths(self):
        write_overlay(self.root, f'## Version\n{INSTALLED}\n## Rote scripts\nsync: python3 .agents/delegation/scripts/sync.py; replaces copying\n')
        material = self.root / '.agents/delegation'
        (material / 'scripts').mkdir(parents=True)
        (material / 'scripts/sync.py').write_text('')
        (material / 'scripts/old.py').write_text('')
        (material / 'notes.md').write_text('')
        (self.root / '.delegation').mkdir()
        (self.root / '.gitignore').write_text('build/\n.delegation/\n')
        (self.root / 'AGENTS.md').write_text('nothing here\n')
        code, data = self.lint()
        self.assertEqual(code, 0)
        found = {(item['kind'], item['path']) for item in data['layout']}
        self.assertEqual(found, {('unexpected', '.delegation'), ('unexpected', '.gitignore:2'),
                                 ('unexpected', '.agents/delegation/notes.md'),
                                 ('unexpected', '.agents/delegation/scripts/old.py'),
                                 ('missing', 'AGENTS.md')})

    def test_claude_md_must_reach_the_pointer(self):
        write_overlay(self.root, f'## Version\n{INSTALLED}\n')
        (self.root / 'CLAUDE.md').write_text('# Notes\n')
        self.assertIn(('missing', 'CLAUDE.md'), {(i['kind'], i['path']) for i in self.lint()[1]['layout']})
        (self.root / 'CLAUDE.md').write_text('@AGENTS.md\n')
        self.assertEqual(self.lint()[1]['layout'], [])

    def test_current_repository_lints_clean(self):
        runbook = self.root / '.agents/delegation/runbooks/review.md'
        runbook.parent.mkdir(parents=True)
        runbook.write_text('review\n')
        git(self.root, 'add', '.agents/delegation/runbooks/review.md')
        write_overlay(self.root, f'## Version\n{INSTALLED}\n## Roles\nreview: tier=execute, runbook=.agents/delegation/runbooks/review.md, max-uses=2\n')
        code, data = self.lint()
        self.assertEqual((code, data['ok'], data['layout'], data['version']['status']), (0, True, [], 'current'))


if __name__ == '__main__':
    unittest.main()
