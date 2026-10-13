"""Parse structure outside fences, preserving source text and line locations."""
import json
import hashlib
import re
from .model import finding

TOKENS = re.compile(r'\b(?:validator|observation):[\w.-]*\w')
LOOSE = re.compile(r'^(?i:done when)\b(?!\s*:)\s*[-\u2013\u2014]?\s*')
KEYS = {'ID', 'Done when', 'Checks', 'Evidence', 'Context', 'Signed-off', 'Archive', 'Reason', 'Policy-Approval', 'Completion', 'Exception'}
# Lane metadata ends a wrapped criterion only on the node kind it belongs to, so other prose is unchanged.
LANE_KEYS = {'task': {'Lane', 'After'}, 'goal': {'Parallel'}}
LANE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')


def outside(text):
    fence = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        match = re.match(r'^(`{3,}|~{3,})', line)
        if match:
            mark = match[1]
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and re.fullmatch(r'(?:`+|~+)\s*', line):
                fence = None
            continue
        if fence is None:
            yield number, raw


def text_id(text):
    return hashlib.sha256(' '.join(text.split()).encode()).hexdigest()[:12]


def node(title, kind, line, markers):
    status = 'open'
    for name, marker in markers.items():
        if title.endswith(marker):
            title, status = title[:-len(marker)].strip(), name
            break
    return {'kind': kind, 'title': title, 'status': status, 'line': line, 'id': '',
            'criteria': '', 'checks': [], 'evidence': {}, 'context': [], 'children': [], 'metadata': {},
            'lane': None, 'after': []}


def parse(text, policy, path=''):
    markers = policy['goals format']['markers']
    goals, findings, ids = [], [], set()
    goal = milestone = current = None
    parked = False
    # A criterion is a paragraph: its Done when line plus directly following lines
    # up to a blank line, heading, task or metadata key.
    paragraph = None
    if not any(re.match(r'^# Goal:', raw) for _, raw in outside(text)):
        first = next((number for number, raw in outside(text) if re.match(r'^## \d', raw.strip())), None)
        if first:
            findings.append(finding('layout-outdated', 'Milestones without a # Goal: heading are not read.',
                'Add "# Goal: <title>" with an ID: line above the first milestone.', 'error', path, first))
    for number, raw in outside(text):
        line = raw.strip()
        if paragraph and (not line or number != paragraph['criteria_end'] + 1 or line.startswith('#')
                          or re.match(r'^- \[[ xX]\]', line) or LOOSE.match(line) or line.split(':', 1)[0].strip() in KEYS
                          or line.split(':', 1)[0].strip() in LANE_KEYS.get(paragraph['kind'], ())):
            paragraph = None
        if paragraph:
            key = 'criteria' if paragraph['criteria'] else 'loose_criteria'
            paragraph[key] += ' ' + line
            paragraph['criteria_end'] = number
            continue
        if line.startswith('# Goal:'):
            goal = node(line[7:].strip(), 'goal', number, markers)
            goals.append(goal)
            current, milestone, parked = goal, None, False
        elif line.startswith('## '):
            title = line[3:].strip()
            parked = title.lower() == 'parked'
            match = re.match(r'^(\d+)\.?\s+(.+)', title)
            if match and goal:
                milestone = node(title, 'milestone', number, markers)
                milestone['id'] = (goal['id'] or 'goal-' + text_id(goal['title'])) + ':' + match[1]
                milestone['number'] = match[1]
                goal['children'].append(milestone)
                current = milestone
            else:
                current, milestone = None, None
        elif not parked and milestone and re.match(r'^- \[[ xX]\]', line):
            match = re.match(r'^- \[([ xX])\]\s+(?:\[([^\]]+)\]\s+)?(.*)', line)
            title = match[3]
            tag = re.search(r'\s+\(([^()]*)\)\s*$', title)
            tags = [x.strip() for x in tag[1].split(',')] if tag else ['any']
            title = title[:tag.start()].rstrip() if tag else title
            task = node(title, 'task', number, markers)
            task.update(id=match[2] or milestone['number'] + '-' + text_id(title),
                        status='done' if match[1].lower() == 'x' else 'open', tags=tags)
            if not match[2]:
                findings.append(finding('missing-task-id', 'Task has a derived ID: ' + task['id'],
                    'Add [' + task['id'] + '] after its checkbox.', 'warning', path, number))
            milestone['children'].append(task)
            current = task
        elif current and LOOSE.match(line):
            # Without its colon the criterion would silently vanish; keep it for lint and the gate.
            current['loose_criteria'] = LOOSE.sub('', line, count=1).strip()
            current['criteria_line'] = current['criteria_end'] = number
            paragraph = current
            findings.append(finding('criteria-format', 'Done when needs a colon; this criterion is ignored.',
                'Write "Done when: ..." (lint --fix previews it).', 'warning', path, number))
        elif current and ':' in line:
            key, value = line.split(':', 1)
            key, value = key.strip(), value.strip()
            if key == 'ID':
                current['id'] = value
            elif key == 'Done when':
                current['criteria'] = value
                current['criteria_line'] = current['criteria_end'] = number
                paragraph = current if value else None
            elif key == 'Checks':
                try:
                    checks = json.loads(value)
                    if not isinstance(checks, list) or not all(isinstance(x, str) and TOKENS.fullmatch(x) for x in checks):
                        raise ValueError()
                    current['checks'] = checks
                except ValueError:
                    findings.append(finding('invalid-checks', 'Checks must be a JSON array of named check tokens.', 'Use Checks: ["validator:unit"].', path=path, line=number))
            elif key == 'Evidence':
                if '=' in value:
                    target, refs = value.split('=', 1)
                    current['evidence'][target.strip()] = [x.strip() for x in refs.split(',') if x.strip()]
                else:
                    findings.append(finding('invalid-evidence', 'Evidence requires target=references.', 'Use Evidence: <id>=<evidence-id-or-commit>.', path=path, line=number))
            elif key == 'Context':
                current['context'].append(value)
            elif key == 'Lane' and current['kind'] == 'task':
                # Lane names are checked against the lanes config only under lanes mode.
                current['lane'] = value
                current['lane_line'] = number
            elif key == 'After' and current['kind'] == 'task':
                current['after'] = [x.strip() for x in value.split(',') if x.strip()]
                current['after_line'] = number
            elif key in ('Signed-off', 'Archive', 'Reason', 'Policy-Approval', 'Completion', 'Exception') or (key == 'Parallel' and current['kind'] == 'goal'):
                current['metadata'].setdefault(key, []).append(value)
    for goal in goals:
        if not goal['id']:
            goal['id'] = 'goal-' + text_id(goal['title'])
            findings.append(finding('missing-goal-id', 'Goal has a derived ID: ' + goal['id'], 'Add ID: ' + goal['id'] + ' below its heading.', 'warning', path, goal['line']))
        validate_node(goal, ids, findings, path, policy)
        for milestone in goal['children']:
            check_criteria(milestone, findings, path)
    for siblings in [goals] + [x['children'] for x in goals]:
        current_nodes = [x for x in siblings if x['status'] == 'current']
        if len(current_nodes) > 1:
            findings.append(finding('multiple-current', 'Multiple current siblings make selection ambiguous.', 'Keep one current marker.', path=path))
        unfinished = False
        for item in siblings:
            if item['status'] in ('done', 'current') and unfinished:
                findings.append(finding('out-of-order', 'Later hierarchy is current/done before earlier unfinished work.', 'Reopen the later milestone or record approved scope/order changes.', path=path, line=item['line']))
            if item['status'] not in ('done', 'shelved', 'dropped'):
                unfinished = True
    mode = 'automatic' if any(x['children'] for x in goals) or (goals and all(x['status'] in ('done', 'shelved', 'dropped') and x['metadata'].get('Archive') for x in goals)) else 'manual'
    if mode == 'manual':
        findings.append(finding('manual-roadmap', 'No numbered milestone hierarchy could be selected.', 'Add ## 1. Title and - [ ] [1.1] Task, or select work manually.', 'warning', path))
    return {'goals': goals, 'mode': mode, 'findings': findings}


def validate_node(item, ids, findings, path, policy):
    if item['id'] in ids:
        findings.append(finding('duplicate-id', 'Duplicate ID: ' + item['id'], 'Assign a unique ID.', path=path, line=item['line']))
    ids.add(item['id'])
    item['checks'] = sorted(set(item['checks']) | set(TOKENS.findall(item['criteria'])))
    children = item['children']
    if item['kind'] == 'milestone' and item['status'] in ('shelved', 'dropped'):
        findings.append(finding('milestone-state', 'Milestones use open/current/done only.', 'Restore an allowed milestone marker.', path=path, line=item['line']))
    if item['status'] == 'done' and children and any(x['status'] != 'done' for x in children):
        findings.append(finding('done-with-open', 'Completed hierarchy contains open children.', 'Reopen the parent or finish its children with evidence.', path=path, line=item['line']))
    if item['kind'] == 'goal' and item['status'] == 'done' and policy['goals and ownership']['goal-signoff'] == 'user' and not (len(item['metadata'].get('Signed-off', [])) == 1 and re.fullmatch(r'[^,]+, \d{4}-\d{2}-\d{2}', item['metadata']['Signed-off'][0])):
        findings.append(finding('missing-signoff', 'Completed goal requires user sign-off.', 'Obtain actual approval and add Signed-off: user, YYYY-MM-DD.', path=path, line=item['line']))
    if item['status'] in ('shelved', 'dropped') and (not item['metadata'].get('Reason') or not item['metadata'].get('Archive')):
        findings.append(finding('missing-stop-record', 'Shelved/dropped goals need a reason and preserved record.', 'Add Reason and Archive after actual user instruction.', path=path, line=item['line']))
    for child in children:
        validate_node(child, ids, findings, path, policy)


def recovered(item):
    """Criteria text the author evidently meant for a milestone, and where it sits."""
    if item.get('criteria'):
        return {'criteria': item['criteria'], 'line': item.get('criteria_line'), 'end': item.get('criteria_end'), 'source': 'criteria'}
    if item.get('loose_criteria'):
        return {'criteria': item['loose_criteria'], 'line': item['criteria_line'], 'end': item['criteria_end'], 'source': 'loose'}
    tasks = item.get('children', [])
    last = tasks[-1] if tasks else None
    # A Done when after the task list attaches to the last task. Only treat it as the
    # milestone's when no other task carries criteria, so per-task criteria stay put.
    if last and (last['criteria'] or last.get('loose_criteria')) and not any(x['criteria'] or x.get('loose_criteria') for x in tasks[:-1]):
        return {'criteria': last['criteria'] or last['loose_criteria'], 'line': last['criteria_line'],
                'end': last['criteria_end'], 'source': 'task', 'task': last['id'], 'loose': not last['criteria']}
    return None


def check_criteria(milestone, findings, path):
    if milestone['criteria'] or not milestone['children']:
        return
    found = recovered(milestone)
    if found and found['source'] == 'task':
        message = 'Milestone has no criteria; the Done when after its tasks attached to task ' + found['task'] + '.'
        remedy = 'Move that Done when paragraph directly under the milestone heading, before the tasks (lint --fix previews it).'
    elif found:
        return  # the colon warning already covers it
    else:
        message, remedy = 'Milestone has tasks but no Done when criteria.', 'Add "Done when: ..." under the milestone heading, before the tasks.'
    findings.append(finding('missing-criteria', message, remedy, 'warning', path, milestone['line']))


def normalized(text):
    """Criteria identity for policy changes: whitespace and .,;: punctuation are not wording."""
    return re.sub(r'[\s.,;:]+', ' ', text or '').strip()


def effective_policy(item):
    found = recovered(item) if item['kind'] == 'milestone' else None
    text = found['criteria'] if found else item['criteria']
    return normalized(text), sorted(set(item['checks']) | set(TOKENS.findall(text or ''))), item['title']


def flatten(goals):
    result = {}
    for item in goals:
        result[item['id']] = item
        result.update(flatten(item['children']))
    return result


def eligibility(task, policy, readiness, blockers):
    """Why a task cannot start now: handoff blockers, unknown tags, unready levels."""
    reasons = list(blockers.get(task['id'], []))
    for tag in task['tags']:
        mapping = policy['capabilities']['tags'].get(tag)
        if mapping is None:
            reasons.append('Unknown capability ' + tag + '; map it under Capabilities tags.')
        else:
            for level in mapping:
                if not readiness.get('levels', {}).get(level, {}).get('ready', False):
                    reasons.append('Missing readiness ' + level + '; ' + readiness.get('recovery', 'run authorized startup and provide its readiness report.'))
    return reasons


def select(parsed, policy, readiness, blockers):
    if policy['state']['state'] == 'dormant':
        return {'mode': 'dormant', 'task': None}
    if parsed['mode'] == 'manual' or any(x.severity == 'error' for x in parsed['findings']):
        return {'mode': 'manual', 'task': None}
    goal = next((x for x in parsed['goals'] if x['status'] not in ('done', 'shelved', 'dropped')), None)
    if goal is None:
        return {'mode': 'no-active-goal', 'task': None}
    milestone = next((x for x in goal['children'] if x['status'] != 'done'), None)
    context = {'goal': goal['id'], 'goal_title': goal['title'], 'task': None}
    if milestone is None:
        return dict(context, mode='awaiting-signoff')
    context.update(milestone=milestone['id'], milestone_title=milestone['title'], context=milestone['context'],
                   progress={'done': sum(x['status'] == 'done' for x in milestone['children']), 'total': len(milestone['children'])})
    unavailable = []
    for task in milestone['children']:
        if task['status'] == 'done':
            continue
        reasons = eligibility(task, policy, readiness, blockers)
        if not reasons:
            return dict(context, mode='selected', task=task, blocked=unavailable)
        unavailable.append({'task': task['id'], 'reasons': reasons})
    return dict(context, mode='all-blocked' if unavailable else 'milestone-acceptance', blocked=unavailable)
