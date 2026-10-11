import re
from pathlib import Path
from .goals import outside, flatten
from .model import finding

# Narrow patterns; report their category only, never the matched bytes.
SECRETS = [r'\b(?:sk|ghp|github_pat)-[A-Za-z0-9_]{20,}', r'\bghp_[A-Za-z0-9]{30,}', r'\bgithub_pat_[A-Za-z0-9_]{20,}', r'\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}',
           r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
           r'(?i)\b(?:password|api[_-]?key|access[_-]?token)\s*[:=]\s*["\']?[^\s"\']{12,}']
LIVE = r'(?i)\b(?:agent[_-]?id|live[_-]?agent)\s*[:=]\s*\S+'


def inspect(policy, git, parsed):
    path = Path(policy['_handoff'])
    findings, blockers, decisions, links = [], {}, [], []
    if not path.is_file():
        return {'state': 'missing', 'blockers': {}, 'decisions': [], 'context': []}, [finding('handoff-missing', 'Handoff is missing.', 'Create the handoff from the setup template.', 'warning', path)]
    text = path.read_text(encoding='utf-8')
    ids = flatten(parsed['goals'])
    section = ''
    for number, raw in outside(text):
        line = raw.strip()
        if line.startswith('## '):
            section = line[3:].strip().lower()
        if line.startswith('Next:'):
            match = re.match(r'^Next:\s*(?:\[([^\]]+)\]|([\w-]+\.[\w.-]+|\d+-[0-9a-f]{12}))', line)
            if match and (match[1] or match[2]) not in ids:
                findings.append(finding('unknown-next-task', 'Handoff next task no longer exists.', 'Reconcile Next with status after the task ID/refinement change.', 'warning', path, number))
        if section == 'blockers' and line.startswith('- '):
            match = re.match(r'^- \[([^\]]+)\]\s*(.*)', line)
            if match:
                blockers.setdefault(match[1], []).append(match[2])
                if match[1] not in ids:
                    findings.append(finding('unknown-blocker', 'Blocker refers to an unknown task.', 'Update its task ID or move it to a pending decision.', 'warning', path, number))
                if 'recover:' not in match[2].lower():
                    findings.append(finding('blocker-recovery', 'Blocker lacks a recovery route.', 'Append recover: <command/link>; YYYY-MM-DD.', 'warning', path, number))
        if section == 'pending decisions' and line.startswith('- ') and line != '- None':
            decisions.append(line[2:])
        links.extend(re.findall(r'\[[^\]]+\]\(([^)]+)\)', line))
        if any(re.search(pattern, line) for pattern in SECRETS):
            findings.append(finding('handoff-secret', 'Credential-shaped value redacted.', 'Remove it, revoke exposed credentials and retain only a recovery reference.', path=path, line=number))
        if re.search(LIVE, line):
            findings.append(finding('handoff-live-agent', 'Live agent identifier redacted.', 'Use a durable delegation result ID instead.', path=path, line=number))
    if len(text.splitlines()) > policy['continuation']['handoff-budget']:
        findings.append(finding('handoff-budget', 'Handoff exceeds its line budget.', 'Move durable detail to findings/context and retain a short continuation.', 'warning', path))
    for heading in ('blockers', 'pending decisions'):
        if '## ' + heading not in text.lower():
            findings.append(finding('handoff-template', 'Missing handoff section: ' + heading, 'Add ## ' + heading.title() + '.', 'warning', path))
    try:
        relative = path.relative_to(git.root).as_posix()
    except ValueError:
        return {'state': 'draft', 'blockers': blockers, 'decisions': decisions, 'context': links}, findings
    last = git.run('log', '-1', '--format=%H', '--', relative, check=False).strip()
    committed = git.read('HEAD', relative).replace('\r\n', '\n')
    state = 'new' if not last else 'dirty' if committed != text else 'current'
    if last and state == 'current':
        later = git.run('diff', '--name-only', last, 'HEAD').splitlines()
        from .scope import noncode
        goals_path = Path(policy['_goals'])
        try:
            goals_relative = goals_path.relative_to(git.root).as_posix()
        except ValueError:
            goals_relative = None
        changed_goals = False
        if goals_relative and goals_relative in later:
            from .goals import parse
            old = flatten(parse(git.read(last, goals_relative), policy)['goals'])
            current = flatten(parsed['goals'])
            changed_goals = {key: (item['status'], item['criteria'], item['checks']) for key, item in old.items()} != {key: (item['status'], item['criteria'], item['checks']) for key, item in current.items()}
        if changed_goals or any(not noncode(name, policy) for name in later):
            state = 'stale'
            findings.append(finding('handoff-stale', 'Relevant code or roadmap changed after the handoff commit.', 'Reconcile the handoff against the later changes.', 'warning', path))
    return {'state': state, 'last_commit': last or None, 'blockers': blockers, 'decisions': decisions, 'context': links}, findings
