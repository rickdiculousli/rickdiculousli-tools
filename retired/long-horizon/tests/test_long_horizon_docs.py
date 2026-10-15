import json
from pathlib import Path
import re
from long_horizon_support import RepoTest, ROOT
from long_horizon.overlay import parse
from long_horizon.goals import outside

PLUGIN = ROOT / 'plugins/long-horizon'


class DocumentationTests(RepoTest):
    def test_resource_links_and_overlay_examples(self):
        for path in PLUGIN.rglob('*.md'):
            text = '\n'.join(raw for _, raw in outside(path.read_text()))
            for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
                if not link.startswith(('https:', 'http:', '#')):
                    self.assertTrue((path.parent / link.split('#')[0]).is_file(), str(path) + ': ' + link)
        document = (PLUGIN / 'skills/resume/reference/overlay.md').read_text()
        blocks = re.findall(r'```markdown\n(.*?)\n```', document, re.S)
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            parse(block)

    def test_public_cli_walkthrough_and_exit_codes(self):
        self.cli('status', '--brief')
        self.cli('lint')
        self.cli('lint', '--fix')
        self.cli('lint', '--fix', '--apply')
        self.cli('gate')
        self.cli('closure', 'verify')
        self.cli('state', 'gc')
        self.cli('state', 'gc', '--apply', '--if-due')
        before = self.prepare('documented')
        trailers = self.base / 'trailers with spaces.txt'
        output = self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS', '--command', 'python3 -m unittest -v', '--exit', '0', '--log', 'regenerate:declared unit check at this commit', '--trailers-file', str(trailers))
        self.assertEqual(trailers.read_text(), output['trailer'] + '\n')
        self.cli('evidence', 'find', 'validator:unit', '--pending', output['record']['id'])
        self.cli('gate', '--pending', output['record']['id'])
        commit = self.carry(output)
        self.cli('evidence', 'cleanup', '--commit', commit, '--id', output['record']['id'])

    def test_installed_copy_with_spaces_imports_without_runtime_files(self):
        import shutil
        import subprocess
        import sys
        installed = self.base / 'installed plugin with spaces'
        shutil.copytree(PLUGIN, installed, ignore=shutil.ignore_patterns('__pycache__'))
        script = installed / 'skills/resume/scripts/lh.py'
        result = subprocess.run([sys.executable, str(script), 'evidence', 'prepare', 'validator:unit', '--root', str(self.root), '--json'], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(list(installed.rglob('__pycache__')))
        self.assertFalse(list(installed.rglob('state.lock')))
        self.assertTrue((self.base / 'state/rickdiculousli-tools/long-horizon/state.lock').exists())
