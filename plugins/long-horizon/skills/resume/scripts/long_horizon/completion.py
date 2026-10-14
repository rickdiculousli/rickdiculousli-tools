"""Completion archives: one rule set to load, validate, build and pre-check them.

The gate, status, lint and `archive prepare/check` all call this module, so an archive the
builder calls valid is one the gate accepts. Nothing here edits the roadmap or invents
approval: user-reserved decisions are reported as approvals to obtain, never filled in.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from .git import confined
from .goals import TOKENS
from .model import Invalid, finding

FENCE = re.compile(r'```json\s*\n(.*?)\n```', re.S)
FILL = '<fill:'
# Archive evidence may cite a record bare or in the goals file's `task=<id>` form.
CITED = re.compile(r'^(?:[^=\s]+=)?([0-9a-f]{64})$')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
TERMINAL = ('done', 'shelved', 'dropped')
REQUIRED = {'version', 'goal_id', 'status', 'outcome', 'milestones', 'goal_checks', 'signoff', 'limitations', 'refuted', 'followups'}


def fill(what):
    return FILL + ' ' + what + '>'


def parse_text(text):
    match = FENCE.search(text)
    if not match:
        raise Invalid('Archive needs a version-1 JSON metadata fence.')
    return json.loads(match[1])


def load(item, policy, status=None):
    """The goal's archive JSON, schema-checked; `status` validates a goal about to be completed."""
    refs = item['metadata'].get('Archive', [])
    if len(refs) != 1:
        raise Invalid('Goal needs one Archive: <tracked-path> completion record.')
    path = confined(policy['_base'], refs[0])
    value = parse_text(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or not REQUIRED <= value.keys() or value['version'] != 1 or value['goal_id'] != item['id'] or value['status'] != (status or item['status']):
        raise Invalid('Archive identity/status/schema does not match the goal.')
    if not isinstance(value['milestones'], list) or not isinstance(value['goal_checks'], list) or not value['milestones']:
        raise Invalid('Archive requires ordered milestone summaries and goal checks.')
    if (status or item['status']) in ('shelved', 'dropped'):
        if not value.get('reason') or not value.get('original_roadmap'):
            raise Invalid('Shelved/dropped archive must preserve reason and original_roadmap.')
    else:
        if not value['outcome'] or not value['goal_checks']:
            raise Invalid('Completed archive needs goal criteria/checks and outcome.')
        for summary in value['milestones']:
            if not isinstance(summary, dict) or not all(summary.get(k) for k in ('id', 'criteria', 'evidence')):
                raise Invalid('Completed archive milestone needs id, criteria and evidence.')
    return value


def unfilled(value, where=''):
    """Paths of builder slots still holding a `<fill: ...>` placeholder."""
    if isinstance(value, str):
        return [where or 'value'] if value.lstrip().startswith(FILL) else []
    if isinstance(value, dict):
        return [x for key, item in value.items() for x in unfilled(item, where + ('.' if where else '') + str(key))]
    if isinstance(value, list):
        return [x for index, item in enumerate(value) for x in unfilled(item, '%s[%d]' % (where, index))]
    return []


def cited(entries):
    """Evidence IDs among archive entries; prose, commits and tree hashes are not proof."""
    ids = []
    for entry in entries or []:
        match = CITED.match(entry.strip()) if isinstance(entry, str) else None
        if match:
            ids.append(match[1])
    return ids


def required(summary):
    return sorted(set(summary.get('checks', TOKENS.findall(summary.get('criteria', '')))))


def proof(summary, records, candidates=None):
    """{check: proving record ID or None} for one milestone's required checks."""
    criteria = ' '.join(summary['criteria'].split())
    checks = required(summary)
    ids = cited(summary.get('evidence', []) + summary.get('exceptions', [])) if candidates is None else candidates
    found = {}
    for check in checks:
        found[check] = None
        for id_ in ids:
            record = records.get(id_)
            if not record:
                continue
            target = next((x for x in record.get('criteria', []) if x.get('id') == summary['id']), None)
            if not target or target['criteria'] != criteria or target['checks'] != checks:
                continue
            if record.get('exception'):
                ok = record.get('target') == summary['id'] and record.get('check') == check
            else:
                ok = record.get('name') == check and record.get('outcome') == 'PASS' and record.get('stable') is True and record.get('exit') == 0
            if ok:
                found[check] = id_
    return found


def gaps(summary, records, candidates=None):
    """Why a milestone's recorded proof does not validate; empty when it does."""
    checks = required(summary)
    if not checks:
        return ['%s has no named checks (it closed before Checks existed or never had them)' % summary['id']]
    return ['%s has no recorded PASS for %s under its current criteria' % (summary['id'], check)
            for check, id_ in proof(summary, records, candidates).items() if id_ is None]


def legacy(value):
    """Milestones covered by the archive's user-approved legacy acceptance, and its problems."""
    block = value.get('legacy_acceptance')
    if block is None:
        return set(), []
    known = [x.get('id') for x in value['milestones'] if isinstance(x, dict)]
    problems = []
    if not isinstance(block, dict):
        return set(), ['legacy_acceptance must be an object with milestones, approved_by, date and reason.']
    ids = block.get('milestones')
    if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids) or len(set(ids)) != len(ids):
        problems.append('legacy_acceptance.milestones must list each covered milestone ID once.')
        ids = []
    unknown = [x for x in ids if x not in known]
    if unknown:
        problems.append('legacy_acceptance names milestones the archive does not have: ' + ', '.join(unknown) + '.')
    for key in ('approved_by', 'reason'):
        if not isinstance(block.get(key), str) or not block[key].strip():
            problems.append('legacy_acceptance.%s must say %s.' % (key, 'who approved it' if key == 'approved_by' else 'why the proof is legacy'))
    if not isinstance(block.get('date'), str) or not DATE.fullmatch(block['date']):
        problems.append('legacy_acceptance.date must be the approval date, YYYY-MM-DD.')
    return set(ids), problems


def record_problems(value, records):
    """Every milestone proof problem, honoring explicit legacy acceptance."""
    covered, problems = legacy(value)
    for summary in value['milestones']:
        missing = gaps(summary, records)
        if summary['id'] in covered:
            if not missing:
                problems.append(summary['id'] + ' already has recorded proof; remove it from legacy_acceptance.')
        else:
            problems += ['Archive has no matching accepted criterion proof: ' + x + '; record it, or cover the milestone with user-approved legacy_acceptance.' for x in missing]
    return problems


def validate(item, policy, value, records, expected, final=True):
    """All problems with a completed goal's archive; `final` also requires recorded sign-off."""
    problems = []
    summaries = value['milestones']
    if not expected or [x['id'] for x in expected] != [x.get('id') for x in summaries]:
        problems.append('Archive must preserve every ordered milestone.')
    else:
        for before, summary in zip(expected, summaries):
            if summary.get('criteria') != before['criteria'] or required(summary) != before['checks']:
                problems.append('Archive must preserve exact milestone criteria and required check lists: ' + before['id'] + '.')
    problems += record_problems(value, records)
    if sorted(set(value['goal_checks'])) != item['checks'] or not value['outcome']:
        problems.append('Archive must preserve goal checks and readable outcome.')
    slots = unfilled(value)
    if slots:
        problems.append('Archive has unfilled slots: ' + ', '.join(slots) + '.')
    if final and policy['goals and ownership']['goal-signoff'] == 'user' and (not value['signoff'] or not item['metadata'].get('Signed-off')):
        problems.append('Archive and goal require actual sign-off.')
    return problems


def slug(title):
    return re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or 'goal'


def path_for(item, policy):
    """The goal's archive path relative to the checkout: its Archive line, else the default name."""
    refs = item['metadata'].get('Archive', [])
    if refs:
        return refs[0]
    folder = policy['continuation']['archive'].rstrip('/')
    name = folder + '/' + datetime.now(timezone.utc).strftime('%Y-%m-%d') + '-' + slug(item['title'])
    existing = confined(policy['_base'], name + '.md')
    if existing.is_file():
        try:
            if parse_text(existing.read_text(encoding='utf-8')).get('goal_id') != item['id']:
                name += '-' + slug(item['id'])
        except (Invalid, ValueError, AttributeError):
            name += '-' + slug(item['id'])
    return name + '.md'


def citations(milestone):
    """`task=ref` references the goals file cites for a milestone and its tasks."""
    refs = []
    for node in [milestone] + milestone['children']:
        for target, values in node['evidence'].items():
            refs += [target + '=' + x for x in values]
    return list(dict.fromkeys(refs))


def build(policy, goal, records, existing=None):
    """The version-1 completion JSON for `goal`, merged with an existing archive's filled parts."""
    previous = {x.get('id'): x for x in (existing or {}).get('milestones', []) if isinstance(x, dict)}
    milestones, needs_legacy = [], []
    for milestone in goal['children']:
        summary = {'id': milestone['id'], 'title': re.sub(r'^\d+\.?\s+', '', milestone['title']),
                   'criteria': milestone['criteria'], 'checks': milestone['checks']}
        found = proof(summary, records, list(records))
        ids = [x for x in dict.fromkeys(found.values()) if x]
        old = previous.get(milestone['id'], {})
        proved = [x for x in ids if not records[x].get('exception')]
        excepted = [x for x in ids if records[x].get('exception')]
        # Keep what a person wrote (prose, citations) unless it restates a proving ID.
        carried = [x for x in old.get('evidence', []) if not (cited([x]) and cited([x])[0] in ids)]
        kept_exceptions = [x for x in old.get('exceptions', []) if not (cited([x]) and cited([x])[0] in ids)]
        summary['evidence'] = proved + carried
        summary['exceptions'] = excepted + kept_exceptions
        if gaps(summary, records, list(records)):
            needs_legacy.append(milestone['id'])
            if not carried:
                summary['evidence'] = proved + (citations(milestone) or [fill('cite the commits, notes or prose that accepted this milestone')])
        if not summary['evidence']:
            summary['evidence'] = [fill('cite this milestone\'s evidence')]
        milestones.append(summary)
    old = existing or {}
    value = dict(old)
    value.update({'version': 1, 'goal_id': goal['id'], 'status': 'done', 'milestones': milestones,
                  'goal_checks': goal['checks']})
    if goal['criteria']:
        value['goal_criteria'] = goal['criteria']
    value.setdefault('outcome', fill('one line on what the goal delivered'))
    value.setdefault('signoff', {'owner': policy['goals and ownership']['goal-signoff'],
                                 'by': fill('who signed off, after they actually did'), 'date': fill('YYYY-MM-DD')})
    for key, what in (('limitations', 'known limitations; use [] if there are none'),
                      ('refuted', 'ideas that were tried and refuted; use [] if none'),
                      ('followups', 'follow-up work; use [] if none')):
        value.setdefault(key, [fill(what)])
    if needs_legacy and 'legacy_acceptance' not in value:
        value['legacy_acceptance'] = {'milestones': needs_legacy, 'approved_by': fill('the user who approved accepting these milestones on their cited evidence'),
                                      'date': fill('YYYY-MM-DD of that approval'),
                                      'reason': fill('why their proof is legacy, e.g. closed before Checks existed or proved in prose')}
    order = ['version', 'goal_id', 'status', 'outcome', 'milestones', 'goal_criteria', 'goal_checks', 'legacy_acceptance',
             'signoff', 'limitations', 'refuted', 'followups']
    return {key: value[key] for key in order if key in value} | {k: v for k, v in value.items() if k not in order}, needs_legacy


def render(goal, value, text=None):
    fence = '```json\n' + json.dumps(value, indent=2, ensure_ascii=False) + '\n```'
    if text is not None:
        match = FENCE.search(text)
        return text[:match.start()] + fence + text[match.end():]
    return ('# Completion archive: ' + goal['title'] + '\n\nGoal `' + goal['id'] + '`. The JSON below is the completion record '
            'the long-horizon gate verifies; prose may be added around it.\n\n' + fence + '\n')


def target(parsed, goal_id=None):
    """The goal to close: an explicit ID, the active goal awaiting sign-off, else the latest completed goal."""
    goals = parsed['goals']
    if goal_id:
        goal = next((x for x in goals if x['id'] == goal_id), None)
        if goal is None:
            raise Invalid('No goal with ID ' + goal_id + '.')
        return goal
    goal = next((x for x in goals if x['status'] not in TERMINAL), None)
    if goal is None:
        done = [x for x in goals if x['status'] == 'done' and (x['children'] or x['metadata'].get('Archive'))]
        if done:
            return done[-1]
    if goal is None or not goal['children'] or any(x['status'] != 'done' for x in goal['children']):
        raise Invalid('No active goal has all milestones done; pass --goal ID to build an archive early.')
    return goal


def plan(git, policy, goal, records, acceptance):
    """Build the archive for `goal` and list every gap and user approval closing it needs."""
    if goal['status'] in ('shelved', 'dropped'):
        raise Invalid('archive prepare builds completion archives; shelved/dropped records follow setup\'s preserved-record flow.')
    if not goal['children']:
        raise Invalid('Goal ' + goal['id'] + ' has no milestones to archive.')
    relative = path_for(goal, policy)
    path = confined(policy['_base'], relative)
    text = path.read_text(encoding='utf-8') if path.is_file() else None
    existing = None
    if text is not None:
        try:
            existing = parse_text(text)
        except (Invalid, ValueError) as error:
            raise Invalid('Existing archive ' + relative + ' has no parseable version-1 JSON fence (' + str(error) + '); repair or move it first.') from None
        if not isinstance(existing, dict) or existing.get('goal_id') != goal['id']:
            raise Invalid('Existing archive ' + relative + ' belongs to another goal; fix the goal\'s Archive line.')
    value, needs_legacy = build(policy, goal, records, existing)
    content = render(goal, value, text)
    item = dict(goal, status='done')
    reserved = policy['goals and ownership']['milestone-policy'] == 'user'
    gaps_, approvals, goal_lines = [], [], []
    if not goal['metadata'].get('Archive'):
        goal_lines.append('Archive: ' + relative)
        gaps_.append({'code': 'archive-pointer', 'message': 'The goal has no Archive line.', 'fix': 'Add "Archive: ' + relative + '" under the goal ID.'})
    if text != content:
        gaps_.append({'code': 'archive-unwritten', 'message': 'The archive file is ' + ('missing' if text is None else 'not the prepared content') + ': ' + relative + '.',
                      'fix': 'Review and run archive prepare --write (filled slots are kept).'})
    if not goal['criteria'] or not goal['checks']:
        missing = 'Done when' if not goal['criteria'] else 'named Checks'
        approvals.append({'kind': 'goal-criteria', 'reserved': reserved,
                          'message': 'The goal has no %s of its own; the completion gate needs criteria with named checks.' % missing,
                          'proposal': [('Done when: ' + goal['criteria']) if goal['criteria'] else 'Done when: ' + fill('what finishing this goal means, in the user\'s words'),
                                       'Checks: ["' + fill('a declared check proving it, often the last milestone\'s review') + '"]',
                                       'Policy-Approval: ' + fill('who') + ' approved the goal\'s Done when and Checks at sign-off, ' + fill('YYYY-MM-DD')]})
    else:
        fresh = {x['check']: x for x in acceptance}
        for check in goal['checks']:
            if fresh.get(check, {}).get('status') != 'fresh':
                gaps_.append({'code': 'goal-check', 'message': 'The goal check ' + check + ' has no fresh PASS for the current goal criteria.',
                              'fix': 'Record it (evidence prepare/record, or evidence rerecord after a criteria change).'})
    slots = unfilled(value)
    # Until the user has approved legacy acceptance, its proof gaps are that one approval.
    legacy_open = any(x.startswith('legacy_acceptance') for x in slots)
    if needs_legacy and legacy_open:
        reasons = {m['id']: gaps({'id': m['id'], 'criteria': m['criteria'], 'checks': m['checks']}, records, list(records))
                   for m in goal['children'] if m['id'] in needs_legacy}
        approvals.append({'kind': 'legacy-acceptance', 'reserved': True, 'milestones': reasons,
                          'message': 'Milestones ' + ', '.join(needs_legacy) + ' have no recorded proof for their named checks; accepting them on their cited evidence needs the user\'s explicit approval, recorded as the archive\'s legacy_acceptance (who, date, which milestones, why).'})
    signed = goal['metadata'].get('Signed-off') and not any(x.startswith('signoff') for x in slots)
    if policy['goals and ownership']['goal-signoff'] == 'user' and not signed:
        approvals.append({'kind': 'signoff', 'reserved': True, 'message': 'Goal sign-off is the user\'s.',
                          'proposal': ['Signed-off: user, ' + fill('YYYY-MM-DD')]})
    agent_slots = [x for x in slots if not x.startswith(('signoff', 'legacy_acceptance'))]
    if agent_slots:
        gaps_.append({'code': 'archive-slots', 'message': 'Archive slots to fill: ' + ', '.join(agent_slots) + '.',
                      'fix': 'Fill them from the handoff, findings and roadmap; write [] for an empty list.'})
    problems = [x for x in validate(item, policy, value, records, goal['children'], final=False)
                if not x.startswith('Archive has unfilled slots')
                and not (legacy_open and x.startswith(('Archive has no matching accepted criterion proof', 'legacy_acceptance')))]
    gaps_ += [{'code': 'archive-invalid', 'message': x, 'fix': 'Repair the roadmap or archive.'} for x in problems]
    return {'goal': goal['id'], 'path': relative, 'value': value, 'content': content, 'current': text == content,
            'gaps': gaps_, 'approvals': approvals, 'goal_lines': goal_lines,
            'pending_evidence': sorted({x for m in value['milestones'] for x in cited(m['evidence'] + m['exceptions'])
                                        if records.get(x, {}).get('pending')})}


def ask(plan_):
    """One Needs-you line: sign-off plus every approval that should be asked with it."""
    extra = []
    for item in plan_['approvals']:
        if item['kind'] == 'goal-criteria':
            extra.append('the goal\'s own Done when/Checks (propose wording)')
        elif item['kind'] == 'legacy-acceptance':
            extra.append('legacy acceptance for ' + ', '.join(item['milestones']))
    return 'sign off the completed goal' + ('; approve with it: ' + '; '.join(extra) if extra else '')


def early(policy, parsed, records):
    """Warnings for an active goal that would stall at sign-off, raised as soon as they are true."""
    findings = []
    path = policy['_goals']
    for goal in parsed['goals']:
        if goal['status'] in TERMINAL or not goal['children']:
            continue
        if not goal['criteria'] or not goal['checks']:
            findings.append(finding('goal-criteria-missing', 'Goal %s has no %s of its own; its completion gate will fail.' % (goal['id'], 'Done when' if not goal['criteria'] else 'named Checks'),
                'Propose goal criteria and Checks to the user now and record Policy-Approval, rather than at sign-off.', 'warning', path, goal['line']))
        for milestone in goal['children']:
            if milestone['status'] != 'done':
                continue
            missing = gaps({'id': milestone['id'], 'criteria': milestone['criteria'], 'checks': milestone['checks']}, records, list(records))
            if missing:
                findings.append(finding('milestone-proof-missing', 'Done milestone without recorded proof: ' + '; '.join(missing) + '.',
                    'Record its checks (or evidence rerecord after a criteria change), or plan user-approved legacy acceptance at sign-off.', 'warning', path, milestone['line']))
    return findings
