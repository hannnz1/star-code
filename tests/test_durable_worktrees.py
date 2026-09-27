import json
import subprocess
from pathlib import Path

from test_agent_loop import ScriptedProvider, runtime

from muse.contracts import ModelEvent, ToolCall
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def test_worktree_tool_explains_registered_role_requirement(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    task = repo.claim_next('parent')
    registry = ToolRegistry(ExecutionContext(worker.settings, repo, task, 'parent'))
    tool = registry.entries['spawn_worktree'][0]
    assert 'omit role' in tool.description.lower()
    assert 'display name' in tool.parameters['properties']['role']['description'].lower()


async def test_worktree_child_uses_isolated_checkout_and_survives_restart(tmp_path):
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
