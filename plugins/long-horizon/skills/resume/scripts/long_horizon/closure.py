import hashlib
import os
import re
from pathlib import Path
import time
from .model import Invalid, digest, finding
from .state import State, atomic, read
from .git import confined


def policy_id(policy):
    return digest(policy['integration'])


def validate_manifest(git, manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'version', 'base', 'paths', 'evidence_ids'} or manifest['version'] != 1:
        raise Invalid('Manifest requires version:1, base, paths and evidence_ids.')
    if not isinstance(manifest['paths'], list) or not isinstance(manifest['evidence_ids'], list):
        raise Invalid('Manifest paths/evidence_ids must be arrays.')
    if not manifest['paths'] or len({x.get('path') for x in manifest['paths'] if isinstance(x, dict)}) != len(manifest['paths']):
        raise Invalid('Manifest requires unique nonempty owned paths.')
    if any(not isinstance(x, str) or not re.fullmatch(r'[0-9a-f]{64}', x) for x in manifest['evidence_ids']):
        raise Invalid('Manifest evidence IDs must be SHA-256.')
    for item in manifest['paths']:
        if not isinstance(item, dict) or set(item) != {'path', 'digest'}:
            raise Invalid('Manifest paths require path and digest (SHA-256 or null deletion).')
        confined(git.root, item['path'])
        if item['digest'] is not None and (not isinstance(item['digest'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['digest'])):
            raise Invalid('Manifest content digest must be SHA-256 or null.')
    return digest({'evidence_ids': sorted(manifest['evidence_ids']), 'paths': sorted(manifest['paths'], key=lambda x: x['path'])})


def content_matches(git, commit, manifest):
    changed = git.run('diff', '--name-only', manifest['base'], commit).splitlines() if git.oid(manifest['base']) else git.run('diff-tree', '--root', '--no-commit-id', '--name-only', '-r', commit).splitlines()
    expected = {x['path'] for x in manifest['paths']}
    if set(changed) != expected:
        return False
    for item in manifest['paths']:
        exists = bool(git.run('ls-tree', commit, '--', item['path']).strip())
        if not exists:
            if item['digest'] is not None:
                return False
            continue
        # The manifest hashes worktree bytes; with eol conversion they match the checked-out form, not the blob.
        stored = git.run('show', commit + ':' + item['path'], binary=True, check=False)
        if hashlib.sha256(stored).hexdigest() != item['digest']:
            checkout = git.run('cat-file', '--filters', commit + ':' + item['path'], binary=True, check=False)
            if hashlib.sha256(checkout).hexdigest() != item['digest']:
                return False
    return True


def manifest(git, policy, base, paths=(), pending=None, output=None):
    """Build the reviewed batch manifest from the worktree, for closure record --manifest."""
    oid = git.oid(base)
    if not oid:
        raise Invalid('Base must name an existing pre-batch commit.')
    spec = ['--', *paths] if paths else []
    names = set(x for x in git.run('diff', '--name-only', '-z', '--no-renames', oid, *spec, binary=True).split(b'\0') if x)
    names |= set(x for x in git.run('ls-files', '--others', '--exclude-standard', '-z', *spec, binary=True).split(b'\0') if x)
    items = []
    for raw in sorted(names):
        name = raw.decode('utf-8', 'surrogateescape')
        path = git.root / name
        if path.is_symlink():
            data = os.fsencode(os.readlink(path))
        elif path.is_file():
            data = path.read_bytes()
        elif path.exists():
            raise Invalid('Unsupported changed entry: ' + name)
        else:
            data = None
        items.append({'path': name, 'digest': hashlib.sha256(data).hexdigest() if data is not None else None})
    if not items:
        raise Invalid('No changed paths since ' + base + '; nothing to close.')
    from .evidence import find, local_pending
    unused = []
    if pending is None:
        # Default to pending records that currently accept their check; stale ones are listed, not included.
        ids = [x['id'] for x in local_pending(git)]
        checks = find(git, policy, pending=ids)[0]['checks']
        accepted = [x['record']['id'] for x in checks if x['status'] == 'fresh' and x['pending']]
        unused = [x for x in ids if x not in accepted]
        ids = accepted
    else:
        ids = list(dict.fromkeys(pending))
    value = {'version': 1, 'base': oid, 'paths': items, 'evidence_ids': ids}
    batch = validate_manifest(git, value)
    result = {'manifest': value, 'batch': batch, 'unused_pending': unused}
    if output:
        target = Path(output).resolve()
        if target == git.root or git.root in target.parents:
            raise Invalid('Write the manifest outside the checkout; inside it would join the batch.')
        atomic(target, value)
        result['path'] = str(target)
    else:
        # Manifests are not check snapshots; keep them out of the snapshot scan.
        state = State(git)
        state.put('manifests/' + batch + '.json', value)
        result['path'] = str(state.path / 'manifests' / (batch + '.json'))
    return result


def record(git, policy, args):
    integration = policy['integration']
    if args.step not in integration['steps'] or not integration.get('authorization'):
        raise Invalid('Closure step is not authorized by recorded integration policy.')
    state = State(git)
    saved = state.get('closure.json')
    if saved and args.new_batch:
        previous, errors = verify(git, policy)
        if previous['state'] != 'complete' or any(x.code != 'closure-policy' for x in errors):
            raise Invalid('Prior closure is unfinished; recover it before starting a new batch.')
        state.put('snapshots/closure-' + saved['batch'] + '.json', dict(saved, created=time.time()), immutable=True)
        saved = None
    if not saved:
        if not args.manifest:
            raise Invalid('First closure record requires --manifest reviewed-paths.json.')
        manifest = read(args.manifest)
        batch = validate_manifest(git, manifest)
        if args.batch != batch:
            raise Invalid('Batch ID must be the evidence/path manifest digest: ' + batch)
        saved = {'version': 1, 'batch': batch, 'manifest': manifest, 'policy': policy_id(policy),
                 'branch': git.branch(), 'target': integration.get('target'), 'remote': integration.get('remote'),
                 'steps': integration['steps'], 'observations': {}}
    if saved['batch'] != args.batch or saved['policy'] != policy_id(policy):
        raise Invalid('Conflicting batch/policy; preserve prior successful closure and explicitly start a new record after recovery.')
    position = saved['steps'].index(args.step)
    if args.outcome == 'success' and any(saved['observations'].get(x, {}).get('outcome') != 'success' for x in saved['steps'][:position]):
        raise Invalid('Prior ordered steps are unfinished; resume the first unfinished operation.')
    observation = {'outcome': args.outcome, 'commit': git.oid(args.commit) if args.commit else None,
                   'integrated_commit': git.oid(args.integrated_commit) if args.integrated_commit else None,
                   'observation': args.observation, 'at': time.time()}
    if args.outcome == 'success':
        if args.step in ('commit', 'merge', 'push') and not observation['commit']:
            raise Invalid('Successful Git step needs its exact --commit OID.')
        if args.step == 'commit' and (not git.ancestor(observation['commit']) or not content_matches(git, observation['commit'], saved['manifest'])):
            raise Invalid('Batch commit is unreachable or does not contain exactly the reviewed owned changes.')
        if args.step in ('merge', 'push'):
            batch_commit = saved['observations'].get('commit', {}).get('commit')
            if observation['commit'] != batch_commit:
                raise Invalid('Git closure must identify the same exact batch commit.')
            integrated = observation['integrated_commit'] or batch_commit
            if observation['integrated_commit'] and not content_matches(git, integrated, saved['manifest']):
                raise Invalid('Explicit squash mapping needs matching reviewed contents.')
            if args.step == 'merge' and not git.ancestor(integrated, 'refs/heads/' + saved['target']):
                raise Invalid('Integrated commit is not contained in the local target branch.')
            if args.step == 'push' and not args.observation:
                raise Invalid('Push success requires its observed command result; local refs alone are insufficient.')
        if args.step == 'sync' and not args.observation:
            raise Invalid('Sync requires an observed result; Git cannot verify it.')
        if args.step == 'validate':
            from .evidence import find
            data, errors = find(git, policy, pending=saved['manifest']['evidence_ids'])
            ids = {x['record']['id'] for x in data['checks'] if x['status'] == 'fresh' and x['record']}
            if any(x not in ids for x in saved['manifest']['evidence_ids']) or errors:
                raise Invalid('Validation manifest lacks verifiable fresh evidence.')
    old = saved['observations'].get(args.step)
    if old and old['outcome'] == 'success':
        if any(old.get(k) != observation[k] for k in ('outcome', 'commit', 'integrated_commit', 'observation')):
            raise Invalid('Successful step is immutable; verify and continue rather than overwriting it.')
        return saved
    saved['observations'][args.step] = observation
    state.put('closure.json', saved)
    return saved


def verify(git, policy, path=None):
    saved = read(path) if path else State(git).get('closure.json')
    if not saved:
        return {'state': 'none', 'steps': [], 'next': None}, []
    if not isinstance(saved, dict) or not isinstance(saved.get('steps'), list) or not isinstance(saved.get('observations'), dict) or not isinstance(saved.get('manifest'), dict):
        raise Invalid('Closure record is malformed; recover the explicitly chosen version-1 JSON.')
    if any(x not in ('validate', 'commit', 'merge', 'push', 'sync') for x in saved['steps']) or any(not isinstance(x, dict) for x in saved['observations'].values()):
        raise Invalid('Closure step/observation schema is malformed.')
    if validate_manifest(git, saved['manifest']) != saved.get('batch'):
        raise Invalid('Closure batch identity does not match its reviewed manifest.')
    findings, steps = [], []
    if saved.get('version') != 1 or saved.get('policy') != policy_id(policy):
        findings.append(finding('closure-policy', 'Closure policy changed or record is malformed.', 'Recover the original batch policy explicitly; do not overwrite success.'))
    commit = saved.get('observations', {}).get('commit', {}).get('commit')
    mapping = saved.get('observations', {}).get('merge', {}).get('integrated_commit') or commit
    for step in saved.get('steps', []):
        observation = saved.get('observations', {}).get(step, {})
        verified = observation.get('outcome') == 'success'
        detail = observation.get('observation')
        if step == 'commit':
            verified = bool(commit and git.oid(commit) and git.ancestor(commit) and content_matches(git, commit, saved['manifest']))
        elif step == 'merge':
            verified = bool(mapping and saved.get('target') and git.ancestor(mapping, 'refs/heads/' + saved['target']))
        elif step == 'push':
            ref = 'refs/remotes/' + str(saved.get('remote')) + '/' + str(saved.get('target'))
            oid = git.oid(ref)
            verified = bool(verified and mapping and oid and git.ancestor(mapping, oid))
            detail = {'ref': ref, 'oid': oid, 'as_of_local_observation': time.time(),
                      'push_observation': observation.get('observation')}
        elif step == 'sync':
            verified = bool(verified and detail)
        steps.append({'step': step, 'verified': verified, 'observation': detail})
    next_step = next((x['step'] for x in steps if not x['verified']), None)
    if next_step:
        findings.append(finding('closure-unfinished', 'Batch closure remains unfinished: ' + next_step,
            'Perform the authorized ' + next_step + ' operation for batch ' + saved['batch'] + ', record its actual outcome, then closure verify.'))
    return {'state': 'unfinished' if next_step else 'complete', 'batch': saved['batch'], 'steps': steps,
            'next': next_step, 'state_directory': str(State(git).path)}, findings
