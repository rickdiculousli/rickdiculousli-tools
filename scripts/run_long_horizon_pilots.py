#!/usr/bin/env python3
"""Run bounded model pilots in disposable host profiles, with explicit credentials.

Profiles (including the temporary credential copy) are always removed. Curatable
reports and transcripts live under XDG cache and expire by manual pilot cleanup
at 30 days; this script never reads credentials except the explicitly named file.
No normal host config, user plugin install, network Git remote or game-decomp changes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/long-horizon'
SCRIPT = PLUGIN / 'skills/resume/scripts/lh.py'
FIXTURES = ROOT / 'tests/fixtures/long_horizon/pilots'


def run(argv, cwd, env, timeout=30):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def git(root, *args):
    result = run(['git', '-C', str(root), *args], root, os.environ)
    if result.returncode:
        raise RuntimeError('Fixture git failed (' + ' '.join(args[:2]) + '): ' + (result.stderr or result.stdout).strip())
    return result.stdout.strip()


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def build(root, scenario):
    root.mkdir()
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.name', 'Long Horizon Pilot')
    git(root, 'config', 'user.email', 'pilot@example.invalid')
    git(root, 'config', 'commit.gpgsign', 'false')
    for path in (FIXTURES / 'project').rglob('*'):
        if path.is_file():
            write(root, path.relative_to(FIXTURES / 'project'), path.read_text())
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Copyright-free pilot starting tree')
    if scenario == 'new':
        linked = root.parent / 'linked worktree'
        git(root, 'worktree', 'add', '-b', 'pilot', str(linked))
        return linked
    if scenario != 'new':
        for path in (FIXTURES / 'configured').rglob('*'):
            if path.is_file():
                write(root, path.relative_to(FIXTURES / 'configured'), path.read_text())
        git(root, 'add', '.')
        git(root, 'commit', '-m', 'Existing long-horizon setup')
    if scenario == 'adopt':
        (root / '.agents/long-horizon.md').unlink()
        git(root, 'add', '-u')
        git(root, 'commit', '-m', 'Existing roadmap without activation')
        write(root, 'unrelated.txt', 'USER DIRTY BYTES MUST SURVIVE\n')
    if scenario == 'branch':
        git(root, 'checkout', '-b', 'existing-policy')
        overlay = (root / '.agents/long-horizon.md').read_text().replace('handoff-budget: 80', 'handoff-budget: 67')
        write(root, '.agents/long-horizon.md', overlay)
        git(root, 'add', '.')
        git(root, 'commit', '-m', 'Unique branch-specific policy')
        git(root, 'checkout', 'main')
        (root / '.agents/long-horizon.md').unlink()
        git(root, 'add', '-u')
        git(root, 'commit', '-m', 'No current overlay; local branch holds it')
    if scenario == 'blocked':
        goals = (root / 'docs/goals.md').read_text().replace('(any)', '(native)', 1)
        write(root, 'docs/goals.md', goals)
        write(root, 'docs/handoff.md', '# Handoff\n## Blockers\n- [1.2] Needs user dataset; recover: docs/recovery.md; 2026-10-11\n## Pending decisions\n- Choose native bytes.\n')
        write(root, 'docs/recovery.md', 'Use fixture inputs or ask user for native bytes.\n')
    if scenario == 'checkpoint':
        write(root, 'tiny.py', 'def tiny():\n    return 2\n')
    return root


def inspect(root, scenario, result, env):
    cli = run([sys.executable, str(SCRIPT), 'status', '--root', str(root), '--json'], root, env)
    try:
        status = json.loads(cli.stdout)
    except ValueError:
        status = {'ok': False}
    checks = {'model_exited_0': result.returncode == 0, 'cli_status_ok': status.get('ok') is True,
              'no_checkout_runtime_state': not (root / '.long-horizon').exists() and not (root / '.pilot-host').exists() and not any(root.rglob('state.lock'))}
    if scenario in ('new', 'adopt', 'branch'):
        cache = Path(env['XDG_CACHE_HOME'])
        checks['setup_cache_layout'] = not cache.exists() or all(x.name == 'rickdiculousli-tools' for x in cache.iterdir())
        checks['overlay_written'] = (root / '.agents/long-horizon.md').is_file()
        checks['handoff_written'] = (root / 'docs/handoff.md').is_file()
        checks['selected_task'] = bool(status.get('selection', {}).get('task'))
        agents = (root / 'AGENTS.md').read_text() if (root / 'AGENTS.md').exists() else ''
        checks['pointer_reachable'] = 'long-horizon:resume' in agents
    if scenario == 'adopt':
        checks['unrelated_dirty_preserved'] = (root / 'unrelated.txt').read_text() == 'USER DIRTY BYTES MUST SURVIVE\n'
        checks['adopted_task_text_preserved'] = 'Implement the bounded tiny behavior.' in (root / 'docs/goals.md').read_text()
    if scenario == 'blocked':
        checks['no_unearned_completion'] = '- [x]' not in (root / 'docs/goals.md').read_text()
        checks['blocked_mode'] = status.get('selection', {}).get('mode') == 'all-blocked'
    if scenario == 'checkpoint':
        checks['durable_evidence_written'] = bool(list((root / 'docs/evidence').glob('*.json')))
        checks['milestone_remains_open'] = '## 1. Build — done' not in (root / 'docs/goals.md').read_text()
    if scenario == 'external':
        checks['external_not_fresh_without_probes'] = all(x['status'] != 'fresh' for x in status.get('acceptance', []) if x['check'] == 'validator:unit')
        checks['no_false_milestone'] = '## 1. Build — done' not in (root / 'docs/goals.md').read_text()
        checks['requested_open_tasks_preserved'] = '- [x]' not in (root / 'docs/goals.md').read_text()
    if scenario == 'composed':
        records = [json.loads(p.read_text()) for p in (root / 'docs/evidence').glob('*.json')]
        checks['checked_result_durable'] = any(x.get('claim') == 'checked' and x.get('result') == 'd1#1' for x in records)
        checks['no_second_ledger'] = not (root / '.long-horizon').exists()
        checker = ROOT / 'plugins/delegation/skills/delegation/scripts/check.py'
        paths = run([sys.executable, str(checker), '--root', str(root), 'paths', '--json'], root, env)
        info = json.loads(paths.stdout) if paths.returncode == 0 else {}
        checks['fixture_ledger_deleted'] = bool(info) and not (Path(info['worktree_state_directory']) / 'ledger.jsonl').exists()
        query = run([sys.executable, str(checker), '--root', str(root), 'query', '--delegation', 'd1', '--tree', 'current', '--json'], root, env)
        checks['current_query_empty_without_identity_error'] = query.returncode == 0 and not json.loads(query.stdout).get('results')
        prepared = run([sys.executable, str(SCRIPT), 'evidence', 'prepare', 'validator:unit', '--root', str(root), '--json'], root, env)
        if prepared.returncode == 0:
            snapshot = json.loads(prepared.stdout)['snapshot']['id']
            rejected = run([sys.executable, str(SCRIPT), 'evidence', 'record', 'validator:unit', '--root', str(root), '--snapshot', snapshot,
                            '--outcome', 'PASS', '--delegation', 'd1', '--result', 'd1#1', '--log', 'regenerate:registered unit validator', '--json'], root, env)
            checks['new_checked_claim_refused_for_missing_result'] = rejected.returncode == 2 and 'Registered result is missing/ambiguous' in rejected.stdout
        else:
            checks['new_checked_claim_refused_for_missing_result'] = False
    if scenario == 'closure':
        verified = run([sys.executable, str(SCRIPT), 'closure', 'verify', '--root', str(root), '--json'], root, env)
        checks['closure_complete'] = verified.returncode == 0 and json.loads(verified.stdout).get('state') == 'complete'
        checks['bare_remote_contains_batch'] = bool(git(root, 'rev-parse', '--verify', 'refs/remotes/origin/main'))
    if scenario == 'lifecycle':
        checks['completion_archive_retained'] = bool(list((root / 'docs/goals-archive').glob('*.md')))
        checks['reactivated_goal_selected'] = bool(status.get('selection', {}).get('task'))
        checks['single_activation_pointer'] = (root / 'AGENTS.md').read_text().count('long-horizon:resume') == 1
    if scenario == 'boundary':
        text = (root / 'docs/goals.md').read_text()
        checks['first_milestone_done'] = '## 1. Build — done' in text
        checks['next_milestone_current_and_open'] = '## 2. Integration — current' in text and '## 2. Integration — done' not in text
        checks['refined_task_selected'] = bool(status.get('selection', {}).get('task'))
        checks['parked_preserved'] = 'Explore widescreen later' in text
    if scenario == 'selection':
        checks['prepared_report_exists'] = (root / 'readiness.json').is_file()
        checks['all_blocked_after_fixture_blocker'] = status.get('selection', {}).get('mode') == 'all-blocked'
        checks['later_milestone_stays_open'] = '## 2. Integration — done' not in (root / 'docs/goals.md').read_text()
    if scenario == 'outcomes':
        records = [json.loads(p.read_text()) for p in (root / 'docs/evidence').glob('*.json')]
        checks['skip_and_unstable_preserved'] = {'SKIP', 'UNSTABLE'} <= {x.get('outcome') for x in records}
        checks['no_false_completion'] = '- [x]' not in (root / 'docs/goals.md').read_text()
    if scenario == 'reconstruct':
        checks['durable_unit_recovered'] = any(x['check'] == 'validator:unit' and x['status'] == 'fresh' for x in status.get('acceptance', []))
        checks['task_only_completion'] = '- [x] [1.1]' in (root / 'docs/goals.md').read_text() and '## 1. Build — done' not in (root / 'docs/goals.md').read_text()
    if scenario == 'stop':
        goals = (root / 'docs/goals.md').read_text()
        checks['shelve_record_retained'] = bool(list((root / 'docs/goals-archive').glob('*.md')))
        checks['unshelved_task_selected'] = status.get('selection', {}).get('task', {}).get('id') == '1.1'
        checks['dropped_goal_retained'] = '— dropped' in goals and 'Reason:' in goals
        checks['no_false_completion'] = '- [x]' not in goals
    if scenario == 'quota':
        calls = root.parent / 'quota-calls.txt'
        checks['one_quota_call'] = calls.is_file() and len(calls.read_text().splitlines()) == 1
        checks['no_automatic_task_completion'] = '- [x]' not in (root / 'docs/goals.md').read_text()
    return checks, status



def lh(root, env, *args):
    result = run([sys.executable, str(SCRIPT), *args, '--root', str(root), '--json'], root, env)
    if result.returncode:
        raise RuntimeError('Fixture CLI seed failed: ' + result.stdout)
    return json.loads(result.stdout)


def seed(root, scenario, env):
    if scenario == 'external':
        write(root, '.gitignore', '__pycache__/\nexternal.data\n')
        write(root, 'external.data', 'a' * 64 + '\n')
        overlay = (root / '.agents/long-horizon.md').read_text().replace('"domain": "unit-v1"', '"domain": "unit-v1", "inputs": ["corpus"]')
        probe = {'command': [sys.executable, '-c', 'from pathlib import Path; print(Path("external.data").read_text().strip())'], 'timeout': 2, 'recover': 'restore explicitly supplied external.data token'}
        write(root, '.agents/long-horizon.md', overlay + 'inputs: ' + json.dumps({'corpus': probe}) + '\n')
    if scenario == 'composed':
        checker = ROOT / 'plugins/delegation/skills/delegation/scripts/check.py'
        overlay = (root / '.agents/long-horizon.md').read_text() + 'delegation-script: ' + json.dumps(str(checker)) + '\n'
        write(root, '.agents/long-horizon.md', overlay)
        write(root, '.agents/delegation.md', '## Validators\nunit: python3 -m unittest -v\n## Parallel limit\n1\n')
        write(root, '.gitignore', '__pycache__/\n.delegation/\n')
        write(root, 'tiny.py', 'def tiny():\n    return 2\n')
        git(root, 'add', '.')
        git(root, 'commit', '-m', 'Registered validator seed')
        brief = root.parent / 'brief.md'
        brief.write_text('Fixture registered validator only; no workers.\n')
        for argv in [('open', '--delegation', 'd1', '--tier', 'execute', '--brief', str(brief)), ('run', 'unit', '--delegation', 'd1'), ('close', '--delegation', 'd1', '--outcome', 'done')]:
            result = run([sys.executable, str(checker), '--root', str(root), *argv], root, env)
            if result.returncode:
                raise RuntimeError('Actual checker seed failed.')
    if scenario in ('closure', 'lifecycle', 'reconstruct', 'boundary'):
        overlay = (root / '.agents/long-horizon.md').read_text()
        if scenario == 'closure':
            overlay += '\n## Integration\nsteps: ["commit", "merge", "push", "sync"]\ntarget: "main"\nremote: "origin"\nsync: "Fixture sync command only"\nauthorization: "Pilot user approves exact local bare remote integration and observed fixture sync."\n'
        write(root, '.agents/long-horizon.md', overlay)
        if scenario in ('lifecycle', 'boundary'):
            write(root, 'docs/goals.md', '# Goal: Tiny behavior — current\nID: tiny\nDone when: validator:unit\n## 1. Build — current\nDone when: validator:unit\n- [ ] [1.1] Implement the bounded tiny behavior. (any)\n## Parked\n')
        if scenario == 'boundary':
            text = (root / 'docs/goals.md').read_text().replace('Done when: validator:unit\n## 1.', 'Done when: validator:unit and observation:review\n## 1.', 1)
            text = text.replace('## Parked', '## 2. Integration\nDone when: observation:review proves the full calling context.\n- [ ] [2.1] Refine integration work at the milestone boundary. (any)\n## Parked\n- Explore widescreen later (2026-10-11)')
            write(root, 'docs/goals.md', text)
        if git(root, 'status', '--porcelain'):
            git(root, 'add', '.')
            git(root, 'commit', '-m', 'Lifecycle/integration seed policy')
        if scenario == 'closure':
            remote = root.parent / 'remote.git'
            git(root, 'init', '--bare', str(remote))
            git(root, 'remote', 'add', 'origin', str(remote))
            hook = remote / 'hooks/pre-receive'
            hook.write_text('#!/bin/sh\nexit 1\n')
            hook.chmod(0o755)
            git(root, 'checkout', '-b', 'batch')
            git(root, 'worktree', 'add', str(root.parent / 'target'), 'main')
        base = git(root, 'rev-parse', 'HEAD')
        write(root, 'tiny.py', 'def tiny():\n    return 2\n')
        before = lh(root, env, 'evidence', 'prepare', 'validator:unit')
        observed = run([sys.executable, '-m', 'unittest', '-v'], root, env)
        if observed.returncode:
            raise RuntimeError('Observed unit seed failed.')
        proof = lh(root, env, 'evidence', 'record', 'validator:unit', '--snapshot', before['snapshot']['id'], '--outcome', 'PASS', '--command', 'python3 -m unittest -v', '--exit', '0', '--log', 'regenerate:python3 -m unittest -v against this fixture commit')
        for path, content in proof['proposed_files'].items():
            write(root, path, content)
        git(root, 'add', '.')
        git(root, 'commit', '-m', 'Observed seed unit check\n\n' + proof['trailer'])
        commit = git(root, 'rev-parse', 'HEAD')
        paths = []
        for path in git(root, 'diff', '--name-only', base, commit).splitlines():
            paths.append({'path': path, 'digest': hashlib.sha256((root / path).read_bytes()).hexdigest()})
        manifest = {'version': 1, 'base': base, 'paths': paths, 'evidence_ids': [proof['record']['id']]}
        (root.parent / 'manifest.json').write_text(json.dumps(manifest))
        batch = hashlib.sha256(json.dumps({'evidence_ids': manifest['evidence_ids'], 'paths': sorted(paths, key=lambda x: x['path'])}, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
        (root.parent / 'seed.json').write_text(json.dumps({'commit': commit, 'evidence': proof['record']['id'], 'batch': batch}))
        if scenario == 'closure':
            lh(root, env, 'closure', 'record', '--batch', batch, '--step', 'commit', '--outcome', 'success', '--commit', commit, '--manifest', str(root.parent / 'manifest.json'))
    if scenario == 'selection':
        overlay = (root / '.agents/long-horizon.md').read_text().replace('"native": ["native"]', '"native": ["fixtures", "native"], "fixtures": ["fixtures"]')
        overlay += '\n## Startup\ncommand: "python3 tools/prepare.py"\neffects: ["read fixture paths", "write readiness.json"]\nreadiness: "readiness.json"\n'
        write(root, '.agents/long-horizon.md', overlay)
        text = (root / 'docs/goals.md').read_text().replace('(any)', '(native)', 1).replace('(any)', '(fixtures)', 1)
        text = text.replace('## Parked', '## 2. Integration\nDone when: observation:review establishes the full call.\n- [ ] [2.1] Later integration behavior. (any)\n## Parked')
        write(root, 'docs/goals.md', text)
        write(root, 'tools/prepare.py', 'import json\nfrom pathlib import Path\nPath("readiness.json").write_text(json.dumps({"version":1,"checkout":str(Path.cwd()),"levels":{"fixtures":{"ready":True,"strength":"sha256"},"native":{"ready":False,"strength":"exists"}},"missing":[{"input":"native bytes","needed_for":["native"],"recover":"docs/recovery.md"}]}))\n')
        write(root, '.gitignore', '__pycache__/\nreadiness.json\n')
        write(root, 'docs/recovery.md', 'Native capture unavailable; use fixtures for bounded work.\n')
        git(root, 'add', '.')
        git(root, 'commit', '-m', 'Preparation capability policy')
        write(root, 'tiny.py', '# Later code change after handoff\ndef tiny():\n    return 1\n')
        git(root, 'add', 'tiny.py')
        git(root, 'commit', '-m', 'Relevant code changed after handoff')
    if scenario == 'quota':
        stub = root.parent / 'quota stub.py'
        calls = root.parent / 'quota-calls.txt'
        stub.write_text('from pathlib import Path\nimport json\np=Path(' + repr(str(calls)) + ')\nwith p.open("a") as f: f.write("call\\n")\nprint(json.dumps({"provider":"fixture","remaining_percent":10}))\n')
        overlay = (root / '.agents/long-horizon.md').read_text() + '\n## Batch\nquota: true\nquota-script: ' + json.dumps(str(stub)) + '\n'
        write(root, '.agents/long-horizon.md', overlay)
        write(root, 'docs/goals.md', (root / 'docs/goals.md').read_text().replace('[1.1] ', '', 1))

def main():
    global PLUGIN, SCRIPT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path, default=SCRIPT, help='Declared installed skill or checkout lh.py path')
    parser.add_argument('--host', choices=['codex', 'claude'], required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--scenario', choices=['new', 'adopt', 'branch', 'blocked', 'checkpoint', 'external', 'composed', 'closure', 'lifecycle', 'quota', 'stop', 'selection', 'outcomes', 'reconstruct', 'boundary'], required=True)
    parser.add_argument('--timeout', type=int, default=420)
    args = parser.parse_args()
    SCRIPT = args.script.resolve()
    if len(SCRIPT.parents) < 4:
        parser.error("Script must be the declared resume/scripts/lh.py of a complete plugin.")
    PLUGIN = SCRIPT.parents[3]
    if not SCRIPT.is_file() or not (PLUGIN / 'plugin.json').is_file():
        parser.error('Script must be the declared resume/scripts/lh.py of a complete plugin.')
    if not args.credentials.is_file():
        parser.error('Explicit pilot credential file is unavailable.')
    raw = os.environ.get('XDG_CACHE_HOME', '')
    cache = Path(raw) if raw and Path(raw).is_absolute() else Path.home() / '.cache'
    output = cache / 'rickdiculousli-tools/long-horizon/pilots' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + args.host + '-' + args.scenario)
    output.mkdir(parents=True, mode=0o700)
    report = {'version': 1, 'host': args.host, 'scenario': args.scenario,
              'started': datetime.now(timezone.utc).isoformat(), 'plugin_version': json.loads((PLUGIN / 'plugin.json').read_text())['version'],
              'source_commit': git(ROOT, 'rev-parse', 'HEAD'), 'python': sys.version.split()[0],
              'plugin_content_sha256': hashlib.sha256(b''.join(str(p.relative_to(PLUGIN)).encode() + b'\0' + p.read_bytes() for p in sorted(PLUGIN.rglob('*')) if p.is_file() and '__pycache__' not in p.parts)).hexdigest()}
    try:
        with tempfile.TemporaryDirectory(prefix='profile-', dir=output) as temporary:
            profile = Path(temporary)
            credential = profile / ('auth.json' if args.host == 'codex' else '.credentials.json')
            shutil.copyfile(args.credentials, credential)
            credential.chmod(0o600)
            env = dict(os.environ, XDG_STATE_HOME=str(output / 'state'), XDG_CACHE_HOME=str(output / 'cache'))
            env.pop('CLAUDECODE', None)
            env.pop('CODEX_THREAD_ID', None)
            env.pop('CODEX_HOME', None)
            env.pop('CLAUDE_CONFIG_DIR', None)
            env['CODEX_HOME' if args.host == 'codex' else 'CLAUDE_CONFIG_DIR'] = str(profile)
            if args.host == 'codex':
                env['CODEX_SQLITE_HOME'] = str(profile)
            else:
                env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
            root = build(output / 'project', args.scenario)
            seed(root, args.scenario, env)
            if args.scenario == 'reconstruct':
                old = root
                root = old.parent / 'reconstructed checkout'
                git(old, 'clone', str(old), str(root))
                git(root, 'config', 'user.name', 'Long Horizon Pilot')
                git(root, 'config', 'user.email', 'pilot@example.invalid')
                shutil.rmtree(Path(env['XDG_STATE_HOME']))
            report['starting_commit'] = git(root, 'rev-parse', 'HEAD')
            report['starting_tree'] = git(root, 'rev-parse', 'HEAD^{tree}')
            prompt = (FIXTURES / (args.scenario + '.txt')).read_text()
            prompt += '\nThe explicitly declared LONG_HORIZON_SCRIPT is ' + str(SCRIPT)
            prompt += '\nRead the actual long-horizon skill files from ' + str(PLUGIN / 'skills')
            prompt += '\nThis is a disposable pilot. No workers/subagents, network Git operations, other projects or normal user settings. Operate only in this fixture and its declared XDG dirs. Preserve the supplied XDG_STATE_HOME/XDG_CACHE_HOME consistently across all calls; never substitute .pilot-host or any checkout-local/Git/plugin runtime path. Never read credentials/profile files. Read skills and use their actual CLI; report exact remaining acceptance/closure.\n'
            env['LONG_HORIZON_SCRIPT'] = str(SCRIPT)
            (output / 'prompt.txt').write_text(prompt)
            report['prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
            version = run([args.host, '--version'], root, env)
            report['host_version'] = version.stdout.strip()
            if args.host == 'codex':
                registered = run(['codex', 'plugin', 'marketplace', 'add', str(ROOT), '--json'], root, env)
                installed = run(['codex', 'plugin', 'add', 'long-horizon@rickdiculousli-tools', '--json'], root, env)
                if registered.returncode or installed.returncode:
                    raise RuntimeError('Disposable native plugin install failed.')
                argv = ['codex', 'exec', '--json', '-s', 'danger-full-access', '-c', 'approval_policy="never"', '-C', str(root), prompt]
            else:
                argv = ['claude', '-p', '--verbose', '--output-format', 'stream-json', '--permission-mode', 'bypassPermissions', '--setting-sources', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--plugin-dir', str(PLUGIN), prompt]
            started = time.monotonic()
            try:
                result = run(argv, root, env, timeout=args.timeout)
            except subprocess.TimeoutExpired as error:
                report['error'] = 'Model pilot timed out'
                stdout = error.stdout or b''
                (output / 'events.jsonl').write_bytes(stdout.encode() if isinstance(stdout, str) else stdout)
                raise RuntimeError('Model pilot timed out') from None
            (output / 'events.jsonl').write_text(result.stdout)
            (output / 'stderr.log').write_text(result.stderr)
            models = set()
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('model'):
                    models.add(event['model'])
            for session in (profile / 'sessions').rglob('*.jsonl'):
                for line in session.read_text().splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get('type') == 'turn_context' and event.get('payload', {}).get('model'):
                        models.add(event['payload']['model'])
            report['observed_models'] = sorted(models)
            report['elapsed_seconds'] = round(time.monotonic() - started, 2)
            report['exit_code'] = result.returncode
            checks, status = inspect(root, args.scenario, result, env)
            report['assertions'] = checks
            report['status'] = status
            report['passed'] = all(checks.values())
            report['tool_calls_require_manual_review'] = True
            # Profiles and their credentials vanish at context exit. Keep fixture/evidence.
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
        report['passed'] = False
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'report': str(output / 'report.json'), 'assertions': report.get('assertions'), 'error': report.get('error')}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
