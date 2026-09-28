import json
import subprocess
from pathlib import Path

import pytest
from test_agent_loop import ScriptedProvider, runtime

from muse.agent.loop import AgentRunner
from muse.contracts import ModelEvent, ToolCall
from muse.tasks.worker import Worker
from muse.tools.context import ApprovalRequired, ExecutionContext
from muse.tools.registry import ToolRegistry


def git(root, *args):
    return subprocess.run(['git', '-c', 'core.longpaths=true', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def git_input(root, value, *args):
    return subprocess.run(['git', '-c', 'core.longpaths=true', '-C', str(root), *args], input=value,
                          text=True, capture_output=True, check=True).stdout.strip()


def test_worktree_tool_explains_registered_role_requirement(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    task = repo.claim_next('parent')
    registry = ToolRegistry(ExecutionContext(worker.settings, repo, task, 'parent'))
    tool = registry.entries['spawn_worktree'][0]
    assert 'omit role' in tool.description.lower()
    assert 'display name' in tool.parameters['properties']['role']['description'].lower()


@pytest.mark.parametrize('directory_name', ['ascii', '项目 with space'])
async def test_worktree_child_uses_isolated_checkout_and_survives_restart(tmp_path, directory_name):
    tmp_path = tmp_path / directory_name
    provider = ScriptedProvider([])
    repo, task, worker = runtime(tmp_path, provider)
    root = tmp_path / 'project'
    git(root, 'init')
    git(root, 'add', 'hello.txt')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
    commit = git(root, 'rev-parse', 'HEAD')
    roles = root / '.muse/agents'
    roles.mkdir(parents=True)
    (roles / 'auditor.md').write_text('---\nname: auditor\ndescription: Isolated reader\nisolation: worktree\ntools: [Read]\nmaxTurns: 3\n---\nRead in isolation.')
    (root / 'hello.txt').write_text('uncommitted parent change')
    provider.turns = iter([
        [ModelEvent(type='call', call=ToolCall(id='isolate', name='spawn_worktree', arguments={'base_commit': commit, 'prompt': 'Read hello.txt', 'role': 'auditor'}))],
        [ModelEvent(type='text', text='Waiting for isolated inspection')],
        [ModelEvent(type='call', call=ToolCall(id='read', name='read_file', arguments={'path': 'hello.txt'}))],
        [ModelEvent(type='text', text='Isolated checkout contains local content')],
        [ModelEvent(type='text', text='Reviewed isolated result')],
    ])
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    assert repo.children(task.id) == []
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    assert repo.get(task.id).status == 'PAUSED'
    child = repo.children(task.id)[0]
    assert child.checkpoint['role'] == 'auditor'
    assert child.checkpoint['allowed_tools'] == ['read_file']
    isolated = Path(repo.workspace(child.workspace_id)['path'])
    assert isolated != root
    assert git(isolated, 'rev-parse', 'HEAD') == commit
    assert (isolated / 'hello.txt').read_text() == 'local content'
    worker = Worker(worker.settings, repo, AgentRunner(provider))
    await worker.run_once()
    read = next(call for call in repo.calls(child.id) if call['name'] == 'read_file')
    assert read['result']['status'] == 'success'
    assert 'local content' in read['result']['content']
    await worker.run_once()
    assert repo.get(task.id).status == 'SUCCEEDED'
    assert (root / 'hello.txt').read_text() == 'uncommitted parent change'
    result = repo.calls(task.id)[0]['result']
    assert json.loads(result['content'])['child_id'] == child.id
    assert isolated.is_dir()  # Completion never deletes the user's work.


def test_worktree_configuration_imports_explicit_managed_root(tmp_path):
    from muse.config import load_settings
    config = tmp_path / 'settings.yaml'
    config.write_text('worktrees:\n  managed_root: short-checkouts\n', encoding='utf-8')
    settings = load_settings(config, data_dir=tmp_path / 'state', require_provider=False)
    assert settings.worktree_managed_root == (tmp_path / 'short-checkouts').resolve()


async def test_approved_worktree_root_is_frozen_across_restart(tmp_path):
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    first_root = tmp_path / 'first-root'
    settings = worker.settings.model_copy(update={'worktree_managed_root': first_root})
    claimed = repo.claim_next('first')
    ctx = ExecutionContext(settings, repo, claimed, 'first')
    call = ToolCall(id='spawn', name='spawn_worktree', arguments={'base_commit': 'a' * 40, 'prompt': 'Read'})
    registry = ToolRegistry(ctx)
    first = registry.worktrees.bind(call)
    assert Path(first.arguments['worktree_path']).parent == first_root
    with pytest.raises(ApprovalRequired):
        await registry.execute(call)
    approval = repo.approvals(task.id)[0]
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    claimed = repo.claim_next('second')
    changed = settings.model_copy(update={'worktree_managed_root': tmp_path / 'changed-root'})
    second = ToolRegistry(ExecutionContext(changed, repo, claimed, 'second')).worktrees.bind(call)
    assert second.arguments['worktree_path'] == first.arguments['worktree_path']
    assert repo.calls(task.id)[0]['arguments']['worktree_path'] == first.arguments['worktree_path']
    assert repo.approvals(task.id)[0]['action_digest'] == approval['action_digest']


async def test_worktree_root_inside_private_state_is_rejected(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    settings = worker.settings.model_copy(update={'worktree_managed_root': worker.settings.data_dir / 'private'})
    parent = repo.claim_next('parent')
    manager = ToolRegistry(ExecutionContext(settings, repo, parent, 'parent')).worktrees
    with pytest.raises(PermissionError, match='state'):
        await manager.spawn({'base_commit': 'a' * 40, 'prompt': 'Read'}, 'spawn')
    assert not (worker.settings.data_dir / 'private').exists()


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Windows Git environment length limit')
async def test_unsupported_worktree_path_is_rejected_before_creating_directory(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    root = tmp_path / 'project'
    git(root, 'init')
    git(root, 'add', 'hello.txt')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
    target_root = tmp_path.joinpath(*(['extra-long-项目-directory'] * 14))
    settings = worker.settings.model_copy(update={'worktree_managed_root': target_root})
    parent = repo.claim_next('parent')
    manager = ToolRegistry(ExecutionContext(settings, repo, parent, 'parent')).worktrees
    result = await manager.spawn({'base_commit': git(root, 'rev-parse', 'HEAD'), 'prompt': 'Read'}, 'spawn')
    assert result.status == 'error'
    assert result.error_code == 'WORKTREE_PATH_UNSUPPORTED'
    assert not target_root.exists()
    assert git(root, 'branch', '--list', 'muse-*') == ''


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Windows checkout filename limits')
@pytest.mark.parametrize('filename', ['x' * 256, 'a\n[stderr]\nb', ' bad.'])
async def test_uncheckoutable_commit_is_rejected_without_creating_branch(tmp_path, filename):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    root = tmp_path / 'project'
    git(root, 'init')
    blob = git_input(root, 'fixture', 'hash-object', '-w', '--stdin')
    tree = git_input(root, '100644 blob ' + blob + '\t' + filename + '\0', 'mktree', '-z')
    commit = git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit-tree', tree, '-m', 'uncheckoutable fixture')
    parent = repo.claim_next('parent')
    manager = ToolRegistry(ExecutionContext(worker.settings, repo, parent, 'parent')).worktrees
    result = await manager.spawn({'base_commit': commit, 'prompt': 'Read'}, 'spawn')
    assert result.status == 'error'
    assert result.error_code == 'WORKTREE_PATH_UNSUPPORTED'
    assert not manager.path('spawn').exists()
    assert git(root, 'branch', '--list', 'muse-*') == ''
