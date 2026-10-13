"""Parallel lanes: the lanes config, its lint, per-lane selection and the judge overview.

Everything here runs only when the overlay's ## Lanes section names a config file.
"""
import re
from pathlib import Path
from .git import confined
from .goals import LANE, flatten, eligibility
from .model import Invalid, finding

PARALLEL = re.compile(r'^lanes,\s*([^,]+?),\s*(\d{4}-\d{2}-\d{2})$')
LANES_LINE = re.compile(r'^Lanes:\s*(\d+)\s+lanes?,\s*run\s+(\S+)')
UNASSIGNED = 'unassigned'
SECTIONS = ('status', 'next', 'asks')


def load(policy, git):
    """Read the lanes TOML; a missing or malformed file is a finding and no config."""
    path = Path(policy['_base']) / policy['lanes']['config']
    if not path.is_file():
        return None, [finding('lanes-config-missing', 'Lanes config does not exist: ' + policy['lanes']['config'],
                              'Create it (long-horizon:setup can scaffold it from a lane plan) or fix the ## Lanes config path.',
                              'error', path)]
    from .toml_subset import load_text
    try:
        data = load_text(path.read_text(encoding='utf-8'))
        config = normalize(data)
    except (Invalid, ValueError, TypeError, UnicodeError) as error:
        return None, [finding('lanes-config-invalid', 'Lanes config is invalid: ' + str(error),
                              'Repair the TOML: a [lanes.<name>] table per lane, each with an optional host string.',
                              'error', path)]
    config['path'] = str(path)
    return config, []


def json_safe(value, where='lanes config'):
    """Both TOML readers must agree: dates, times and other non-JSON values are rejected."""
    if isinstance(value, dict):
        for key, item in value.items():
            json_safe(item, where + '.' + str(key))
    elif isinstance(value, list):
        for item in value:
            json_safe(item, where)
    elif not isinstance(value, (str, int, float, bool)) or value is None:
        raise Invalid(where + ': only strings, integers, floats, booleans, arrays and tables are supported.')
    return value


def normalize(data):
    json_safe(data)
    lanes = data.get('lanes')
    if not isinstance(lanes, dict) or not lanes:
        raise Invalid('expected at least one [lanes.<name>] table.')
    result = {'lanes': {}, 'run': data.get('run') if isinstance(data.get('run'), dict) else {}}
    for name, spec in lanes.items():
        if not LANE.fullmatch(name) or name == UNASSIGNED:
            raise Invalid('lane names are a letter or digit followed by letters, digits, _ or -, and never ' + UNASSIGNED + ': ' + name)
        if not isinstance(spec, dict):
            raise Invalid('[lanes.' + name + '] must be a table.')
        host = spec.get('host', 'any')
        if not isinstance(host, str) or not host:
            raise Invalid('[lanes.' + name + '] host must be a nonempty string.')
        for key in ('owns', 'validators'):
            if key in spec and (not isinstance(spec[key], list) or not all(isinstance(x, str) for x in spec[key])):
                raise Invalid('[lanes.' + name + '] ' + key + ' must be a string array.')
        result['lanes'][name] = {'host': host, 'owns': spec.get('owns', []), 'validators': spec.get('validators', [])}
    return result


def active_goal(parsed):
    return next((x for x in parsed['goals'] if x['status'] not in ('done', 'shelved', 'dropped')), None)


def open_milestones(goal):
    return [x for x in goal['children'] if x['status'] != 'done']


def tasks_of(goal, done=False):
    """Tasks the lanes run: every task of the goal's unfinished milestones, in roadmap order."""
    return [task for milestone in open_milestones(goal) for task in milestone['children'] if done or task['status'] != 'done']


def parallel_approval(goal):
    values = goal['metadata'].get('Parallel', [])
    match = PARALLEL.match(values[0].strip()) if len(values) == 1 else None
    return {'by': match[1].strip(), 'date': match[2]} if match else None


def config_changed_after(git, policy, approval_line):
    """True when the lanes config has uncommitted changes or commits after the one that recorded the approval."""
    try:
        relative = confined(policy['_base'], policy['lanes']['config']).relative_to(git.root).as_posix()
        goals_relative = Path(policy['_goals']).relative_to(git.root).as_posix()
    except (Invalid, ValueError):
        return False
    if not git.run('ls-files', '--', relative).strip():
        return False  # an untracked draft has no history to compare
    if any(line[3:] == relative for line in git.dirty()):
        return True
    # The commit that last changed the Parallel line is the approval; config commits after it need re-approval.
    approved = git.run('log', '-1', '--no-show-signature', '--format=%H', '-S', approval_line, '--', goals_relative, check=False).strip()
    if not approved:
        return False  # the approval itself is not committed yet
    return bool(git.run('log', '--no-show-signature', '--format=%H', approved + '..HEAD', '--', relative, check=False).strip())


def cycle(tasks):
    """One After: cycle as an ordered id list, or None."""
    graph = {task['id']: [x for x in task['after']] for task in tasks}
    state = {}
    stack = []

    def visit(node):
        state[node] = 'active'
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 'active':
                return stack[stack.index(nxt):] + [nxt]
            if nxt not in state:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 'done'
        return None

    for node in graph:
        if node not in state:
            found = visit(node)
            if found:
                return found
    return None


def lint(policy, git, parsed, config, continuation):
    """Lanes-mode findings; nothing is reported for repositories without a lanes config."""
    if not policy['_lanes']:
        return []
    path = policy['_goals']
    findings = []
    nodes = flatten(parsed['goals'])
    goal = active_goal(parsed)
    names = set(config['lanes']) if config else set()
    hosts = {spec['host'] for spec in config['lanes'].values() if spec['host'] != 'any'} if config else set()
    if goal:
        approval = parallel_approval(goal)
        if not approval:
            findings.append(finding('parallel-approval-missing', 'Lanes mode needs the goal\'s Parallel approval: ' + goal['id'],
                'After actual approval add "Parallel: lanes, <who>, YYYY-MM-DD" under the goal heading.', 'error', path, goal['line']))
        elif config and config_changed_after(git, policy, goal['metadata']['Parallel'][0]):
            findings.append(finding('lanes-config-changed', 'The lanes config changed after its Parallel approval on ' + approval['date'] + '.',
                'Re-approve the lane plan and update the Parallel date, or revert the config change.', 'error', config['path']))
        all_tasks = [task for milestone in goal['children'] for task in milestone['children']]
        for task in tasks_of(goal):
            if task['lane'] is None:
                findings.append(finding('lane-missing', 'Open task has no Lane: ' + task['id'],
                    'Add "Lane: <name>" (or "Lane: unassigned") under the task; the judge assigns lanes.', 'error', path, task['line']))
            elif config and task['lane'] != UNASSIGNED and task['lane'] not in names:
                findings.append(finding('lane-unknown', 'Task ' + task['id'] + ' names a lane the config does not declare: ' + task['lane'],
                    'Use one of ' + ', '.join(sorted(names)) + ' or add a [lanes.' + task['lane'] + '] table.', 'error', path, task.get('lane_line', task['line'])))
            elif config and task['lane'] in names:
                needed = sorted(set(task.get('tags', [])) & hosts)
                if needed and config['lanes'][task['lane']]['host'] not in needed:
                    findings.append(finding('mac-task-on-non-native-lane', 'Task ' + task['id'] + ' needs host ' + '/'.join(needed) +
                        ' but lane ' + task['lane'] + ' runs on ' + config['lanes'][task['lane']]['host'] + '.',
                        'Assign it to a lane whose host matches its capability tag, or drop the tag after approval.', 'error', path, task['line']))
        for task in all_tasks:
            for ref in task['after']:
                target = nodes.get(ref)
                if target is None or target['kind'] != 'task':
                    findings.append(finding('after-missing', 'Task ' + task['id'] + ' waits for an unknown task: ' + ref,
                        'Point After: at an existing task ID or remove it.', 'error', path, task.get('after_line', task['line'])))
        loop = cycle(all_tasks)
        if loop:
            findings.append(finding('after-cycle', 'After: dependencies form a cycle: ' + ' -> '.join(loop),
                'Break the cycle so every lane can start somewhere.', 'error', path, nodes[loop[0]]['line']))
    if config:
        folder = Path(policy['_base']) / policy['lanes']['lane-files']
        handoff_text = ''
        handoff_path = Path(policy['_handoff'])
        if handoff_path.is_file():
            handoff_text = handoff_path.read_text(encoding='utf-8')
        for name in sorted(names):
            lane_file = folder / (name + '.md')
            if not lane_file.is_file():
                findings.append(finding('lane-file-missing', 'Lane ' + name + ' has no lane file.',
                    'Create ' + policy['lanes']['lane-files'] + '/' + name + '.md with ## Status, ## Next and ## Asks.', 'warning', lane_file))
            else:
                text = lane_file.read_text(encoding='utf-8').lower()
                missing = [x for x in SECTIONS if '## ' + x not in text]
                if missing:
                    findings.append(finding('lane-file-template', 'Lane file for ' + name + ' lacks: ' + ', '.join('## ' + x.title() for x in missing),
                        'Add the missing headings; the lane file is the lane\'s durable handoff.', 'warning', lane_file))
            if handoff_text and not any(link.split('#')[0].endswith(policy['lanes']['lane-files'].strip('/') + '/' + name + '.md') or
                                         link.split('#')[0].endswith('/' + name + '.md') and 'lanes' in link
                                         for link in continuation.get('context', [])):
                findings.append(finding('handoff-lane-link', 'Handoff has no Context link to the lane file for ' + name + '.',
                    'Add "- [' + name + '](' + policy['lanes']['lane-files'] + '/' + name + '.md)" under ## Context.', 'warning', handoff_path))
        if handoff_text:
            matches = [LANES_LINE.match(line.strip()) for line in handoff_text.splitlines()]
            matches = [x for x in matches if x]
            if not matches or int(matches[0][1]) != len(names):
                findings.append(finding('handoff-lanes-line', 'Handoff lacks a current "Lanes: <n> lanes, run <id>" line for ' + str(len(names)) + ' lanes.',
                    'Add or update the Lanes: line near Next:.', 'warning', handoff_path))
    return findings


def task_blockers(task, nodes, policy, readiness, blockers):
    reasons = eligibility(task, policy, readiness, blockers)
    for ref in task['after']:
        target = nodes.get(ref)
        if target is None:
            reasons.append('After: ' + ref + ' does not exist.')
        elif target['status'] != 'done':
            reasons.append('Waits for ' + ref + ' (' + target['status'] + ', lane ' + (target.get('lane') or 'none') + ').')
    return reasons


def context(goal):
    milestone = next(iter(open_milestones(goal)), None)
    data = {'goal': goal['id'], 'goal_title': goal['title'], 'task': None}
    if milestone:
        data.update(milestone=milestone['id'], milestone_title=milestone['title'], context=milestone['context'],
                    progress={'done': sum(x['status'] == 'done' for x in milestone['children']), 'total': len(milestone['children'])})
    return data


def preamble(parsed, policy):
    """Shared early exits; None means lanes selection applies."""
    if policy['state']['state'] == 'dormant':
        return {'mode': 'dormant', 'task': None}
    if parsed['mode'] == 'manual' or any(x.severity == 'error' for x in parsed['findings']):
        return {'mode': 'manual', 'task': None}
    goal = active_goal(parsed)
    if goal is None:
        return {'mode': 'no-active-goal', 'task': None}
    if not open_milestones(goal):
        return dict(context(goal), mode='awaiting-signoff')
    return None


def select_lane(parsed, policy, readiness, blockers, config, lane):
    """The first open task on this lane whose After: tasks are done, walking milestones in order."""
    if config is None:
        return {'mode': 'manual', 'task': None, 'lane': lane}
    if lane not in config['lanes']:
        raise Invalid('Unknown lane ' + lane + '; the lanes config declares: ' + ', '.join(sorted(config['lanes'])) + '.')
    early = preamble(parsed, policy)
    if early:
        return dict(early, lane=lane)
    goal = active_goal(parsed)
    nodes = flatten(parsed['goals'])
    result = dict(context(goal), lane=lane)
    unavailable = []
    for milestone in open_milestones(goal):
        for task in milestone['children']:
            if task['status'] == 'done' or task['lane'] != lane:
                continue
            reasons = task_blockers(task, nodes, policy, readiness, blockers)
            if not reasons:
                result.update(milestone=milestone['id'], milestone_title=milestone['title'], context=milestone['context'],
                              progress={'done': sum(x['status'] == 'done' for x in milestone['children']), 'total': len(milestone['children'])})
                return dict(result, mode='selected', task=task, blocked=unavailable)
            unavailable.append({'task': task['id'], 'reasons': reasons})
    return dict(result, mode='all-blocked' if unavailable else 'lane-done', blocked=unavailable)


def judge(parsed, policy):
    early = preamble(parsed, policy)
    if early:
        return early
    return dict(context(active_goal(parsed)), mode='judge')


def critical_path(tasks):
    """The longest chain of open tasks through After: edges, earliest first; empty on a cycle."""
    by_id = {x['id']: x for x in tasks if x['status'] != 'done'}
    successors = {key: [] for key in by_id}
    for task in by_id.values():
        for ref in task['after']:
            if ref in by_id:
                successors[ref].append(task['id'])
    if cycle(list(by_id.values())):
        return []
    best = {}

    def longest(node):
        if node not in best:
            chains = [longest(x) for x in successors[node]]
            best[node] = [node] + (max(chains, key=len) if chains else [])
        return best[node]

    chains = [longest(x) for x in by_id]
    return max(chains, key=len) if chains else []


def overview(parsed, policy, readiness, blockers, config):
    """What the judge sees: every lane's open, eligible, blocked and done tasks, plus the critical path."""
    goal = active_goal(parsed)
    data = {'config': policy['lanes']['config'], 'names': sorted(config['lanes']) if config else [],
            'run': (config or {}).get('run', {}), 'done': [], 'open': [], 'eligible': [], 'blocked': [], 'critical_path': [], 'per_lane': {}}
    if config:
        data['hosts'] = {name: spec['host'] for name, spec in config['lanes'].items()}
    if goal is None or parsed['mode'] == 'manual':
        return data
    nodes = flatten(parsed['goals'])
    for name in data['names'] + [UNASSIGNED]:
        data['per_lane'][name] = {'open': [], 'eligible': [], 'blocked': [], 'done': []}
    tasks = tasks_of(goal, done=True)
    for task in tasks:
        lane = task['lane'] if task['lane'] in data['per_lane'] else UNASSIGNED
        if task['status'] == 'done':
            data['done'].append(task['id'])
            data['per_lane'][lane]['done'].append(task['id'])
            continue
        data['open'].append(task['id'])
        data['per_lane'][lane]['open'].append(task['id'])
        reasons = task_blockers(task, nodes, policy, readiness, blockers)
        if reasons:
            data['blocked'].append({'task': task['id'], 'lane': task['lane'], 'reasons': reasons})
            data['per_lane'][lane]['blocked'].append(task['id'])
        else:
            data['eligible'].append(task['id'])
            data['per_lane'][lane]['eligible'].append(task['id'])
    data['critical_path'] = critical_path(tasks)
    return data


def scaffold(plan):
    """A lanes.toml draft from a lane plan: [{'name', 'owns', 'validators', 'host'}], plus run settings."""
    lines = ['[run]']
    for key, value in plan.get('run', {}).items():
        lines.append(key + ' = ' + toml_value(value))
    for lane in plan['lanes']:
        name = lane['name']
        if not LANE.fullmatch(name) or name == UNASSIGNED:
            raise Invalid('Invalid lane name: ' + name)
        lines += ['', '[lanes.' + name + ']',
                  'owns = ' + toml_value(lane.get('owns', [])),
                  'validators = ' + toml_value(lane.get('validators', [])),
                  'host = ' + toml_value(lane.get('host', 'any'))]
    return '\n'.join(lines) + '\n'


def toml_value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return '[' + ', '.join(toml_value(x) for x in value) + ']'
    if isinstance(value, str):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    raise Invalid('Unsupported lanes config value: ' + repr(value))
