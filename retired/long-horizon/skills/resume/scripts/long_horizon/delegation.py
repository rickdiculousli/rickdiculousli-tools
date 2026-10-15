import json
import re
import subprocess
import sys
from .overlay import script
from .model import Invalid


class Checker:
    def __init__(self, git, policy):
        self.git = git
        self.path = script(policy, 'evidence', 'delegation')

    def call(self, *args, json_output=False):
        if self.path is None:
            raise Invalid('Delegation is not configured; use solo observed provenance or declare its checker path.')
        try:
            result = subprocess.run([sys.executable, str(self.path), '--root', str(self.git.root), *args],
                                    text=True, capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise Invalid('Delegation checker unavailable/timed out; recover its configured installation.') from None
        if result.returncode:
            raise Invalid('Delegation checker rejected ' + args[0] + '; run its lint and recover pending work.')
        if json_output:
            try:
                return json.loads(result.stdout)
            except ValueError:
                raise Invalid('Delegation checker returned malformed JSON.') from None
        return result.stdout.strip()

    def tree(self):
        value = self.call('tree')
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', value):
            raise Invalid('Delegation tree output is malformed.')
        return value

    def pending(self):
        value = self.call('pending', '--json', json_output=True)
        if not isinstance(value, dict) or not isinstance(value.get('pending'), list):
            raise Invalid('Delegation pending output must contain a pending array.')
        return value['pending']

    def result(self, delegation, result_id, validator, tree):
        """The registered result `result_id` (or its run number) of `delegation`, run at exactly `tree`.

        The snapshot fixed `tree` when it was prepared and record checks the check's scope is
        unchanged since, so later edits outside that scope (evidence files, goals, review notes)
        do not invalidate the result.
        """
        if re.fullmatch(r'\d+', result_id or ''):
            result_id = delegation + '#' + result_id
        value = self.call('query', '--delegation', delegation, '--json', json_output=True)
        if not isinstance(value, dict) or not isinstance(value.get('results'), list):
            raise Invalid('Delegation query output is malformed; run its lint and recover pending work.')
        matches = [x for x in value['results'] if isinstance(x, dict) and x.get('id') == result_id]
        if len(matches) != 1:
            known = ', '.join(describe(x) for x in value['results'] if isinstance(x, dict)) or 'none'
            raise Invalid('Registered result ' + result_id + ' is ' + ('ambiguous' if matches else 'missing') +
                          ' for delegation ' + delegation + '; its results: ' + known + '.')
        result = matches[0]
        if result.get('tree') != tree:
            raise Invalid('Result ' + result_id + ' ran at tree ' + str(result.get('tree'))[:12] + ' but the snapshot was prepared at ' +
                          str(tree)[:12] + '. Prepare every check of a run before writing records or editing files '
                          '(evidence prepare CHECK [CHECK ...]), or rerun the validator on this tree.')
        if result.get('validator') != validator or result.get('stable') is not True:
            raise Invalid('Result is unstable or not the named registered validator.')
        return result


def describe(result):
    return '%s (%s, %s, tree %s%s)' % (result.get('id'), result.get('validator'), 'PASS' if result.get('ok') else 'FAIL',
                                       str(result.get('tree'))[:12], '' if result.get('stable') else ', unstable')
