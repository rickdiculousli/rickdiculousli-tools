import json
import shutil
from long_horizon_support import RepoTest, GOALS, OVERLAY
from long_horizon.evidence import parse_trailer
from long_horizon.model import Invalid


class EvidenceTests(RepoTest):
    def test_pending_then_durable_docs_reuse_and_fresh_clone(self):
        before = self.prepare('run-1')
        output = self.record(before)
        id_ = output['record']['id']
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'missing')
        self.assertEqual(self.cli('evidence', 'find', '--pending', id_)['checks'][0]['status'], 'fresh')
        commit = self.carry(output)
        self.write('docs/handoff.md', '# Handoff\n## Blockers\n## Pending decisions\nDocs-only update\n')
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'fresh')
        clone = self.base / 'fresh clone'
        self.git('clone', str(self.root), str(clone))
        shutil.rmtree(self.base / 'state')
        self.assertEqual(self.cli('evidence', 'find', root=clone)['checks'][0]['status'], 'fresh')
        self.assertTrue(commit)

    def test_stale_and_unstable(self):
        before = self.prepare()
        self.write('tiny.py', 'changed\n')
        self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS',
                 '--command', 'true', '--exit', '0', '--log', 'regenerate:true fixture check', code=1)
        self.record(before, 'UNSTABLE')
        before = self.prepare()
        output = self.record(before)
        self.carry(output)
        self.write('tiny.py', 'changed again\n')
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'stale')

    def test_mode_deletion_untracked_ignored_and_no_git_mutation(self):
        before = self.prepare()
        original_index = (self.root / '.git/index').read_bytes()
        objects = sorted(str(x) for x in (self.root / '.git/objects').rglob('*'))
        self.prepare()
        self.assertEqual((self.root / '.git/index').read_bytes(), original_index)
        self.assertEqual(sorted(str(x) for x in (self.root / '.git/objects').rglob('*')), objects)
        (self.root / 'tiny.py').chmod(0o755)
        self.assertNotEqual(before['scope'], self.prepare()['scope'])
        (self.root / 'tiny.py').unlink()
        self.assertNotEqual(before['scope'], self.prepare()['scope'])
        self.write('new file.py', 'new')
        self.assertNotEqual(before['scope'], self.prepare()['scope'])
        self.write('.git/info/exclude', 'ignored.data\n')
        scope = self.prepare()['scope']
        self.write('ignored.data', 'ignored')
        self.assertEqual(scope, self.prepare()['scope'])

    def test_idempotent_attempt_and_record(self):
        before = self.prepare('attempt')
        self.assertEqual(before['id'], self.prepare('attempt')['id'])
        output = self.record(before)
        self.assertEqual(output, self.record(before))
        self.write('tiny.py', 'changed')
        self.cli('evidence', 'prepare', 'validator:unit', '--attempt', 'attempt', code=2)

    def test_later_fail_and_duplicate_old_pass(self):
        passed = self.record(self.prepare())
        self.carry(passed)
        failed = self.record(self.prepare(), 'FAIL')
        self.carry(failed)
        self.write('docs/handoff.md', '# Handoff\n## Blockers\n## Pending decisions\nRepeat old PASS\n')
        self.commit('Duplicate old PASS\n\n' + passed['trailer'])
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'fail')

    def test_policy_criteria_and_free_text_changes(self):
        output = self.record(self.prepare())
        self.carry(output)
        self.write('docs/goals.md', GOALS.replace('Done when: validator:unit', 'Done when: validator:unit on a bigger corpus', 1))
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'stale')

    def test_strict_trailer_and_persistent_route(self):
        before = self.prepare()
        self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS',
                 '--command', 'true', '--exit', '0', '--log', '/tmp/transient.log', code=2)
        output = self.record(before)
        self.assertEqual(parse_trailer(output['trailer'])['id'], output['record']['id'])
        with self.assertRaises(Invalid):
            parse_trailer(output['trailer'] + ' name=duplicate')

    def test_external_probe_before_after_and_unknown_default(self):
        self.write('input.data', 'a' * 64 + '\n')
        import sys
        input_spec = {'command': [sys.executable, '-c', 'from pathlib import Path; print(Path("input.data").read_text().strip())'], 'timeout': 2, 'recover': 'restore input.data'}
        self.write('.agents/long-horizon.md', OVERLAY.replace('{"domain": "unit-v1"}', '{"domain": "unit-v1", "inputs": ["fixture"]}') + 'inputs: ' + json.dumps({'fixture': input_spec}) + '\n')
        self.cli('evidence', 'prepare', 'validator:unit', code=2)
        before = self.cli('evidence', 'prepare', 'validator:unit', '--probe-inputs')['snapshot']
        self.cli('evidence', 'record', 'validator:unit', '--snapshot', before['id'], '--outcome', 'PASS',
                 '--command', 'true', '--exit', '0', '--log', 'regenerate:fixture check', '--probe-inputs')
        self.assertEqual(self.cli('evidence', 'find')['checks'][0]['status'], 'unknown')
        self.write('input.data', 'bad output\n')
        self.cli('evidence', 'prepare', 'validator:unit', '--probe-inputs', code=2)


class SnapshotAndReviewTests(RepoTest):
    def test_prepare_is_compact_unless_full(self):
        compact = self.cli('evidence', 'prepare', 'validator:unit')
        self.assertNotIn('manifest', compact['snapshot'])
        self.assertGreater(compact['snapshot']['files'], 0)
        full = self.cli('evidence', 'prepare', 'validator:unit', '--full')['snapshot']
        self.assertEqual(len(full['manifest']), compact['snapshot']['files'])
        both = self.cli('evidence', 'prepare', 'validator:unit', 'observation:review')
        self.assertEqual([x['check'] for x in both['snapshots']], ['validator:unit', 'observation:review'])
        self.assertNotIn('snapshot', both)

    def test_inline_review_text_becomes_a_dated_note(self):
        before = self.prepare(check='observation:review')
        args = ('evidence', 'record', 'observation:review', '--snapshot', before['id'], '--outcome', 'PASS',
                '--reviewer', 'user', '--reviewer-kind', 'human')
        missing = self.cli(*args, '--review-note', 'docs/evidence/none.md', '--log', 'regenerate:the review', code=2)
        self.assertIn('--review-text', missing['findings'][0]['message'])
        self.write('docs/evidence/undated.md', 'Looks right.\n')
        undated = self.cli(*args, '--review-note', 'docs/evidence/undated.md', '--log', 'docs/evidence/undated.md', code=2)
        self.assertIn('has no YYYY-MM-DD date', undated['findings'][0]['message'])
        both = self.cli(*args, '--review-note', 'docs/evidence/undated.md', '--review-text', 'Fine.', code=2)
        self.assertIn('exactly one of --review-note PATH', both['findings'][0]['message'])
        output = self.cli(*args, '--review-text', 'Played the whole flow; accepted.', '--write-proposed')
        note = output['record']['review_note']
        self.assertRegex(note, r'^docs/evidence/\d{4}-\d{2}-\d{2}-review-review-[0-9a-f]{8}\.md$')
        self.assertEqual(output['record']['log'], note)
        self.assertIn(note, output['written'])
        text = (self.root / note).read_text()
        self.assertRegex(text, r'Date: \d{4}-\d{2}-\d{2}\nReviewer: user \(human\)\n\nPlayed the whole flow; accepted.\n')
        self.carry(output)
        self.assertEqual(self.cli('evidence', 'find', 'observation:review')['checks'][0]['status'], 'fresh')
        self.cli('evidence', 'record', 'validator:unit', '--snapshot', self.prepare()['id'], '--outcome', 'PASS',
                 '--command', 'true', '--exit', '0', '--log', 'regenerate:unit', '--review-text', 'no reviewer', code=2)
