"""Original Java-target contracts executed by Python MUSE (JDK is fixture-only).

The controller copies fixtures, initializes Git, approves a frozen allowlist and
observes. Only the agents implement, commit, review and integrate contributions.
"""
import argparse
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from muse.agent.loop import AgentRunner
from muse.config import load_settings
from muse.contracts import TERMINAL, TaskRequest
from muse.providers.compatible import HttpModelProvider
from muse.tasks.repository import TaskRepository
from muse.tasks.worker import Worker

VERIFY = 'powershell.exe -NoProfile -File ./verify.ps1'
COMPONENTS = {'src/checkout/shipping/ShippingQuote.java', 'src/checkout/pricing/DiscountPolicy.java',
              'src/stats/Mean.java', 'src/retry/Delay.java', 'src/text/Slug.java', 'src/text/Header.java'}


def overlap_seconds(first, second):
    return sum(max(0, min(b, d) - max(a, c)) for a, b in first for c, d in second)


def contributions_valid(base, components, contributions):
    return (len(contributions) == 2
            and all(c['commit'] != base and len(c['changed']) == 1
                    and all(c[k] for k in ('reviewed', 'integrated', 'ancestor', 'files_equal')) for c in contributions)
            and {name for c in contributions for name in c['changed']} == set(components))


def intervention_required(statuses):
    return any(status in {'WAITING_INPUT', 'INTERRUPTED'} for status in statuses)


def integrated_source_equal(workspace, source_commit, changed):
    """Compare committed Git content; Windows checkout line endings may differ."""
    for path in changed:
        parent = subprocess.run(['git', 'rev-parse', 'HEAD:' + path], cwd=workspace,
                                capture_output=True, text=True, check=False)
        source = subprocess.run(['git', 'rev-parse', source_commit + ':' + path], cwd=workspace,
                                capture_output=True, text=True, check=False)
        if parent.returncode or source.returncode or parent.stdout.strip() != source.stdout.strip():
            return False
        clean = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', path], cwd=workspace,
                               capture_output=True, check=False)
        if clean.returncode:
            return False
    return True


def approve_fixture_action(name, args):
    if name == 'spawn_worktree':
        return True  # production binds exact base/path/role and checks workspace
    if name == 'worktree_manage':
        return args.get('action') in {'review', 'merge', 'integrate'}
    if name == 'verify_command':
        return args.get('command') == VERIFY or args.get('command') in {'javac -d build ' + path for path in COMPONENTS}
    if name != 'run_command':
        return False
    command = args.get('command', '')
    if command in {'javac -d build ' + path for path in COMPONENTS}:
        return True  # Compilation is permitted, but does not create a verification receipt.
    if '&&' in command:
        parts = [part.strip() for part in command.split('&&')]
        return (len(parts) == 2 and parts[0].startswith('git add ') and parts[1].startswith('git commit ')
                and all(approve_fixture_action(name, {'command': part}) for part in parts))
    if any(char in command for char in '\n\r;&|`$><:') or '..' in command:
        return False
    return bool(re.fullmatch(r'''git (?:status|rev-parse|log|diff|show|add|commit) [a-zA-Z0-9_./\\ :"'\-=]+|git status''', command))


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '.git' not in p.parts and 'build' not in p.parts}


def intervals(events):
    result, start = [], None
    for event in events:
        if event['type'] != 'status':
            continue
        payload = event['payload']
        status = payload['status']
        if status == 'RUNNING':
            start = event['created_at']
        elif start is not None:
            result.append((start, event['created_at']))
            start = None
    return result


async def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    for case in ('checkout', 'numeric', 'text'):
        directory = args.output / case
        workspace = directory / 'workspace'
        shutil.copytree(args.fixtures / case, workspace)
        before = hashes(workspace)
        def git(*parts, workspace=workspace):
            return subprocess.run(['git', *parts], cwd=workspace, capture_output=True, text=True, check=True).stdout.strip()
        git('init')
        git('config', 'user.name', 'MUSE fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('add', '.')
        git('commit', '-m', 'Frozen original benchmark fixture')
        base = git('rev-parse', 'HEAD')
        baseline = await asyncio.to_thread(subprocess.run, ['powershell.exe', '-NoProfile', '-File', './verify.ps1'], cwd=workspace, capture_output=True, text=True, timeout=60, check=False)
        (directory / 'baseline-verifier.txt').write_text(baseline.stdout + baseline.stderr, encoding='utf-8')
        if baseline.returncode == 0:
            raise ValueError('Verifier did not reject unimplemented fixture')
        settings = load_settings(args.config, data_dir=directory / 'private-state')
        repo = TaskRepository(settings.data_dir / 'state.sqlite3')
        ws = repo.register_workspace(str(workspace))
        prompt = ('Read README.md and contract.json. Implement the two independent components by spawning exactly two children '
                  'in separate worktrees at commit ' + base + '. Spawn both before waiting. Each child must read the contract, '
                  'Include the tool name verify_command explicitly in each child prompt, not only the shell command. '
                  'implement only its assigned component, then run verify_command with exactly javac -d build <assigned component path> '
                  '(for example javac -d build src/stats/Mean.java). The full verifier cannot pass inside a child before the other component is integrated. '
                  'Each child must commit only its source with git add and git commit (separate calls or one git add ... && git commit ... pair). '
                  'Any run_command counts as a potential mutation in this runtime, including git status/log. '
                  'Run the component verify_command again AFTER all git calls, immediately before the child final answer. '
                  'Collect both child results, review exact commits using worktree_manage, and integrate both into the main checkout '
                  '(worktree_manage action integrate supports divergent commits). Preserve README, contract, tests and verify.ps1. '
                  'After the final integration and all other commands you must run verify_command LAST with exactly: ' + VERIFY + '. '
                  'No shell chaining except a single git add ... && git commit ... pair; no push, no checkout deletion. Plain git status/rev-parse/log/diff/show/add/commit commands '
                  'and the exact verifier/compiler commands are approved; other commands are denied. This is a coding task, not a speed claim.')
        task = repo.create(TaskRequest(prompt=prompt, scenario='coding', workspace_id=ws['id'], client_request_id=case))
        stopped = asyncio.Event()
        workers = [Worker(settings, repo, AgentRunner(HttpModelProvider(settings.provider))) for _ in range(3)]
        async def loop(worker, stopped=stopped):
            while not stopped.is_set():
                if not await worker.run_once():
                    await asyncio.sleep(.1)
        runners = [asyncio.create_task(loop(w)) for w in workers]
        start = time.monotonic()
        try:
            while time.monotonic() - start < 1200:
                members = [repo.get(task.id), *repo.children(task.id)]
                for member in members:
                    for approval in repo.approvals(member.id):
                        if approval['status'] == 'PENDING':
                            repo.decide_approval(approval['id'], approve_fixture_action(approval['name'], approval['arguments']), approval['action_digest'])
                if repo.get(task.id).status in TERMINAL or intervention_required([m.status for m in members]):
                    break
                await asyncio.sleep(.1)
        finally:
            stopped.set()
            for runner in runners:
                runner.cancel()
            await asyncio.gather(*runners, return_exceptions=True)
        current, children = repo.get(task.id), repo.children(task.id)
        after = hashes(workspace)
        components = json.loads((workspace / 'contract.json').read_text())['components']
        overlap = overlap_seconds(intervals(repo.events(children[0].id)), intervals(repo.events(children[1].id))) if len(children) == 2 else 0
        verifier = await asyncio.to_thread(subprocess.run, ['powershell.exe', '-NoProfile', '-File', './verify.ps1'], cwd=workspace, capture_output=True, text=True, timeout=60, check=False)
        calls = repo.calls(task.id)
        contributions = []
        for child in children:
            child_path = Path(repo.workspace(child.workspace_id)['path'])
            source = git('-C', str(child_path), 'rev-parse', 'HEAD')
            changed = git('-C', str(child_path), 'diff', '--name-only', base, source).splitlines()
            reviewed = False
            for call in calls:
                if call['name'] == 'worktree_manage' and call['arguments'].get('child_id') == child.id and call['arguments'].get('action') == 'review' and call['result'] and call['result']['status'] == 'success':
                    reviewed |= json.loads(call['result']['content']).get('source_commit') == source
            integrated = any(c['name'] == 'worktree_manage' and c['arguments'].get('child_id') == child.id
                             and c['arguments'].get('action') in {'merge', 'integrate'} and c['arguments'].get('source_commit') == source
                             and c['result'] and c['result']['status'] == 'success' for c in calls)
            ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'HEAD'], cwd=workspace, capture_output=True, check=False).returncode == 0  # noqa: ASYNC221 -- short local observer, after workers stop.
            contributions.append({'child_id': child.id, 'commit': source, 'changed': changed,
                                  'reviewed': reviewed, 'integrated': integrated, 'ancestor': ancestor,
                                  'files_equal': integrated_source_equal(workspace, source, changed)})
        checks = {'parent_completed': current.status == 'SUCCEEDED', 'two_children': len(children) == 2,
                  'children_completed': all(c.status == 'SUCCEEDED' for c in children),
                  'independent_workspaces': len({c.workspace_id for c in children}) == 2,
                  'overlap': overlap > 0, 'unified_verifier': verifier.returncode == 0,
                  'agent_ran_verifier': any(c['name'] == 'verify_command' and c['result'] and c['result']['status'] == 'success' for c in calls),
                  'contract_preserved': all(after.get(name) == digest for name, digest in before.items() if name not in components),
                  'committed_child_contributions': contributions_valid(base, components, contributions)}
        record = {'case': case, 'checks': checks, 'passed': all(checks.values()), 'fixture_hashes': before,
                  'overlap_seconds': overlap, 'parent_status': current.status, 'error': current.error,
                  'usage': current.checkpoint.get('usage'), 'seconds': time.monotonic() - start, 'contributions': contributions,
                  'children': [{'id': c.id, 'status': c.status, 'usage': c.checkpoint.get('usage')} for c in children]}
        for member in [current, *children]:
            (directory / (member.id + '-events.json')).write_text(json.dumps(repo.events(member.id), ensure_ascii=False, indent=2), encoding='utf-8')
            (directory / (member.id + '-calls.json')).write_text(json.dumps(repo.calls(member.id), ensure_ascii=False, indent=2), encoding='utf-8')
        (directory / 'verifier.txt').write_text(verifier.stdout + verifier.stderr, encoding='utf-8')
        (directory / 'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        records.append(record)
        (args.output / 'summary.json').write_text(json.dumps({'planned': 3, 'records': records, 'speedup_claimed': False}, indent=2), encoding='utf-8')
        print(json.dumps({'case': case, 'passed': record['passed'], 'checks': checks}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('fixtures', 'config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
