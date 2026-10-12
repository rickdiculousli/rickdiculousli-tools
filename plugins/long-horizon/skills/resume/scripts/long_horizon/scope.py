import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
from .model import Invalid, digest
from .goals import parse, flatten


def noncode(name, policy):
    paths = policy['continuation']['non-code'] + [policy['continuation']['evidence']]
    return any(name == path.rstrip('/') or name.startswith(path.rstrip('/') + '/') for path in paths)


def definition(policy, check):
    checks = policy['evidence']['checks']
    if check not in checks:
        raise Invalid('Unknown check ' + check + '; declare it in Evidence checks.')
    return checks[check]


def criterion_policy(policy, check):
    spec = definition(policy, check)
    path = Path(policy['_goals'])
    parsed = parse(path.read_text(encoding='utf-8') if path.exists() else '', policy)
    nodes = list(flatten(parsed['goals']).values())
    # Compression preserves criterion identity; archived children remain policy.
    for goal in parsed['goals']:
        if not goal['children'] and goal['metadata'].get('Archive'):
            from .gate import archive
            try:
                saved = archive(goal, policy)
                for child in saved['milestones']:
                    nodes.append({'id': child['id'], 'criteria': child['criteria'],
                                  'checks': sorted(set(child.get('checks', [])))})
            except (Invalid, OSError, ValueError, KeyError, TypeError):
                raise Invalid('Archived criteria are not verifiable; restore roadmap or repair the archive.') from None
    criteria = sorted([{'id': x['id'], 'criteria': ' '.join(x['criteria'].split()), 'checks': x['checks']}
                for x in nodes if check in x['checks']], key=lambda x: x['id'])
    return criteria


def policy_digest(policy, check, criteria=None):
    spec = definition(policy, check)
    criteria = criterion_policy(policy, check) if criteria is None else criteria
    validator = policy['evidence'].get('validator-policy')
    if not validator and (policy['evidence'].get('delegation-script') or policy['evidence'].get('delegation-env')):
        validator = '.agents/delegation.md'
    validator_content = None
    if validator:
        source = Path(policy['_base']) / validator
        if not source.is_file():
            raise Invalid('Validator policy is missing: ' + validator)
        validator_content = hashlib.sha256(source.read_bytes()).hexdigest()
    return digest({'definition': spec, 'criteria': criteria,
        'inputs': {name: policy['evidence']['inputs'][name] for name in spec.get('inputs', [])},
        'scope_exclusions': policy['continuation']['non-code'] + [policy['continuation']['evidence']],
        'validator_policy': validator_content})


def snapshot(git, policy, check, probe=False):
    spec = definition(policy, check)
    includes = spec.get('scope', [])
    args = includes or ['.', *[':(exclude)' + name for name in policy['continuation']['non-code'] + [policy['continuation']['evidence']]]]
    # Git itself interprets pathspecs, including magic/globs and exclusions.
    listed = git.run('ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', *args, binary=True)
    paths = sorted(set(x for x in listed.split(b'\0') if x))
    staged = git.run('ls-files', '--stage', '-z', binary=True)
    index = {}
    for entry in staged.split(b'\0'):
        if entry:
            meta, path = entry.split(b'\t', 1)
            mode, oid, stage = meta.split()
            if stage != b'0':
                raise Invalid('Unresolved index conflicts; resolve them before preparing evidence.')
            index[path] = (mode.decode(), oid.decode())
    items = []
    for raw in paths:
        name = raw.decode('utf-8', 'surrogateescape')
        path = git.root / name
        indexed = index.get(raw)
        if indexed and indexed[0] == '160000':
            if not path.is_dir():
                raise Invalid('Submodule unavailable; initialize or model its contents as inputs.')
            result = subprocess.run(['git', '-C', str(path), 'status', '--porcelain'], capture_output=True, timeout=10, env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
            oid = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, timeout=10)
            if result.returncode or result.stdout or oid.returncode:
                raise Invalid('Dirty/unavailable submodule cannot establish freshness.')
            items.append([name, '160000', oid.stdout.decode().strip()])
            continue
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue  # deletion changes the manifest
        if stat.S_ISLNK(info.st_mode):
            content = os.fsencode(os.readlink(path))
            mode = '120000'
        elif stat.S_ISREG(info.st_mode):
            content = path.read_bytes()
            mode = '100755' if info.st_mode & 0o111 else '100644'
        else:
            raise Invalid('Unsupported/unreadable scope entry: ' + name)
        # --path applies the checkout's eol/clean rules, so CRLF and LF checkouts of one commit agree.
        where = ['--path', name] if mode != '120000' else []
        oid = git.run('hash-object', *where, '--stdin', binary=True, input=content).decode().strip()
        items.append([name, mode, oid])
    inputs = {}
    for name in spec.get('inputs', []):
        if not probe:
            inputs[name] = None
            continue
        configured = policy['evidence']['inputs'][name]
        try:
            result = subprocess.run(configured['command'], cwd=git.root, capture_output=True,
                                    text=True, timeout=configured['timeout'])
        except (OSError, subprocess.TimeoutExpired):
            raise Invalid('Input probe failed for ' + name + '; recover: ' + configured['recover']) from None
        if result.returncode or not re.fullmatch(r'[0-9a-f]{64}\n?', result.stdout):
            raise Invalid('Input probe must return one SHA-256 token: ' + name + '; recover: ' + configured['recover'])
        inputs[name] = result.stdout.strip()
    return {'scope': digest(items), 'policy': policy_digest(policy, check), 'inputs': inputs,
            'domain': spec.get('domain', 'default'), 'manifest': items}
