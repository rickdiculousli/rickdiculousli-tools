"""Current-contract lint: layout drift and the overlay's version tag."""
import json
from long_horizon_support import ROOT, RepoTest, OVERLAY
from long_horizon import contract

INSTALLED = json.loads((ROOT / 'plugins/long-horizon/plugin.json').read_text())['version']


def bumped(version, index, delta):
    parts = [int(x) for x in version.split('.')]
    parts[index] += delta
    return '.'.join(str(x) for x in parts)


class ContractTests(RepoTest):
    def codes(self, command='status', code=0):
        return {x['code']: x for x in self.cli(command, code=code)['findings']}

    def test_installed_version_comes_from_the_plugin_manifest(self):
        self.assertEqual(contract.installed_version(), INSTALLED)

    def test_version_findings(self):
        cases = [(None, 'version-mismatch'), ('0.0.1', 'version-mismatch'), (INSTALLED, None),
                 (bumped(INSTALLED, 2, 7), None), (bumped(INSTALLED, 1, 1), 'version-newer')]
        for tagged, expected in cases:
            with self.subTest(tagged=tagged):
                self.write('.agents/long-horizon.md', OVERLAY + (f'## Version\n{tagged}\n' if tagged else ''))
                codes = self.codes()
                found = {'version-mismatch', 'version-newer'} & set(codes)
                self.assertEqual(found, {expected} if expected else set())
                if expected:
                    self.assertEqual(codes[expected]['severity'], 'warning')
        self.write('.agents/long-horizon.md', OVERLAY)
        self.assertIn('long-horizon:migrate', self.codes()['version-mismatch']['remedy'])

    def test_no_overlay_skips_the_version_check(self):
        (self.root / '.agents/long-horizon.md').unlink()
        self.assertNotIn('version-mismatch', self.codes())

    def test_malformed_version_is_invalid(self):
        self.write('.agents/long-horizon.md', OVERLAY + '## Version\nlatest\n')
        self.assertIn('Version needs one plugin version', self.cli('status', code=2)['findings'][0]['message'])

    def test_schema_heading_is_ignored_and_reported(self):
        self.write('.agents/long-horizon.md', OVERLAY.replace('# Long-horizon\n', '# Long-horizon\n## Schema\n1\n') + f'## Version\n{INSTALLED}\n')
        outdated = self.codes('lint')['layout-outdated']
        self.assertEqual((outdated['severity'], outdated['line']), ('warning', 2))
        self.assertIn('## Version', outdated['remedy'])

    def test_layout_reports_stray_state_and_missing_files(self):
        self.write('.agents/long-horizon.md', OVERLAY + f'## Version\n{INSTALLED}\n')
        self.write('.long-horizon/notes.json', '{}')
        (self.root / 'docs/handoff.md').unlink()
        codes = self.codes('lint')
        self.assertTrue(codes['layout-unexpected']['path'].endswith('.long-horizon'))
        self.assertTrue(codes['layout-missing']['path'].endswith('handoff.md'))
        self.assertNotIn('layout-unexpected', self.codes('status'))

    def test_current_repository_lints_clean(self):
        self.write('.agents/long-horizon.md', OVERLAY + f'## Version\n{INSTALLED}\n')
        codes = self.codes('lint')
        self.assertFalse({c for c in codes if c.startswith(('layout-', 'version-'))})
