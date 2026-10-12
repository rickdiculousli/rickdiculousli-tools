import json
import time
from pathlib import Path, PureWindowsPath
from datetime import datetime, timezone
from .model import finding, Invalid
from . import state


def cache_name(name):
    value = name[len('cache:'):]
    windows = PureWindowsPath(value)
    if (not value or windows.drive or windows.root or '\\' in value
            or any(not part or part.endswith((' ', '.')) or ':' in part or '\0' in part for part in value.split('/'))
            or Path(value).is_absolute() or Path(value).suffix != '.json'):
        raise Invalid('Readiness cache: requires a relative JSON path without .., absolute paths or backslashes.')
    return value


def resolve(policy, git):
    name = policy['startup'].get('readiness')
    if not name:
        return None
    if not name.startswith('cache:'):
        return Path(policy['_base']) / name
    base = state.State(git).cache / 'readiness'
    path = base / cache_name(name)
    # Reject symlinks as well as lexical traversal, including links in ancestors.
    ancestors = [path]
    parent = path.parent
    while parent != state.xdg('cache') and parent != parent.parent:
        ancestors.append(parent)
        parent = parent.parent
    if any(item.is_symlink() for item in ancestors):
        raise Invalid('Unsafe symlink in readiness cache path.')
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        raise Invalid('Readiness path escapes cache directory.') from None
    return path


def cache_identity(git):
    current = state.State(git)
    expected = state.identity(git, time.time())
    saved = state.read(current.cache / 'identity.json')
    if saved is not None and (not isinstance(saved, dict) or
            any(saved.get(k) != expected[k] for k in ('version', 'worktree', 'common', 'git', 'files', 'volume'))):
        raise Invalid('Cache worktree identity changed or malformed; inspect state gc and recover explicitly.')
    return saved, expected


def paths(policy, git):
    current = state.State(git)
    path = resolve(policy, git)
    saved, expected = cache_identity(git)
    return {'state_directory': str(current.path), 'cache_directory': str(current.cache),
            'readiness_directory': str(current.cache / 'readiness'),
            'readiness_path': str(path) if path else None,
            'cache_identity_path': str(current.cache / 'identity.json'),
            'cache_identity': saved or expected}


def load(policy, git):
    name = policy['startup'].get('readiness')
    empty = {'levels': {}, 'recovery': 'Configure and run an authorized startup helper; provide readiness JSON.'}
    if not name:
        return empty, []
    path = resolve(policy, git)
    try:
        if name.startswith('cache:') and cache_identity(git)[0] is None:
            raise Invalid('Missing readiness cache identity; regenerate with paths discovery.')
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
    except (Invalid, OSError, ValueError, TypeError, AttributeError):
        return empty, [finding('readiness-unknown', 'Readiness is missing, malformed, stale or for another checkout.',
            'Run the authorized helper and regenerate ' + name, 'warning', path)]
