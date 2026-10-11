import json
from pathlib import Path
from datetime import datetime, timezone
from .model import finding


def load(policy, git):
    name = policy['startup'].get('readiness')
    empty = {'levels': {}, 'recovery': 'Configure and run an authorized startup helper; provide readiness JSON.'}
    if not name:
        return empty, []
    path = Path(policy['_base']) / name
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('version') != 1 or not isinstance(value.get('levels'), dict) or not isinstance(value.get('missing', []), list):
            raise ValueError()
        if value.get('checkout') and Path(value['checkout']).resolve() != git.root:
            raise ValueError()
        if value.get('generated_at'):
            date = datetime.fromisoformat(value['generated_at'].replace('Z', '+00:00'))
            if date.tzinfo is None or not -300 <= (datetime.now(timezone.utc) - date).total_seconds() <= 86400:
                raise ValueError()
        for item in value['levels'].values():
            if type(item.get('ready')) is not bool or item.get('strength') not in ('exists', 'size', 'sha256', 'probed'):
                raise ValueError()
        value['recovery'] = '; '.join(x.get('recover', '') for x in value.get('missing', []) if isinstance(x, dict) and x.get('recover')) or 'run authorized startup and regenerate readiness JSON.'
        return value, []
    except (OSError, ValueError, TypeError, AttributeError):
        return empty, [finding('readiness-unknown', 'Readiness is missing, malformed, stale or for another checkout.',
            'Run the authorized helper and regenerate ' + name, 'warning', path)]
