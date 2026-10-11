"""Immutable pending proposals and reachable, independently verifiable evidence."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import time
import uuid
from .delegation import Checker
from .git import confined
from .model import Invalid, Blocked, digest, finding
from .scope import snapshot, definition, policy_digest, criterion_policy
from .state import State, atomic

HEX = re.compile(r'^[0-9a-f]{64}$')
FIELDS = {'id', 'name', 'outcome', 'scope', 'policy', 'inputs', 'domain', 'ledger', 'claim', 'detail', 'log'}
EXCEPTION_FIELDS = {'id', 'check', 'target', 'reason', 'by', 'policy', 'detail'}


def record_id(record):
    return digest({k: v for k, v in record.items() if k not in ('id', 'created', 'last_use', 'detail', 'snapshot')})


def trailer(record):
    if record.get('exception'):
        values = {k: record[k] for k in ('id', 'check', 'target', 'reason', 'by', 'policy', 'detail')}
        prefix = 'Accepted-Exception: '
    else:
        values = {k: record[k] for k in ('id', 'name', 'outcome', 'scope', 'policy', 'domain', 'claim', 'detail', 'log')}
        values['inputs'] = ','.join(k + ':' + v for k, v in sorted(record['inputs'].items())) or 'none'
        values['ledger'] = record.get('delegation') or 'none'
        prefix = 'Accepted-Check: '
    return prefix + ' '.join(k + '=' + shlex.quote(str(v)) for k, v in values.items())


def parse_trailer(line):
    exception = line.startswith('Accepted-Exception: ')
    prefix = 'Accepted-Exception: ' if exception else 'Accepted-Check: '
    if not line.startswith(prefix):
        raise Invalid('Malformed acceptance trailer prefix.')
    fields = {}
    try:
        for token in shlex.split(line[len(prefix):]):
            key, value = token.split('=', 1)
            if key in fields or not value:
                raise ValueError()
            fields[key] = value
    except ValueError:
        raise Invalid('Malformed/repeated acceptance trailer field.') from None
    if set(fields) != (EXCEPTION_FIELDS if exception else FIELDS):
        raise Invalid('Acceptance trailer fields do not match version 1.')
    if not HEX.fullmatch(fields['id']) or not HEX.fullmatch(fields['policy']):
        raise Invalid('Acceptance trailer has an invalid content ID/policy digest.')
    if not exception and (not HEX.fullmatch(fields['scope']) or fields['outcome'] not in ('PASS', 'FAIL', 'SKIP', 'UNSTABLE')):
        raise Invalid('Acceptance trailer has invalid scope/outcome.')
    return fields


def prepare(git, policy, check, attempt=None, probe=False):
    value = snapshot(git, policy, check, probe)
    if any(x is None for x in value['inputs'].values()):
        raise Invalid('External checks require --probe-inputs before and after the check.')
    value.update(version=1, check=check, criteria=criterion_policy(policy, check), attempt=attempt or uuid.uuid4().hex)
    checker = Checker(git, policy)
    if checker.path:
        value['tree'] = checker.tree()
    value['id'] = digest(value)
    state = State(git)
    # Same attempt identifies one execution; it cannot be silently retargeted.
    if state.path.exists() and state.compatible():
        for path in (state.path / 'snapshots').glob('*.json'):
            old = state.get('snapshots/' + path.name)
            if old['attempt'] == value['attempt']:
                if old['id'] != value['id']:
                    raise Invalid('Attempt contents changed; choose a new --attempt and rerun the check.')
                old['last_use'] = time.time()
                state.put('snapshots/' + old['id'] + '.json', old)
                return old
    value['created'] = value['last_use'] = time.time()
    state.put('snapshots/' + value['id'] + '.json', value, immutable=True)
    return value


def recovery(git, policy, route):
    if not route:
        raise Invalid('A persistent --log recovery route is required.')
    if route.startswith(('https://', 'http://', 'regenerate:')):
        if len(route.split(':', 1)[1].strip()) < 5:
            raise Invalid('Recovery route is not specific enough.')
        return digest(route)
    path = confined(git.root, route)
    if not path.is_file() or '.delegation' in path.parts:
        raise Invalid('Log must be a durable checkout file or a specific persistent retrieval/regeneration route.')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(git, policy, args):
    check = args.check
    definition(policy, check)
    state = State(git)
    if args.exception:
        if not args.target or not args.reason or not args.reason.strip() or not args.by or not args.by.strip():
            raise Invalid('Exception requires --target, --reason and --by after actual approval.')
        from .goals import parse, flatten
        nodes = flatten(parse(Path(policy['_goals']).read_text(encoding='utf-8'), policy)['goals'])
        if args.target not in nodes or check not in nodes[args.target]['checks']:
            raise Invalid('Exception target must require this named check.')
        value = {'version': 1, 'exception': True, 'check': check, 'target': args.target,
                 'reason': args.reason, 'by': args.by, 'policy': policy_digest(policy, check), 'criteria': criterion_policy(policy, check)}
    else:
        if not args.snapshot or not args.outcome:
            raise Invalid('Record requires --snapshot and --outcome.')
        before = state.get('snapshots/' + args.snapshot + '.json')
        if not before or before.get('check') != check:
            raise Invalid('Snapshot is missing or for another check; run evidence prepare.')
        after = snapshot(git, policy, check, args.probe_inputs)
        stable = all(before[key] == after[key] for key in ('scope', 'policy', 'inputs', 'domain'))
        if any(v is None for v in after['inputs'].values()):
            raise Invalid('External record requires --probe-inputs.')
        modes = [bool(args.command), bool(args.delegation), bool(args.reviewer)]
        if sum(modes) != 1:
            raise Invalid('Choose exactly one provenance: command/exit, delegation/result, or reviewer/review-note.')
        value = {'version': 1, 'name': check, 'outcome': args.outcome, 'scope': before['scope'],
                 'policy': before['policy'], 'inputs': before['inputs'],
                 'domain': args.domain or before['domain'], 'attempt': before['attempt'],
                 'snapshot': before['id'], 'criteria': before['criteria'], 'stable': stable, 'log': args.log,
                 'log_digest': recovery(git, policy, args.log)}
        if args.command:
            if args.exit is None:
                raise Invalid('Solo provenance requires --exit.')
            value.update(command=args.command, exit=args.exit, claim='observed')
        elif args.reviewer:
            if not check.startswith('observation:') or not args.review_note:
                raise Invalid('Human provenance requires observation:<name> and --review-note.')
            note = confined(git.root, args.review_note)
            if not note.is_file() or not re.search(r'\b\d{4}-\d{2}-\d{2}\b', note.read_text(encoding='utf-8')):
                raise Invalid('Review note must be a durable dated file.')
            value.update(reviewer=args.reviewer, review_note=args.review_note,
                         review_digest=hashlib.sha256(note.read_bytes()).hexdigest(), exit=0, claim='reviewed')
        else:
            if not args.result or not before.get('tree'):
                raise Invalid('Delegated record requires --result and a snapshot prepared with its checker.')
            result = Checker(git, policy).result(args.delegation, args.result,
                         definition(policy, check).get('validator', check.removeprefix('validator:')), before['tree'])
            value.update(delegation=args.delegation, result=args.result, tree=before['tree'],
                         command=result['command'], exit=result['exit'], claim='checked', result_digest=digest(result))
            if args.outcome == 'PASS' and (result.get('ok') is not True or result.get('timed_out')):
                raise Blocked('Delegated failure/timeout cannot be recorded as PASS.')
        if args.outcome == 'PASS' and (not stable or value['exit'] != 0):
            raise Blocked('PASS requires stable before/after scope, policy, inputs and exit 0; record FAIL/UNSTABLE or rerun.')
    value['id'] = record_id(value)
    detail = args.detail or policy['continuation']['evidence'].rstrip('/') + '/' + value['id'] + '.json'
    confined(git.root, detail)
    value['detail'] = detail
    value['created'] = time.time()
    existing = state.get('evidence/' + value['id'] + '.json')
    if existing:
        value = existing
    state.put('evidence/' + value['id'] + '.json', value, immutable=True)
    if not args.exception:
        before['last_use'] = time.time()
        state.put('snapshots/' + before['id'] + '.json', before)
    output = trailer(value) + '\n'
    if args.trailers_file:
        atomic(Path(args.trailers_file), output.encode(), raw=True)
    return {'record': value, 'trailer': output.strip(), 'proposed_files': {value['detail']: json.dumps(value, sort_keys=True, indent=2) + '\n'}, 'pending': True}



def validate_durable(git, commit, value):
    if value.get('version') != 1:
        raise Invalid('Unknown evidence version.')
    if value.get('exception'):
        if any(not value.get(key) for key in ('check', 'target', 'reason', 'by')):
            raise Invalid('Incomplete accepted exception.')
        return
    if value.get('claim') not in ('observed', 'checked', 'reviewed') or type(value.get('stable')) is not bool:
        raise Invalid('Evidence provenance/stability is invalid.')
    if value.get('outcome') == 'PASS' and (not value['stable'] or value.get('exit') != 0):
        raise Invalid('PASS is unstable or exited nonzero.')
    if value['claim'] in ('observed', 'checked') and not value.get('command'):
        raise Invalid('Observed command is missing.')
    if value['claim'] == 'checked' and any(not value.get(k) for k in ('delegation', 'result', 'tree', 'result_digest')):
        raise Invalid('Checked result provenance is incomplete.')
    route = value.get('log', '')
    if route.startswith(('https://', 'http://', 'regenerate:')):
        if digest(route) != value.get('log_digest'):
            raise Invalid('Log recovery route digest mismatch.')
    else:
        path = confined(git.root, route).relative_to(git.root).as_posix()
        content = git.run('show', commit + ':' + path, binary=True, check=False)
        if not git.run('ls-tree', commit, '--', path).strip() or hashlib.sha256(content).hexdigest() != value.get('log_digest'):
            raise Invalid('Durable log is missing or altered.')
    if value['claim'] == 'reviewed':
        path = confined(git.root, value['review_note']).relative_to(git.root).as_posix()
        content = git.run('show', commit + ':' + path, binary=True, check=False)
        if not value.get('reviewer') or not re.search(rb'\b\d{4}-\d{2}-\d{2}\b', content) or hashlib.sha256(content).hexdigest() != value.get('review_digest'):
            raise Invalid('Dated review note is missing/altered.')


def committed(git):
    records, findings = [], []
    seen = set()
    # Reverse topological traversal identifies original introduction, not duplicate carrying commits.
    commits = git.run('rev-list', '--reverse', '--topo-order', 'HEAD', check=False).splitlines()
    for commit in commits:
        message = git.run('show', '-s', '--format=%B', commit)
        for line in message.splitlines():
            if not line.startswith(('Accepted-Check:', 'Accepted-Exception:')):
                continue
            try:
                fields = parse_trailer(line)
                if fields['id'] in seen:
                    continue
                path = confined(git.root, fields['detail']).relative_to(git.root).as_posix()
                value = json.loads(git.read(commit, path))
                validate_durable(git, commit, value)
                if record_id(value) != fields['id'] or parse_trailer(trailer(value)) != fields:
                    raise Invalid('Trailer/detail content mismatch.')
                seen.add(value['id'])
                value = dict(value, carrying_commit=commit, pending=False)
                records.append(value)
            except (Invalid, ValueError, KeyError, TypeError):
                findings.append(finding('evidence-corrupt', 'Committed acceptance trailer/detail is invalid.', 'Inspect acceptance records in commit ' + commit + ' and record new reviewed evidence.'))
    return records, findings


def candidates(git, pending):
    records, findings = committed(git)
    known = {x['id'] for x in records}
    state = State(git)
    for id_ in pending:
        if not HEX.fullmatch(id_):
            raise Invalid('Pending evidence ID must be SHA-256.')
        if id_ in known:
            continue
        value = state.get('evidence/' + id_ + '.json')
        if not value or record_id(value) != id_:
            findings.append(finding('pending-missing', 'Explicit pending record is missing/invalid.', 'Prepare and record a new check.'))
        else:
            records.append(dict(value, pending=True, carrying_commit=None))
    return records, findings


def find(git, policy, check=None, probe=False, pending=()):
    records, findings = candidates(git, pending)
    result = []
    names = [check] if check else list(policy['evidence']['checks'])
    for name in names:
        current = snapshot(git, policy, name, probe)
        matching = [x for x in records if not x.get('exception') and x.get('name') == name and
                    all(x.get(key) == current[key] for key in ('scope', 'policy', 'domain'))]
        matching = [x for x in matching if x['inputs'] == current['inputs']]
        maximal = [x for x in matching if not any(x is not y and
                   (y['pending'] and not x['pending'] or
                    x['carrying_commit'] and y['carrying_commit'] and
                    x['carrying_commit'] != y['carrying_commit'] and git.ancestor(x['carrying_commit'], y['carrying_commit'])) for y in matching)]
        status = 'unknown' if any(x is None for x in current['inputs'].values()) else 'missing'
        accepted = None
        if maximal:
            if len(maximal) > 1 and len({x['outcome'] for x in maximal}) > 1:
                status = 'conflict'
                findings.append(finding('evidence-conflict', 'Incomparable acceptance outcomes require a new run.', 'Prepare and run a reviewed check after integration.'))
            else:
                accepted = maximal[-1]
                outcome = accepted['outcome']
                status = 'fresh' if outcome == 'PASS' and accepted.get('stable') is True and accepted.get('exit') == 0 else outcome.lower()
        elif any(x.get('name') == name for x in records) and status != 'unknown':
            status = 'stale'
        result.append({'check': name, 'status': status, 'record': accepted,
                       'recovery': 'evidence prepare ' + name + (' --probe-inputs' if current['inputs'] else '')})
    return {'checks': result, 'records': records}, findings


def cleanup(git, commit, ids):
    oid = git.oid(commit)
    if not oid or not git.ancestor(oid):
        raise Invalid('Cleanup commit must be reachable from this worktree HEAD.')
    durable, findings = committed(git)
    carried = {x['id'] for x in durable if x['carrying_commit'] == oid}
    # A duplicate carrying commit is allowed only if it contains the exact verified trailer/detail.
    message = git.run('show', '-s', '--format=%B', oid)
    for record in durable:
        if trailer(record) in message.splitlines() and git.read(oid, record['detail']):
            carried.add(record['id'])
    if any(id_ not in carried for id_ in ids) or findings:
        raise Invalid('Resolve every pending ID in this exact durable carrying commit before cleanup.')
    state = State(git)
    removed = []
    from .state import lock, read
    with lock(state.root):
        if not state.compatible():
            raise Invalid('Worktree identity changed; refusing pending cleanup.')
        for id_ in ids:
            path = state.path / 'evidence' / (id_ + '.json')
            if path.is_file() and not path.is_symlink():
                value = read(path)
                path.unlink()
                removed.append(id_)
                snapshot_id = value.get('snapshot')
                others = [read(x, {}) for x in (state.path / 'evidence').glob('*.json')]
                if snapshot_id and not any(x.get('snapshot') == snapshot_id for x in others):
                    source = state.path / 'snapshots' / (snapshot_id + '.json')
                    if source.is_file() and not source.is_symlink():
                        source.unlink()
    return {'removed': removed, 'commit': oid}
