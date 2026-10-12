"""Pilot assertions must distinguish missing evidence from a broken environment."""
import json
from pathlib import Path
import subprocess
import sys
from long_horizon_support import RepoTest, OVERLAY, ROOT
from scripts.run_long_horizon_pilots import inspect


class PilotAssertionsTests(RepoTest):
    def test_composed_requires_real_ledger_deletion_and_missing_result_refusal(self):
        checker = ROOT / 'plugins/delegation/skills/delegation/scripts/check.py'
        def check(*args):
            result = subprocess.run([sys.executable, str(checker), '--root', str(self.root), *args], env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout
        self.write('.agents/delegation.md', '## Validators\nunit: echo fixture\n')
        self.write('.agents/long-horizon.md', OVERLAY + 'delegation-script: ' + json.dumps(str(checker)) + '\n')
        self.commit('Declared checker')
        brief = self.base / 'brief.md'
        brief.write_text('Fixture')
        check('open', '--delegation', 'd1', '--tier', 'routine', '--brief', str(brief))
        check('run', 'unit', '--delegation', 'd1')
        check('close', '--delegation', 'd1', '--outcome', 'done')
        result = subprocess.CompletedProcess([], 0, '', '')
        assertions, _ = inspect(self.root, 'composed', result, self.env)
        self.assertFalse(assertions['fixture_ledger_deleted'])
        self.assertFalse(assertions['current_query_empty_without_identity_error'])
        self.assertFalse(assertions['new_checked_claim_refused_for_missing_result'])
        path = Path(json.loads(check('paths', '--json'))['worktree_state_directory'])
        (path / 'ledger.jsonl').unlink()
        assertions, _ = inspect(self.root, 'composed', result, self.env)
        self.assertTrue(assertions['fixture_ledger_deleted'])
        self.assertTrue(assertions['current_query_empty_without_identity_error'])
        self.assertTrue(assertions['new_checked_claim_refused_for_missing_result'])
        # A changed identity is an environment error, not evidence of correct refusal.
        saved = json.loads((path / 'identity.json').read_text())
        saved['files']['worktree']['inode'] += 1
        (path / 'identity.json').write_text(json.dumps(saved))
        assertions, _ = inspect(self.root, 'composed', result, self.env)
        self.assertFalse(assertions['current_query_empty_without_identity_error'])
        self.assertFalse(assertions['new_checked_claim_refused_for_missing_result'])
