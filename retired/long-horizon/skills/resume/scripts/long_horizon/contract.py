"""Compare a checkout's long-horizon files with the installed plugin's current contract.

Only the current layout is known here; anything else is reported, never rewritten.
"""
import json
from pathlib import Path
from .model import finding


def installed_version(start=None):
    """The nearest plugin manifest above this package names the installed version."""
    here = Path(start or __file__).resolve()
    for folder in here.parents:
        for name in ('plugin.json', '.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
            try:
                data = json.loads((folder / name).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get('name') == 'long-horizon' and isinstance(data.get('version'), str):
                return data['version']
    return None


def minor(version):
    return tuple(int(part) for part in version.split('.')[:2])


def version(policy, installed):
    """Findings for a missing, older or newer overlay tag; patch differences are ignored."""
    tagged = policy.get('_version')
    if not policy['_installed'] or installed is None:
        return []
    if tagged is None or minor(tagged) < minor(installed):
        return [finding('version-mismatch', 'long-horizon plugin is %s; the overlay is %s.' % (installed, tagged or 'untagged'),
                        'Offer to run long-horizon:migrate.', 'warning', policy['_overlay'])]
    if minor(tagged) > minor(installed):
        return [finding('version-newer', 'The overlay is %s but the installed long-horizon plugin is %s.' % (tagged, installed),
                        'Update the installed plugin; do not migrate.', 'warning', policy['_overlay'])]
    return []


def layout(policy, git):
    findings = []
    stray = git.root / '.long-horizon'
    if stray.exists() or stray.is_symlink():
        findings.append(finding('layout-unexpected', 'Checkout-local long-horizon state is not part of the current layout.',
                                'Delete it after approval; runtime state lives under the XDG state root (lh.py paths).',
                                'warning', stray))
    for line in policy.get('_outdated', []):
        findings.append(finding('layout-outdated', 'The ## Schema heading is superseded and ignored.',
                                'Replace it with ## Version.', 'warning', policy['_overlay'], line))
    if policy['_installed'] and policy['state']['state'] == 'active':
        for key, name in (('_goals', 'Goals file'), ('_handoff', 'Handoff file')):
            if not Path(policy[key]).is_file():
                findings.append(finding('layout-missing', name + ' configured by the overlay does not exist.',
                                        'Create it from the setup templates or fix the overlay path.', 'warning', policy[key]))
    return findings
