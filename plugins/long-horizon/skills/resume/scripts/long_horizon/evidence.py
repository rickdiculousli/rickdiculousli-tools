"""Immutable pending proposals and reachable, independently verifiable evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid
from .delegation import Checker
from .git import Git, confined, path_key
from .model import Invalid, Blocked, digest, finding
from .scope import snapshot, definition, policy_digest, criterion_policy
from .state import State, atomic, lock, read, xdg

# The repository-wide evidence index is written only under lanes mode or by --commit-in;
# every other repository reads it when present and is otherwise unchanged.
INDEX_WRITES = False


def enable_index_writes():
    global INDEX_WRITES
    INDEX_WRITES = True


class Index:
    """Per-commit cache of validated acceptance records, shared by a repository's worktrees.

    A commit's trailers and detail files never change, so what one worktree validated holds
    for every other; records written in a landing checkout resolve anywhere after a rebase.
    Lives under the XDG cache: <repo-key>/evidence/<commit>.json plus identity.json.
    """

    def __init__(self, git):
        self.git = git
        self.path = xdg('cache') / path_key(git.common) / 'evidence'

    def get(self, commit):
        try:
            value = read(self.path / (commit + '.json'))
        except Invalid:
            return None
        if (not isinstance(value, dict) or value.get('version') != 1 or value.get('commit') != commit
                or value.get('common') != str(self.git.common) or value.get('invalid') != [] or not isinstance(value.get('records'), list)):
            return None
        return value

    def put(self, commit, records, invalid):
        # Only commits whose every trailer validated are cached; a failure is re-examined each time.
        if not INDEX_WRITES or invalid:
            return
        value = {'version': 1, 'commit': commit, 'common': str(self.git.common), 'records': records, 'invalid': [], 'created': time.time()}
        with lock():
            if not (self.path / 'identity.json').is_file():
                atomic(self.path / 'identity.json', {'version': 1, 'common': str(self.git.common), 'created': time.time(), 'missing_since': None})
            atomic(self.path / (commit + '.json'), value)

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
            # Older versions also kept manifests and closure archives here; only snapshots count.
            if not HEX.fullmatch(path.stem):
                continue
            old = state.get('snapshots/' + path.name)
            if not isinstance(old, dict) or old.get('id') != path.stem or 'attempt' not in old:
                continue
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
                raise Invalid('Reviewed provenance requires observation:<name> and --review-note.')
            # Who reviewed is recorded, never inferred; agents review only where the check allows it.
            allowed = definition(policy, check).get('reviewer', 'human')
            if args.reviewer_kind not in ('human', 'agent'):
                raise Invalid('Reviewed provenance requires --reviewer-kind human or agent.')
            if args.reviewer_kind == 'agent' and allowed != 'any':
                raise Invalid(check + ' requires a human reviewer; an agent review needs "reviewer": "any" in its check definition.')
            note = confined(git.root, args.review_note)
            if not note.is_file() or not re.search(r'\b\d{4}-\d{2}-\d{2}\b', note.read_text(encoding='utf-8')):
                raise Invalid('Review note must be a durable dated file.')
            value.update(reviewer=args.reviewer, reviewer_kind=args.reviewer_kind, review_note=args.review_note,
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
    if not args.exception:
        before['last_use'] = time.time()
        state.put('snapshots/' + before['id'] + '.json', before)
    return store(git, policy, state, value, args)


def store(git, policy, state, value, args):
    value['id'] = record_id(value)
    detail = args.detail or policy['continuation']['evidence'].rstrip('/') + '/' + value['id'] + '.json'
    confined(git.root, detail)
    value['detail'] = detail
    value['created'] = time.time()
    existing = state.get('evidence/' + value['id'] + '.json')
    if existing:
        value = existing
    state.put('evidence/' + value['id'] + '.json', value, immutable=True)
    line = trailer(value)
    files = {value['detail']: proposed(value)}
    output = {'record': value, 'trailer': line, 'proposed_files': files, 'pending': True}
    if args.trailers_file:
        add_trailer(Path(args.trailers_file), line)
    if args.write_proposed:
        output['written'] = write_files(git, files)
    return output


def proposed(value):
    return json.dumps(value, sort_keys=True, indent=2) + '\n'


def add_trailer(path, line, remove=()):
    """Accumulate one batch's trailers: append once, keep order, drop superseded lines."""
    lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    lines = [x for x in lines if x and x not in remove]
    if line and line not in lines:
        lines.append(line)
    atomic(path, ('\n'.join(lines) + '\n' if lines else '').encode(), raw=True)


def write_files(git, files):
    """Write only the record's own detail paths; never overwrite different bytes."""
    written = []
    for name, content in files.items():
        path = confined(git.root, name)
        data = content.encode()
        if path.exists() and (path.is_symlink() or not path.is_file() or path.read_bytes() != data):
            raise Invalid('Refusing to overwrite different content at ' + name + '; review it and remove it explicitly.')
        if not path.exists():
            atomic(path, data, raw=True)
            written.append(name)
    return written


def lookup(git, id_):
    if not HEX.fullmatch(id_ or ''):
        raise Invalid('Evidence ID must be SHA-256.')
    durable = next((x for x in committed(git)[0] if x['id'] == id_), None)
    if durable:
        return durable
    value = State(git).get('evidence/' + id_ + '.json')
    if not value or record_id(value) != id_:
        raise Invalid('No committed or pending record ' + id_ + '; use evidence find.')
    return dict(value, pending=True, carrying_commit=None)


def rerecord(git, policy, args):
    """Carry an unchanged observation onto revised criteria with a fresh snapshot."""
    old = lookup(git, args.id)
    if old.get('exception'):
        raise Invalid('Exceptions approve one criterion revision; obtain a new approval and record a new exception.')
    check = old['name']
    if policy_digest(policy, check, old['criteria']) != old['policy']:
        raise Invalid('The check definition, inputs or validator policy changed, not only its criteria; prepare and run the check again.')
    if old['criteria'] == criterion_policy(policy, check):
        raise Invalid('Criteria are unchanged; the record is already current for this policy.')
    snap = prepare(git, policy, check, args.attempt, args.probe_inputs)
    if snap['scope'] != old['scope'] or snap['inputs'] != old['inputs'] or snap['domain'] != old['domain']:
        raise Invalid('Scope, inputs or domain changed since the record; prepare and run the check again.')
    if recovery(git, policy, old['log']) != old['log_digest']:
        raise Invalid('The recorded log changed or is missing; prepare and run the check again.')
    if old['claim'] == 'checked':
        if snap.get('tree') != old['tree']:
            raise Invalid('Delegation tree changed; the registered result no longer describes this tree.')
        result = Checker(git, policy).result(old['delegation'], old['result'],
                     definition(policy, check).get('validator', check.removeprefix('validator:')), old['tree'])
        if digest(result) != old['result_digest']:
            raise Invalid('Registered result changed; prepare and run the check again.')
    elif old['claim'] == 'reviewed':
        note = confined(git.root, old['review_note'])
        if not note.is_file() or hashlib.sha256(note.read_bytes()).hexdigest() != old['review_digest']:
            raise Invalid('Review note changed or is missing; obtain and record a new review.')
    value = {k: v for k, v in old.items() if k not in ('id', 'created', 'last_use', 'detail', 'snapshot', 'carrying_commit', 'pending')}
    value.update(policy=snap['policy'], criteria=snap['criteria'], attempt=snap['attempt'], snapshot=snap['id'], rerecorded_from=old['id'])
    state = State(git)
    trailers = args.trailers_file
    args.trailers_file = None
    output = store(git, policy, state, value, args)
    superseded = {'id': old['id'], 'committed': not old['pending'], 'removed': []}
    if old['pending']:
        # An uncommitted superseded proposal goes; committed history is never touched.
        detail = confined(git.root, old['detail'])
        relative = detail.relative_to(git.root).as_posix()
        tracked = git.run('ls-files', '--', relative).strip()
        if detail.is_file() and not detail.is_symlink() and not tracked and detail.read_bytes() == proposed({k: v for k, v in old.items() if k not in ('pending', 'carrying_commit')}).encode():
            detail.unlink()
            superseded['removed'].append(old['detail'])
        state.remove('evidence/' + old['id'] + '.json')
    if trailers:
        add_trailer(Path(trailers), output['trailer'], remove=(trailer(old),) if old['pending'] else ())
    output['superseded'] = superseded
    return output



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
        if value.get('reviewer_kind', 'human') not in ('human', 'agent'):
            raise Invalid('Reviewer kind must be human or agent.')
        path = confined(git.root, value['review_note']).relative_to(git.root).as_posix()
        content = git.run('show', commit + ':' + path, binary=True, check=False)
        if not value.get('reviewer') or not re.search(rb'\b\d{4}-\d{2}-\d{2}\b', content) or hashlib.sha256(content).hexdigest() != value.get('review_digest'):
            raise Invalid('Dated review note is missing/altered.')


def commit_records(git, commit, lines, index):
    """Validated records one commit carries plus the trailer IDs (None when unparseable) that failed,
    from the shared index when it already knows the commit."""
    cached = index.get(commit)
    if cached is not None:
        return cached['records'], []
    records, invalid = [], []
    for line in lines:
        fields = None
        try:
            fields = parse_trailer(line)
            path = confined(git.root, fields['detail']).relative_to(git.root).as_posix()
            value = json.loads(git.read(commit, path))
            validate_durable(git, commit, value)
            if record_id(value) != fields['id'] or parse_trailer(trailer(value)) != fields:
                raise Invalid('Trailer/detail content mismatch.')
            records.append(value)
        except (Invalid, ValueError, KeyError, TypeError):
            invalid.append(fields['id'] if fields else None)
    index.put(commit, records, invalid)
    return records, invalid


def history(git, ref='HEAD'):
    """(commit, message) pairs oldest first; one log call, signatures never mixed into the text."""
    raw = git.run('log', '-z', '--no-show-signature', '--reverse', '--topo-order', '--format=%H%n%B', ref, check=False)
    for entry in raw.split('\0'):
        if entry.strip():
            commit, _, message = entry.partition('\n')
            yield commit, message


def committed(git):
    records, findings = [], []
    seen = set()
    index = Index(git)
    # Reverse topological traversal identifies original introduction, not duplicate carrying commits.
    for commit, message in history(git):
        lines = [x for x in message.splitlines() if x.startswith(('Accepted-Check:', 'Accepted-Exception:'))]
        if not lines:
            continue
        values, invalid = commit_records(git, commit, lines, index)
        for value in values:
            if value['id'] in seen:
                continue
            seen.add(value['id'])
            records.append(dict(value, carrying_commit=commit, pending=False))
        for id_ in invalid:
            # A repeated trailer of a record already introduced is not corruption, as before.
            if id_ is None or id_ not in seen:
                findings.append(finding('evidence-corrupt', 'Committed acceptance trailer/detail is invalid.', 'Inspect acceptance records in commit ' + commit + ' and record new reviewed evidence.'))
    return records, findings


def commit_in(git, record, directory):
    """Lander flow: commit exactly the record's detail file, with its trailer, in a checkout of this repository.

    Uses a private index file, so the checkout's own index and staged work stay untouched; it never
    amends, pushes or moves any ref but that checkout's HEAD, and only from the HEAD it read.
    """
    other = Git(directory)
    if other.common != git.common:
        raise Invalid('--commit-in must name a checkout of the same repository as --root.')
    head = other.oid()
    if not head:
        raise Invalid('--commit-in checkout has no commit to build on.')
    # The commit carries exactly the detail file, so every file the record relies on must already be history.
    if not record.get('exception') and not record['log'].startswith(('https://', 'http://', 'regenerate:')):
        raise Invalid('--commit-in needs a persistent --log route (regenerate: or http(s)), not a checkout file.')
    if record.get('claim') == 'reviewed':
        raise Invalid('--commit-in records observed or delegated checks; reviewed observations go through the reviewed commit flow.')
    line = trailer(record)
    for existing in committed(other)[0]:
        if existing['id'] == record['id']:
            return {'commit': existing['carrying_commit'], 'committed_in': str(other.root), 'already_committed': True}
    content = proposed(record)
    write_files(other, {record['detail']: content})
    relative = confined(other.root, record['detail']).relative_to(other.root).as_posix()
    blob = other.run('hash-object', '-w', '--path', relative, '--stdin', input=content).strip()
    scratch = xdg('cache') / path_key(git.common) / 'scratch'
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    index_file = scratch / ('index-' + uuid.uuid4().hex)
    env = dict(os.environ, GIT_INDEX_FILE=str(index_file), GIT_OPTIONAL_LOCKS='0')

    def run(*args, input=None):
        result = subprocess.run(['git', '-C', str(other.root), *args], input=input, capture_output=True, text=True, timeout=30, env=env)
        if result.returncode:
            raise Invalid('Git operation failed in --commit-in checkout: ' + args[0] + '; ' + result.stderr.strip())
        return result.stdout.strip()

    try:
        run('read-tree', head)
        run('update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + relative)
        tree = run('write-tree')
        if tree == other.run('rev-parse', head + '^{tree}').strip():
            raise Invalid('The detail file is already in HEAD without its trailer; record a new check or cite the carrying commit.')
        subject = 'Evidence: ' + (('exception ' + record['check'] + ' for ' + record['target']) if record.get('exception') else record['name'] + ' ' + record['outcome'])
        commit = run('commit-tree', tree, '-p', head, input=subject + '\n\n' + line + '\n')
        # The dangling commit is checked as history would read it before any ref moves.
        values, invalid = commit_records(other, commit, [line], Index(other))
        if invalid or [x['id'] for x in values] != [record['id']]:
            raise Invalid('The evidence commit would not validate from history; nothing was committed.')
        run('update-ref', '-m', 'long-horizon evidence', 'HEAD', commit, head)
        # The checkout's own index learns the one added path, so the worktree matches its new HEAD.
        other.run('update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + relative)
    finally:
        if index_file.exists():
            index_file.unlink()
        try:
            scratch.rmdir()
        except OSError:
            pass
    result = {'commit': commit, 'committed_in': str(other.root), 'already_committed': False}
    if other.root == git.root:
        result['cleanup'] = cleanup(git, commit, [record['id']])
    return result


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


def local_pending(git):
    """Uncommitted records in this worktree's XDG state, newest last; status shows them as pending."""
    state = State(git)
    folder = state.path / 'evidence'
    if not folder.is_dir():
        return []
    durable = {x['id'] for x in committed(git)[0]}
    values = [state.get('evidence/' + path.name) for path in folder.glob('*.json')]
    values = [x for x in values if isinstance(x, dict) and x.get('id') == record_id(x) and x['id'] not in durable]
    return sorted(values, key=lambda x: x.get('created', 0))


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
        result.append({'check': name, 'status': status, 'record': accepted, 'pending': bool(accepted and accepted['pending']),
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
