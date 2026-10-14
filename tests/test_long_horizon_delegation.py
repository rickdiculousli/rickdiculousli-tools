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


class RecordingAfterOwnOutputTests(RepoTest):
    """Judge runs first, then each result is recorded: the 0.6.1 flow that broke on its own output."""

    def setUp(self):
        super().setUp()
        self.write('.agents/delegation.md', '## Validators\nunit: echo unit\nlint: echo lint\n## Parallel limit\n1\n')
        overlay = OVERLAY.replace('"observation:review"', '"validator:lint": {"domain": "lint-v1"}, "observation:review"')
        self.write('.agents/long-horizon.md', overlay + 'delegation-script: ' + json.dumps(str(CHECKER)) + '\n')
        self.commit('Two registered validators')

    def judge(self, validator):
        result = subprocess.run([sys.executable, str(CHECKER), '--root', str(self.root), 'run', validator, '--judge'],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.split()[0]

    def record(self, check, snapshot, delegation, result, code=0, extra=()):
        return self.cli('evidence', 'record', check, '--snapshot', snapshot, '--outcome', 'PASS', '--delegation', delegation,
                        '--result', result, '--log', 'regenerate:registered validator via the declared checker', *extra, code=code)

    def test_run_number_and_listed_candidates(self):
        unit = self.judge('unit')
        delegation = unit.split('#')[0]
        snapshot = self.cli('evidence', 'prepare', 'validator:unit')['snapshot']['id']
        failed = self.record('validator:unit', snapshot, delegation, '2', code=2)
        message = failed['findings'][0]['message']
        self.assertIn('Registered result ' + delegation + '#2 is missing', message)
        self.assertIn(unit + ' (unit, PASS, tree ', message)
        self.assertEqual(self.record('validator:unit', snapshot, delegation, '1')['record']['result'], unit)

    def test_second_record_after_written_evidence_and_doc_edit(self):
        unit, lint = self.judge('unit'), self.judge('lint')
        snapshots = self.cli('evidence', 'prepare', 'validator:unit', 'validator:lint', '--attempt', 'batch')['snapshots']
        self.assertEqual([x['check'] for x in snapshots], ['validator:unit', 'validator:lint'])
        self.assertEqual(len({x['tree'] for x in snapshots}), 1)
        self.assertEqual({x['attempt'] for x in snapshots}, {'batch:validator:unit', 'batch:validator:lint'})
        trailers = self.base / 'trailers.txt'
        first = self.record('validator:unit', snapshots[0]['id'], unit.split('#')[0], unit, extra=('--write-proposed', '--trailers-file', str(trailers)))
        self.assertTrue(first['written'])
        # The written detail file and a review-doc edit both change the checker tree, not the checks' scope.
        self.write('docs/evidence/checklist.md', 'Reviewed 2026-10-13.\n')
        tree = subprocess.run([sys.executable, str(CHECKER), '--root', str(self.root), 'tree'], capture_output=True, text=True, env=self.env).stdout.strip()
        self.assertNotEqual(tree, snapshots[1]['tree'])
        second = self.record('validator:lint', snapshots[1]['id'], lint.split('#')[0], lint, extra=('--write-proposed', '--trailers-file', str(trailers)))
        self.assertEqual(second['record']['tree'], snapshots[1]['tree'])
        self.assertEqual(len(trailers.read_text().splitlines()), 2)
        # An in-scope change still blocks PASS, and a snapshot from after the run names the fix.
        late = self.cli('evidence', 'prepare', 'validator:unit')['snapshot']['id']
        failed = self.record('validator:unit', late, unit.split('#')[0], unit, code=2)
        self.assertIn('Prepare every check of a run before writing records', failed['findings'][0]['message'])
        snapshot = self.cli('evidence', 'prepare', 'validator:unit')['snapshot']['id']
        fresh = self.judge('unit')
        self.write('tiny.py', 'def tiny():\n    return 2\n')
        self.record('validator:unit', snapshot, fresh.split('#')[0], fresh, code=1)

    def test_rerecord_checked_result_after_criteria_change(self):
        unit = self.judge('unit')
        snapshot = self.cli('evidence', 'prepare', 'validator:unit')['snapshot']['id']
        output = self.record('validator:unit', snapshot, unit.split('#')[0], unit)
        self.carry(output)
        self.write('docs/goals.md', (self.root / 'docs/goals.md').read_text().replace(
            'Done when: validator:unit\n- [ ] [1.1]', 'Done when: validator:unit on the whole module\n- [ ] [1.1]'))
        self.assertEqual(self.cli('evidence', 'find', 'validator:unit')['checks'][0]['status'], 'stale')
        carried = self.cli('evidence', 'rerecord', output['record']['id'])
        self.assertEqual(carried['record']['tree'], output['record']['tree'])
        self.assertEqual(self.cli('evidence', 'find', 'validator:unit', '--pending', carried['record']['id'])['checks'][0]['status'], 'fresh')
