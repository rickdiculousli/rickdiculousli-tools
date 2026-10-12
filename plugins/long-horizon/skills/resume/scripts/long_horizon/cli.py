import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
from . import closure, evidence, gate, goals, handoff, lint, overlay, readiness, state
from .git import Git
from .model import Invalid, Blocked, finding


def common(parser):
    parser.add_argument('--root', default='.')
    parser.add_argument('--overlay')
    parser.add_argument('--draft-root')
    parser.add_argument('--goals')
    parser.add_argument('--handoff')
    parser.add_argument('--json', action='store_true')
    return parser


def parser():
    top = argparse.ArgumentParser(description='Inspect continuation and acceptance without running validators or Git integration.')
    commands = top.add_subparsers(dest='command', required=True)
    common(commands.add_parser('paths'))
    status = common(commands.add_parser('status'))
    status.add_argument('--brief', action='store_true')
    check = common(commands.add_parser('lint'))
    check.add_argument('--fix', action='store_true')
    check.add_argument('--apply', action='store_true')
    check = common(commands.add_parser('gate'))
    check.add_argument('--base', default='HEAD')
    check.add_argument('--probe-inputs', action='store_true')
    check.add_argument('--pending', action='append', default=[])
    ev = commands.add_parser('evidence').add_subparsers(dest='action', required=True)
    prepare = common(ev.add_parser('prepare'))
    prepare.add_argument('check')
    prepare.add_argument('--attempt')
    prepare.add_argument('--probe-inputs', action='store_true')
    record = common(ev.add_parser('record'))
    record.add_argument('check')
    for key in ('snapshot', 'domain', 'log', 'detail', 'command', 'delegation', 'result', 'reviewer', 'review-note', 'trailers-file', 'target', 'reason', 'by'):
        record.add_argument('--' + key, dest='observed_command' if key == 'command' else key.replace('-', '_'))
    record.add_argument('--reviewer-kind', choices=('human', 'agent'))
    record.add_argument('--outcome', choices=('PASS', 'FAIL', 'SKIP', 'UNSTABLE'))
    record.add_argument('--exit', type=int)
    record.add_argument('--probe-inputs', action='store_true')
    record.add_argument('--exception', action='store_true')
    record.add_argument('--write-proposed', action='store_true')
    again = common(ev.add_parser('rerecord'))
    again.add_argument('id')
    for key in ('attempt', 'detail', 'trailers-file'):
        again.add_argument('--' + key, dest=key.replace('-', '_'))
    again.add_argument('--probe-inputs', action='store_true')
    again.add_argument('--write-proposed', action='store_true')
    cleanup = common(ev.add_parser('cleanup'))
    cleanup.add_argument('--commit', required=True)
    cleanup.add_argument('--id', action='append', required=True)
    find = common(ev.add_parser('find'))
    find.add_argument('check', nargs='?')
    find.add_argument('--probe-inputs', action='store_true')
    find.add_argument('--pending', action='append', default=[])
    cl = commands.add_parser('closure').add_subparsers(dest='action', required=True)
    build = common(cl.add_parser('manifest'))
    build.add_argument('--base', required=True)
    build.add_argument('--path', action='append', default=[])
    build.add_argument('--pending', action='append')
    build.add_argument('--output')
    record = common(cl.add_parser('record'))
    record.add_argument('--batch', required=True)
    record.add_argument('--new-batch', action='store_true')
    record.add_argument('--step', required=True, choices=('validate', 'commit', 'merge', 'push', 'sync'))
    record.add_argument('--outcome', required=True, choices=('success', 'failed', 'pending'))
    for key in ('commit', 'integrated-commit', 'observation', 'manifest'):
        record.add_argument('--' + key)
    verify = common(cl.add_parser('verify'))
    verify.add_argument('--state')
    st = commands.add_parser('state').add_subparsers(dest='action', required=True)
    draft = common(st.add_parser('draft'))
    draft.add_argument('--id')
    clear = common(st.add_parser('clear'))
    clear.add_argument('--state-directory', required=True)
    gc = common(st.add_parser('gc'))
    gc.add_argument('--apply', action='store_true')
    gc.add_argument('--if-due', action='store_true')
    return top


def context(args):
    git = Git(args.root)
    policy = overlay.load(git, args.overlay, args.draft_root, args.goals, args.handoff)
    path = Path(policy['_goals'])
    parsed = goals.parse(path.read_text(encoding='utf-8') if path.exists() else '', policy, str(path))
    return git, policy, parsed


def inspect(args, git, policy, parsed):
    report, reports = readiness.load(policy, git)
    continuation, warnings = handoff.inspect(policy, git, parsed)
    findings = list(parsed['findings']) + reports + warnings
    if not policy['_installed'] and not args.draft_root:
        findings.append(finding('setup-missing', 'No installed long-horizon overlay.', 'Use long-horizon:setup or proceed with explicit session instructions.', 'warning'))
    try:
        pending = evidence.local_pending(git)
    except Invalid as error:
        pending = []
        findings.append(finding('pending-unreadable', 'Pending evidence is unreadable: ' + str(error), 'Inspect state gc and recover the records explicitly.', 'warning'))
    # Status shows local pending records; the gate still accepts only explicit --pending IDs.
    acceptance, acceptance_findings = evidence.find(git, policy, pending=[x['id'] for x in pending])
    findings += acceptance_findings
    pending = [{'id': x['id'], 'check': x.get('name') or x.get('check'), 'outcome': x.get('outcome', 'EXCEPTION'),
                'detail': x['detail'], 'pending': True} for x in pending]
    archived = [x for x in parsed['goals'] if x['status'] == 'done' and not x['children']]
    if archived:
        records, history_findings = evidence.candidates(git, [])
        findings += history_findings
        for goal in archived:
            try:
                gate.verify_archive_records(gate.archive(goal, policy), {x['id']: x for x in records})
            except (Invalid, OSError, ValueError, KeyError, TypeError) as error:
                findings.append(finding('archive-invalid', 'Archived goal proof is invalid: ' + str(error),
                    'Restore the goal children or recover the complete matching archive/evidence.'))
    for section, name in [('evidence', 'delegation'), ('batch', 'quota')]:
        try:
            overlay.script(policy, section, name)
        except Invalid as error:
            findings.append(finding('script-missing', str(error), 'Configure the declared script path/environment value.', 'warning'))
    if (git.root / '.long-horizon').exists():
        findings.append(finding('legacy-state', 'Legacy checkout-local long-horizon state exists.',
            'Review and explicitly import recoverable records into XDG; no automatic move/delete.', 'warning'))
    selection = goals.select(parsed, policy, report, continuation['blockers'])
    needs = continuation['decisions'][:]
    if selection['mode'] == 'awaiting-signoff':
        needs.append('sign off the completed goal')
    if selection['mode'] == 'all-blocked':
        needs += [reason for item in selection['blocked'] for reason in item['reasons']]
    try:
        cl, closure_findings = closure.verify(git, policy)
    except Invalid as error:
        cl = {'state': 'unknown', 'steps': [], 'next': 'recover-closure'}
        closure_findings = [finding('state-identity-unknown', str(error), 'Inspect state gc; explicitly recover the prior closure/evidence before reuse.', 'warning')]
    if cl['next']:
        needs.append('unfinished closure: ' + cl['next'])
    # Unfinished closure is status data, not a failed inspection.
    findings += [finding(x.code, x.message, x.remedy, 'warning', x.path, x.line) for x in closure_findings]
    return {'selection': selection, 'handoff': continuation, 'needs_you': needs, 'acceptance': acceptance['checks'],
            'pending_evidence': pending,
            'closure': cl, 'state_directory': str(state.State(git).path), 'cache_directory': str(state.State(git).cache),
            'git': {'root': str(git.root), 'common_dir': str(git.common), 'branch': git.branch(),
                    'head': git.oid(), 'target': policy['integration'].get('target') or git.target(), 'dirty': git.dirty()}}, findings


def execute(args):
    if args.command == 'state':
        if args.action == 'draft':
            return state.draft(Git(args.root), args.id), []
        if args.action == 'clear':
            return state.clear(Git(args.root), args.state_directory), []
        return state.gc(args.apply, args.if_due, location_root=args.root), []
    if args.command == 'paths':
        git = Git(args.root)
        policy = overlay.load(git, args.overlay, args.draft_root, args.goals, args.handoff)
        return readiness.paths(policy, git), []
    git, policy, parsed = context(args)
    if args.command == 'status':
        return inspect(args, git, policy, parsed)
    if args.command == 'lint':
        if args.apply and not args.fix:
            raise Invalid('--apply requires --fix and explicit review of the mechanical diff.')
        data, findings = inspect(args, git, policy, parsed)
        findings += lint.pointers(policy, git)
        name = policy['startup'].get('readiness')
        if name and not name.startswith('cache:'):
            findings.append(finding('readiness-legacy-path', 'Legacy readiness path violates the external runtime cache contract.',
                'Use readiness: \"cache:readiness.json\" and have the startup helper discover its destination with lh.py paths --root PATH --json.', 'warning', policy['_overlay']))
        if args.fix:
            data['diff'] = lint.repair(policy, parsed, args.apply)
        return data, findings
    if args.command == 'evidence':
        if args.action == 'cleanup':
            return evidence.cleanup(git, args.commit, args.id), []
        if args.action == 'prepare':
            return {'snapshot': evidence.prepare(git, policy, args.check, args.attempt, args.probe_inputs)}, []
        if args.action == 'record':
            # Keep argparse's command discriminator separate from provenance.
            args.command = args.observed_command
            return evidence.record(git, policy, args), []
        if args.action == 'rerecord':
            return evidence.rerecord(git, policy, args), []
        return evidence.find(git, policy, args.check, args.probe_inputs, args.pending)
    if args.command == 'gate':
        findings = []
        checker = evidence.Checker(git, policy)
        open_ = checker.pending() if checker.path else []
        if open_:
            ids = [str(x.get('delegation')) for x in open_]
            findings.append(finding('delegation-pending', 'Delegation has open delegations: ' + ', '.join(ids) + '.',
                'Review and hand them back, then close each: ' + '; '.join(
                    'python3 ' + shlex.quote(str(checker.path)) + ' --root ' + shlex.quote(str(git.root)) +
                    ' close --delegation ' + shlex.quote(x) + ' --outcome done|stuck|abandoned' for x in ids) + '.'))
        data, more = gate.run(git, policy, parsed, args.base, args.pending, args.probe_inputs)
        return data, findings + more
    if args.action == 'manifest':
        return closure.manifest(git, policy, args.base, args.path, args.pending, args.output), []
    if args.action == 'record':
        return {'closure': closure.record(git, policy, args)}, []
    return closure.verify(git, policy, args.state)


def main(argv=None):
    args = parser().parse_args(argv)
    command = args.command + (' ' + args.action if hasattr(args, 'action') else '')
    try:
        data, findings = execute(args)
        ok = not any(x.severity == 'error' for x in findings)
        output = dict(version=1, command=command, ok=ok, findings=[x.json() for x in findings], **data)
        code = 0 if ok else 1
    except (Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError, subprocess.SubprocessError) as error:
        output = {'version': 1, 'command': command, 'ok': False,
                  'findings': [finding('acceptance-blocked' if isinstance(error, Blocked) else 'invalid-environment', str(error), 'Run a new reviewed check or record the actual nonpassing outcome.' if isinstance(error, Blocked) else 'Repair the reported policy/path or rerun with --help.').json()]}
        code = 1 if isinstance(error, Blocked) else 2
    if args.json:
        print(json.dumps(output, sort_keys=True, indent=2))
    else:
        if 'selection' in output:
            selection = output['selection']
            print('Goal: ' + selection.get('goal_title', selection['mode']))
            task = selection.get('task')
            progress = selection.get('progress', {})
            print('Milestone: ' + selection.get('milestone_title', selection['mode']) +
                  (f" ({progress['done']}/{progress['total']} tasks)" if progress else ''))
            print('Next: ' + (task['id'] + ' ' + task['title'] if task else selection['mode']) +
                  '; Needs you: ' + ('; '.join(output.get('needs_you', [])) or 'none'))
            handoff = output.get('handoff', {})
            if 'lines' in handoff:
                print('Handoff: %d/%d lines' % (handoff['lines'], handoff['budget']) + (' (over budget)' if handoff['lines'] > handoff['budget'] else ''))
            for item in output.get('pending_evidence', []):
                print('Pending evidence: ' + item['check'] + ' ' + item['outcome'] + ' ' + item['id'] + ' (uncommitted; pass --pending to gate)')
        elif not output.get('findings'):
            print(json.dumps({k: v for k, v in output.items() if k not in ('version', 'command', 'ok', 'findings')}, indent=2))
        if output.get('diff'):
            print(output['diff'], end='')
        for item in output['findings']:
            print(item['severity'] + ': ' + item['message'] + ' Fix: ' + item['remedy'])
    return code
