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
        value = self.call('query', '--delegation', delegation, '--tree', 'current', '--json', json_output=True)
        if not isinstance(value, dict) or value.get('tree') != tree or not isinstance(value.get('results'), list):
            raise Invalid('Delegation tree changed or query is malformed; prepare and run a new check.')
        matches = [x for x in value['results'] if x.get('id') == result_id]
        if len(matches) != 1:
            raise Invalid('Registered result is missing/ambiguous for the current tree.')
        result = matches[0]
        if result.get('validator') != validator or result.get('tree') != tree or result.get('stable') is not True:
            raise Invalid('Result is unstable, from another tree, or not the named registered validator.')
        return result
