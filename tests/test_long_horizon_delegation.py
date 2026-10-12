import json
from pathlib import Path
import subprocess
import sys
from long_horizon_support import RepoTest, OVERLAY, ROOT

CHECKER = ROOT / 'plugins/delegation/skills/delegation/scripts/check.py'


class DelegationTests(RepoTest):
    def checker(self, *args, code=0):
        result = subprocess.run([sys.executable, str(CHECKER), '--root', str(self.root), *args], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def test_actual_checker_registered_result_and_lost_ledger(self):
        self.write('.agents/delegation.md', '## Validators\nunit: echo fixture validator\n## Parallel limit\n1\n')
        self.write('.gitignore', '.delegation/\n')
        self.write('.agents/long-horizon.md', OVERLAY + 'delegation-script: ' + json.dumps(str(CHECKER)) + '\n')
        self.commit('Actual checker fixture')
        brief = self.base / 'brief.md'
        brief.write_text('Run the tiny validator\n')
        self.checker('open', '--delegation', 'd1', '--tier', 'execute', '--brief', str(brief))
        self.assertIn('delegation-pending', [x['code'] for x in self.cli('gate', code=1)['findings']])
        before = self.prepare()
        self.checker('run', 'unit', '--delegation', 'd1')
        output = self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS',
                          '--delegation', 'd1', '--result', 'd1#1', '--log', 'regenerate:registered unit validator via declared checker')
        self.assertEqual(output['record']['claim'], 'checked')
        self.checker('close', '--delegation', 'd1', '--outcome', 'done')
        self.carry(output)
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'fresh')
        import shutil
        paths = json.loads(self.checker('paths', '--json'))
        shutil.rmtree(paths['worktree_state_directory'])
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'fresh')
        before = self.prepare()
        self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS',
                 '--delegation', 'd1', '--result', 'd1#1', '--log', 'regenerate:unit fixture', code=2)

    def test_configured_missing_env_and_corrupt_stub(self):
        self.write('.agents/long-horizon.md', OVERLAY + 'delegation-env: "LONG_HORIZON_TEST_MISSING_CHECKER"\n')
        self.cli('evidence', 'prepare', 'validator:unit', code=2)
        stub = self.base / 'stub checker.py'
        stub.write_text('print("corrupt")\n')
        self.write('.agents/long-horizon.md', OVERLAY + 'delegation-script: ' + json.dumps(str(stub)) + '\n')
        self.cli('evidence', 'prepare', 'validator:unit', code=2)

    def test_registered_wrong_validator_unstable_and_failed_never_pass(self):
        self.write('.agents/delegation.md', '## Validators\nunit: echo unit\nother: echo other\nbad: exit 3\nedit: echo changed >> tiny.py\n## Parallel limit\n1\n')
        self.write('.gitignore', '.delegation/\n')
        self.write('.agents/long-horizon.md', OVERLAY + 'delegation-script: ' + json.dumps(str(CHECKER)) + '\n')
        self.commit('Negative actual checker fixture')
        brief = self.base / 'brief.md'
        brief.write_text('Negative validators\n')
        self.checker('open', '--delegation', 'd1', '--tier', 'execute', '--brief', str(brief))
        for validator, code in [('other', 0), ('bad', 1), ('edit', 0)]:
            before = self.prepare()
            self.checker('run', validator, '--delegation', 'd1', code=code)
            output = json.loads(self.checker('query', '--delegation', 'd1', '--json'))
            result = output['results'][-1]['id']
            self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS', '--delegation', 'd1', '--result', result, '--log', 'regenerate:negative actual validator', code=2)

    def test_gate_names_close_command_and_judge_run_records_evidence(self):
        self.write('.agents/delegation.md', '## Validators\nunit: echo fixture validator\n## Parallel limit\n1\n')
        self.write('.agents/long-horizon.md', OVERLAY + 'delegation-script: ' + json.dumps(str(CHECKER)) + '\n')
        self.commit('Actual checker fixture')
        brief = self.base / 'brief.md'
        brief.write_text('Read only\n')
        self.checker('open', '--delegation', 'd1', '--tier', 'routine', '--brief', str(brief))
        pending = next(x for x in self.cli('gate', code=1)['findings'] if x['code'] == 'delegation-pending')
        self.assertIn('d1', pending['message'])
        self.assertIn('close --delegation d1 --outcome', pending['remedy'])
        self.checker('close', '--delegation', 'd1', '--outcome', 'done')
        before = self.prepare()
        result = self.checker('run', 'unit', '--judge').split()[0]
        self.assertNotIn('delegation-pending', [x['code'] for x in self.cli('gate')['findings']])
        output = self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS',
                          '--delegation', result.split('#')[0], '--result', result, '--log', 'regenerate:registered unit validator via judge run')
        self.assertEqual(output['record']['claim'], 'checked')
