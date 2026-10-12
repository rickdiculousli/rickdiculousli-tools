import copy
import difflib
import json
import os
from pathlib import Path
from .git import confined
from .model import Invalid

# A closed grammar keeps misspelled authorization from becoming policy.
SCHEMA = {
    'state': {'state': str},
    'goals and ownership': {'path': str, 'milestone-policy': str, 'task-refinement': str,
        'task-completion': str, 'milestone-completion': str, 'goal-signoff': str},
    'goals format': {'markers': dict},
    'continuation': {'handoff': str, 'archive': str, 'findings': list, 'evidence': str,
                     'non-code': list, 'handoff-budget': int},
    'startup': {'command': str, 'effects': list, 'context': str, 'readiness': str},
    'capabilities': {'tags': dict},
    'evidence': {'checks': dict, 'inputs': dict, 'delegation-script': str,
                 'delegation-env': str, 'validator-policy': str},
    'batch': {'tasks': int, 'blocker-resolutions': int, 'quota': bool, 'quota-script': str, 'quota-env': str},
    'integration': {'steps': list, 'target': str, 'remote': str, 'sync': str,
                    'stop-conditions': list, 'authorization': str},
}
DEFAULTS = {
    'state': {'state': 'active'},
    'goals and ownership': {'path': 'docs/goals.md', 'milestone-policy': 'user',
        'task-refinement': 'agent', 'task-completion': 'agent',
        'milestone-completion': 'agent', 'goal-signoff': 'user'},
    'goals format': {'markers': {'current': '— current', 'done': '— done',
                                'shelved': '— shelved', 'dropped': '— dropped'}},
    'continuation': {'handoff': 'docs/handoff.md', 'archive': 'docs/goals-archive',
        'findings': [], 'evidence': 'docs/evidence', 'handoff-budget': 80},
    'startup': {}, 'capabilities': {'tags': {'any': []}},
    'evidence': {'checks': {}, 'inputs': {}},
    'batch': {'tasks': 1, 'blocker-resolutions': 1, 'quota': False},
    'integration': {'steps': [], 'stop-conditions': []},
}


def suggested(value, choices):
    matches = difflib.get_close_matches(value, choices, n=1)
    return '; perhaps ' + matches[0] if matches else ''


def parse(text):
    data = copy.deepcopy(DEFAULTS)
    sections, keys, section = set(), set(), None
    schema_valid = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or (line.startswith('<!--') and line.endswith('-->')):
            continue
        if line.startswith('# ') and not line.startswith('## '):
            continue
        if line.startswith('## '):
            section = line[3:].strip().lower()
            if section not in SCHEMA and section != 'schema':
                raise Invalid(f'Overlay line {number}: unknown heading {section}' + suggested(section, SCHEMA))
            if section in sections:
                raise Invalid(f'Overlay line {number}: duplicate heading {section}')
            sections.add(section)
            keys = set()
            continue
        if section == 'schema':
            if line != '1' or keys:
                raise Invalid('Overlay schema must contain exactly 1.')
            keys.add('version')
            schema_valid = True
            continue
        if section is None or ':' not in line:
            raise Invalid(f'Overlay line {number}: expected key: JSON value under a named heading.')
        key, raw_value = line.removeprefix('- ').split(':', 1)
        key = key.strip().lower()
        if key not in SCHEMA[section]:
            raise Invalid(f'Overlay line {number}: unknown key {key}' + suggested(key, SCHEMA[section]))
        if key in keys:
            raise Invalid(f'Overlay line {number}: duplicate key {key}')
        keys.add(key)
        try:
            value = json.loads(raw_value)
        except ValueError:
            raise Invalid(f'Overlay line {number}: invalid JSON value for {key}') from None
        if type(value) is not SCHEMA[section][key]:
            raise Invalid(f'Overlay line {number}: wrong type for {key}')
        data[section][key] = value
    if 'schema' in sections and not schema_valid:
        raise Invalid('Overlay Schema heading requires 1.')
    validate(data)
    return data


def validate(data):
    name = data['startup'].get('readiness')
    if name and name.startswith('cache:'):
        from .readiness import cache_name
        cache_name(name)
    if data['state']['state'] not in ('active', 'dormant'):
        raise Invalid('State must be active or dormant.')
    for key, value in data['goals and ownership'].items():
        if key != 'path' and value not in ('user', 'agent'):
            raise Invalid('Ownership must be user or agent: ' + key)
    c = data['continuation']
    for key in ('findings', 'non-code'):
        if key in c and not all(isinstance(x, str) for x in c[key]):
            raise Invalid(key + ' must contain paths.')
    if c['handoff-budget'] <= 0 or data['batch']['tasks'] <= 0 or data['batch']['blocker-resolutions'] <= 0:
        raise Invalid('Budgets must be positive integers.')
    markers = data['goals format']['markers']
    if set(markers) != {'current', 'done', 'shelved', 'dropped'} or not all(isinstance(x, str) and x for x in markers.values()) or len(set(markers.values())) != 4:
        raise Invalid('Markers require four distinct literal strings: current, done, shelved, dropped.')
    data['capabilities']['tags'].setdefault('any', [])
    if data['capabilities']['tags']['any']:
        raise Invalid('The built-in any tag has no preparation requirements.')
    for tag, levels in data['capabilities']['tags'].items():
        if not isinstance(levels, list) or not all(isinstance(x, str) for x in levels):
            raise Invalid('Capability tags map to lists of readiness level names.')
    steps = data['integration']['steps']
    allowed = ['validate', 'commit', 'merge', 'push', 'sync']
    if any(x not in allowed for x in steps) or steps != sorted(set(steps), key=allowed.index):
        raise Invalid('Integration steps must be unique and ordered validate, commit, merge, push, sync.')
    if steps and not data['integration'].get('authorization', '').strip():
        raise Invalid('Integration steps require a recorded authorization description.')
    if any(x in steps for x in ('merge', 'push')) and not data['integration'].get('target'):
        raise Invalid('Merge/push requires a named target.')
    if 'push' in steps and not data['integration'].get('remote'):
        raise Invalid('Push requires a named remote.')
    if 'sync' in steps and not data['integration'].get('sync'):
        raise Invalid('Sync requires its configured operation.')
    for name, spec in data['evidence']['checks'].items():
        if not isinstance(spec, dict) or set(spec) - {'scope', 'inputs', 'domain', 'allowed-skips', 'validator', 'reviewer'}:
            raise Invalid('Invalid check definition: ' + name)
        if 'reviewer' in spec and (not name.startswith('observation:') or spec['reviewer'] not in ('human', 'any')):
            raise Invalid('Check reviewer must be "human" or "any", on observation: checks only: ' + name)
        for key in ('scope', 'inputs', 'allowed-skips'):
            if key in spec and (not isinstance(spec[key], list) or not all(isinstance(x, str) for x in spec[key])):
                raise Invalid('Check ' + key + ' must be a string list.')
        for key in ('domain', 'validator'):
            if key in spec and not isinstance(spec[key], str):
                raise Invalid('Check ' + key + ' must be a string.')
        for value in spec.get('inputs', []):
            if value not in data['evidence']['inputs']:
                raise Invalid('Undeclared input: ' + value)
    for name, spec in data['evidence']['inputs'].items():
        if not isinstance(spec, dict) or set(spec) != {'command', 'timeout', 'recover'}:
            raise Invalid('Input requires command (argv), timeout, recover: ' + name)
        if not isinstance(spec['command'], list) or not spec['command'] or not all(isinstance(x, str) for x in spec['command']):
            raise Invalid('Input command must be an argv string list.')
        if type(spec['timeout']) not in (int, float) or not 0 < spec['timeout'] <= 60 or not isinstance(spec['recover'], str) or not spec['recover']:
            raise Invalid('Input requires timeout (0,60] and a recovery route.')


def load(git, overlay=None, draft_root=None, goals=None, handoff=None):
    base = Path(draft_root).resolve() if draft_root else git.root
    path = Path(overlay) if overlay else git.root / '.agents/long-horizon.md'
    if not path.is_absolute():
        path = git.root / path
    exists = path.is_file()
    data = parse(path.read_text(encoding='utf-8')) if exists else copy.deepcopy(DEFAULTS)
    data['_installed'] = exists and not draft_root
    data['_overlay'] = str(path)
    data['_base'] = str(base)
    data['_goals'] = str(confined(base, goals or data['goals and ownership']['path']))
    data['_handoff'] = str(confined(base, handoff or data['continuation']['handoff']))
    for value in [data['continuation']['archive'], data['continuation']['evidence'], *data['continuation']['findings']]:
        confined(base, value)
    if 'non-code' not in data['continuation']:
        data['continuation']['non-code'] = [data['goals and ownership']['path'], data['continuation']['handoff'],
                                           data['continuation']['archive'], *data['continuation']['findings']]
    return data


def script(data, section, name):
    literal, env = data[section].get(name + '-script'), data[section].get(name + '-env')
    if literal and env:
        raise Invalid('Choose one literal script path or environment variable.')
    value = os.environ.get(env) if env else literal
    if env and not value:
        raise Invalid('Configured environment variable is missing: ' + env)
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(data['_base']) / path
    if not path.is_file():
        raise Invalid('Configured script is missing; set a valid path: ' + str(path))
    return path
