"""Compare proposed lifecycle claims with a base; never edit the roadmap."""
import json
from pathlib import Path
import re
from .evidence import find
from .git import confined
from .goals import effective_policy, flatten, parse, TOKENS
from .model import Invalid, finding
from .scope import policy_digest


def archive(item, policy):
    refs = item['metadata'].get('Archive', [])
    if len(refs) != 1:
        raise Invalid('Goal needs one Archive: <tracked-path> completion record.')
    path = confined(policy['_base'], refs[0])
    text = path.read_text(encoding='utf-8')
    match = re.search(r'```json\s*\n(.*?)\n```', text, re.S)
    if not match:
        raise Invalid('Archive needs a version-1 JSON metadata fence.')
    value = json.loads(match[1])
    required = {'version', 'goal_id', 'status', 'outcome', 'milestones', 'goal_checks', 'signoff', 'limitations', 'refuted', 'followups'}
    if not required <= value.keys() or value['version'] != 1 or value['goal_id'] != item['id'] or value['status'] != item['status']:
        raise Invalid('Archive identity/status/schema does not match the goal.')
    if not isinstance(value['milestones'], list) or not isinstance(value['goal_checks'], list) or not value['milestones']:
        raise Invalid('Archive requires ordered milestone summaries and goal checks.')
    if item['status'] in ('shelved', 'dropped'):
        if not value.get('reason') or not value.get('original_roadmap'):
            raise Invalid('Shelved/dropped archive must preserve reason and original_roadmap.')
    else:
        if not value['outcome'] or not value['goal_checks']:
            raise Invalid('Completed archive needs goal criteria/checks and outcome.')
        for summary in value['milestones']:
            if not isinstance(summary, dict) or not all(summary.get(k) for k in ('id', 'criteria', 'evidence')):
                raise Invalid('Completed archive milestone needs id, criteria and evidence.')
    return value


def run(git, policy, parsed, base='HEAD', pending=(), probe=False):
    findings = list(parsed['findings'])
    path = Path(policy['_goals'])
    try:
        relative = path.relative_to(git.root).as_posix()
    except ValueError:
        relative = policy['goals and ownership']['path']
    previous = parse(git.read(base, relative) if git.oid(base) else '', policy)
    old = flatten(previous['goals'])
    proposed = flatten(parsed['goals'])
    if parsed['mode'] == 'manual':
        findings.append(finding('gate-manual-roadmap', 'Acceptance needs parseable goals.', 'Annotate ## 1. Title, task IDs, Done when and Checks before closing work.'))
        return {'completed': [], 'policy_changes': []}, findings
    changed = []
    for id_, before in old.items():
        after = proposed.get(id_)
        # Reformatting the same criterion (colon, whitespace, moving it above the tasks) is not a policy change.
        if after and before['kind'] in ('goal', 'milestone') and effective_policy(before) != effective_policy(after):
            changed.append(id_)
            if policy['goals and ownership']['milestone-policy'] == 'user' and not after['metadata'].get('Policy-Approval'):
                findings.append(finding('policy-approval', 'Reserved scope/criteria changed: ' + id_,
                    'Obtain actual user approval and add an adjacent Policy-Approval: who approved what.'))
    before_order = [x['id'] for x in previous['goals']]
    after_order = [x['id'] for x in parsed['goals']]
    for goal in parsed['goals']:
        if goal['id'] in old:
            before_order += [x['id'] for x in old[goal['id']]['children']]
            after_order += [x['id'] for x in goal['children']]
    if [x for x in before_order if x in proposed] != [x for x in after_order if x in old]:
        if policy['goals and ownership']['milestone-policy'] == 'user' and not any(x['metadata'].get('Policy-Approval') for x in proposed.values()):
            findings.append(finding('order-approval', 'Milestone/goal ordering changed.', 'Obtain user approval and record Policy-Approval.'))
    base_overlay = git.read(base, '.agents/long-horizon.md') if git.oid(base) else ''
    if base_overlay:
        from .overlay import parse as parse_overlay
        previous_policy = parse_overlay(base_overlay)
        if previous_policy['goals and ownership'] != policy['goals and ownership'] or previous_policy['integration'] != policy['integration']:
            if not any(x['metadata'].get('Policy-Approval') for x in proposed.values()):
                findings.append(finding('ownership-approval', 'Ownership or integration authorization changed.', 'Record actual user approval before using the changed policy.'))
    if policy['goals and ownership']['task-refinement'] == 'user':
        for id_, after in proposed.items():
            before = old.get(id_)
            if after['kind'] == 'task' and (not before or before['title'] != after['title'] or before.get('tags') != after.get('tags')):
                parent = next((x for x in proposed.values() if after in x['children']), None)
                if not after['metadata'].get('Policy-Approval') and not (parent and parent['metadata'].get('Policy-Approval')):
                    findings.append(finding('task-refinement-approval', 'Reserved task refinement changed: ' + id_, 'Obtain actual user approval and add adjacent Policy-Approval.'))
    completed = [x for x in proposed.values() if x['status'] == 'done' and (x['id'] not in old or old[x['id']]['status'] != 'done')]
    checks, evidence_findings = find(git, policy, probe=probe, pending=pending)
    findings += evidence_findings
    fresh = {x['check']: x for x in checks['checks']}
    records = {x['id']: x for x in checks['records']}
    for item in completed:
        owner_key = 'task-completion' if item['kind'] == 'task' else 'milestone-completion' if item['kind'] == 'milestone' else None
        if owner_key and policy['goals and ownership'][owner_key] == 'user' and not item['metadata'].get('Policy-Approval'):
            findings.append(finding('completion-approval', 'Completion is reserved to the user: ' + item['id'], 'Obtain actual user instruction and add adjacent Policy-Approval for completion.'))
        refs = item['evidence'].get(item['id'], [])
        if item['kind'] == 'task':
            parent = next((x for x in proposed.values() if item in x['children']), None)
            if parent:
                refs += parent['evidence'].get(item['id'], [])
            if not refs:
                findings.append(finding('task-evidence', 'Newly completed task lacks evidence: ' + item['id'], 'Add adjacent Evidence: ' + item['id'] + '=<evidence-id-or-ancestor-commit>.'))
            for ref in refs:
                if ref in records:
                    result = records[ref]
                    if result.get('exception') or result.get('outcome') != 'PASS' or not fresh.get(result.get('name')) or fresh[result['name']]['status'] != 'fresh' or fresh[result['name']]['record']['id'] != ref:
                        findings.append(finding('task-evidence-outcome', 'Task evidence is not the current accepted scoped PASS.', 'Record passing observed work or leave the task open.'))
                elif not git.oid(ref) or not git.ancestor(ref) or not git.run('diff-tree', '--root', '--no-commit-id', '--name-only', '-r', ref).strip():
                    findings.append(finding('task-citation', 'Task commit citation is unresolved/unreachable/empty.', 'Cite an ancestor commit with inspectable changes or explicit pending evidence.'))
            if not item['criteria'] and not item['checks']:
                continue
        if not item['criteria'] or not item['checks']:
            findings.append(finding('unverifiable-criteria', 'Free-text acceptance cannot auto-pass: ' + item['id'],
                'Add Checks: ["validator:name", "observation:review"] without changing the adopted criteria, or leave the milestone open.'))
        for check in item['checks']:
            accepted = fresh.get(check)
            exceptions = [x for x in records.values() if x.get('exception') and x.get('target') == item['id'] and
                          x.get('check') == check and x.get('policy') == policy_digest(policy, check)] if check in policy['evidence']['checks'] else []
            skips = accepted and accepted['status'] == 'skip' and accepted['record'].get('domain') in policy['evidence']['checks'][check].get('allowed-skips', [])
            if not (accepted and accepted['status'] == 'fresh') and not exceptions and not skips:
                findings.append(finding('missing-acceptance', 'Missing fresh ' + check + ' for ' + item['id'],
                    'Run evidence prepare ' + check + ', perform/record the check; leave only tasks done; or obtain an explicit targeted user exception.'))
        if item['kind'] == 'goal':
            try:
                value = archive(item, policy)
                expected = item['children'] or old.get(item['id'], {}).get('children', [])
                summaries = value['milestones']
                if not expected or [x['id'] for x in expected] != [x.get('id') for x in summaries]:
                    raise Invalid('Archive must preserve every ordered milestone.')
                for before, summary in zip(expected, summaries):
                    if summary.get('criteria') != before['criteria'] or sorted(set(summary.get('checks', TOKENS.findall(summary.get('criteria', ''))))) != before['checks']:
                        raise Invalid('Archive must preserve exact milestone criteria and required check lists.')
                verify_archive_records(value, records)
                if sorted(set(value['goal_checks'])) != item['checks'] or not value['outcome']:
                    raise Invalid('Archive must preserve goal checks and readable outcome.')
                if policy['goals and ownership']['goal-signoff'] == 'user' and (not value['signoff'] or not item['metadata'].get('Signed-off')):
                    raise Invalid('Archive and goal require actual sign-off.')
            except (Invalid, OSError, ValueError, KeyError, TypeError) as error:
                findings.append(finding('archive-invalid', 'Completion record is invalid: ' + str(error), 'Preserve complete milestone criteria/evidence and user sign-off in the version-1 archive.'))
    for goal in parsed['goals']:
        if goal['status'] in ('shelved', 'dropped'):
            try:
                archive(goal, policy)
            except (Invalid, OSError, ValueError, KeyError, TypeError):
                findings.append(finding('stop-record-invalid', 'Shelved/dropped goal lacks a valid preserved record.', 'Preserve reason and original_roadmap in its version-1 archive after actual user instruction.'))
        if goal['status'] == 'done' and not goal['children']:
            try:
                value = archive(goal, policy)
                verify_archive_records(value, records)
            except (Invalid, OSError, ValueError, KeyError, TypeError):
                findings.append(finding('compressed-goal-invalid', 'Compressed goal has no valid archive.', 'Restore its children or provide the verified completion record.'))
    return {'completed': [x['id'] for x in completed], 'policy_changes': changed, 'acceptance': checks['checks']}, findings


def verify_archive_records(value, records):
    for summary in value['milestones']:
        required = sorted(set(summary.get('checks', TOKENS.findall(summary['criteria']))))
        if not required:
            raise Invalid('Archived milestone needs named required checks.')
        ids = summary['evidence'] + summary.get('exceptions', [])
        for check in required:
            valid = False
            for id_ in ids:
                record = records.get(id_)
                if not record:
                    continue
                target = next((x for x in record.get('criteria', []) if x['id'] == summary['id']), None)
                if not target or target['criteria'] != ' '.join(summary['criteria'].split()) or target['checks'] != required:
                    continue
                if record.get('exception'):
                    valid |= record.get('target') == summary['id'] and record.get('check') == check
                else:
                    valid |= record.get('name') == check and record.get('outcome') == 'PASS' and record.get('stable') is True and record.get('exit') == 0
            if not valid:
                raise Invalid('Archive has no matching accepted criterion proof for ' + summary['id'] + '/' + check)
