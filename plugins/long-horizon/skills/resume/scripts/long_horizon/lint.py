import difflib
import hashlib
from pathlib import Path
import re
from .goals import LOOSE, flatten, recovered
from .model import finding, Invalid
from .state import atomic


def pointers(policy, git):
    if not policy['_installed'] or policy['state']['state'] != 'active':
        return []
    findings = []
    def visit(path, stack, depth):
        if depth > 12:
            findings.append(finding('pointer-depth', 'Instruction import depth exceeds 12.', 'Flatten recursive instruction imports.', path=path))
            return False
        path = path.resolve()
        if path in stack:
            findings.append(finding('pointer-cycle', 'Instruction imports contain a cycle.', 'Remove the cyclic import.', path=path))
            return False
        if not path.is_file():
            findings.append(finding('pointer-missing', 'Instruction file/import is missing.', 'Create the file or repair its relative import.', path=path))
            return False
        text = path.read_text(encoding='utf-8')
        reached = 'long-horizon:resume' in text and '.agents/long-horizon.md' in text
        for match in re.finditer(r'(?m)(?:^|\s)@([^\s]+\.md)\b', text):
            imported = (path.parent / match[1]).resolve()
            try:
                imported.relative_to(git.root)
            except ValueError:
                findings.append(finding('pointer-escape', 'Instruction import leaves the checkout.', 'Use a relative checkout import.', path=path))
                continue
            reached = visit(imported, stack + [path], depth + 1) or reached
        return reached
    for name in ('AGENTS.md', 'CLAUDE.md'):
        if not visit(git.root / name, [], 0):
            findings.append(finding('activation-unreachable', name + ' cannot reach the long-horizon pointer.',
                'Add the plugin-qualified pointer to AGENTS.md and @AGENTS.md to CLAUDE.md.', path=git.root / name))
    return findings


def repair(policy, parsed, apply=False):
    path = Path(policy['_goals'])
    if not path.exists():
        return ''
    before = path.read_bytes()
    text = before.decode()
    lines = text.splitlines(keepends=True)
    for item in flatten(parsed['goals']).values():
        if item['kind'] == 'task' and any(x.code == 'missing-task-id' and x.line == item['line'] for x in parsed['findings']):
            offset = item['line'] - 1
            lines[offset] = re.sub(r'(^\s*- \[[ xX]\]\s+)', lambda m: m[1] + '[' + item['id'] + '] ', lines[offset], count=1)
    moves = {}
    for item in flatten(parsed['goals']).values():
        offset = (item.get('criteria_line') or 0) - 1
        if item.get('loose_criteria') and offset >= 0:
            indent = re.match(r'\s*', lines[offset])[0]
            lines[offset] = indent + LOOSE.sub('Done when: ', lines[offset][len(indent):], count=1)
        found = recovered(item) if item['kind'] == 'milestone' and not item['criteria'] else None
        if found and found['source'] == 'task':
            # A trailing criterion moves above the first task, keeping its text unchanged.
            moves[item['children'][0]['line'] - 1] = found['line'] - 1
    for target, source in sorted(moves.items(), reverse=True):
        line = lines.pop(source)
        lines.insert(target, line if line.endswith(('\n', '\r')) else line + ('\r\n' if lines[target - 1].endswith('\r\n') else '\n'))
    after = ''.join(lines).encode()
    diff = ''.join(difflib.unified_diff(text.splitlines(True), after.decode().splitlines(True), fromfile=str(path), tofile=str(path)))
    if apply and after != before:
        if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(before).digest():
            raise Invalid('Goals changed during repair; review the new diff before applying.')
        atomic(path, after, raw=True)
    return diff
