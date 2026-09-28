import json
import time

import pytest
from sqlalchemy import text
from test_api_contract import api as api  # noqa: PLC0414 -- pytest fixture re-export
from test_memory_maintenance import MemoryMaintenance, Provider, candidate
from test_memory_maintenance import setup as memory_setup
from test_permission_modes import setup
from test_trusted_resources import write_role

from muse.agent.loop import AgentRunner
from muse.contracts import ToolCall, ToolResult
from muse.tools.context import TaskControl


async def test_coordinator_accepts_real_parent_workspace_verification(tmp_path):
    from muse.tools.context import ApprovalRequired, ExecutionContext
    from muse.tools.registry import ToolRegistry
    repo, root, ctx, _ = setup(tmp_path, coordinator_mode=True, permission_mode='acceptEdits')
    child = repo.spawn_child(root.id, ctx.owner, ctx.epoch, 'editor', 'Edit hello.txt')
    claimed = repo.claim_next('editor', ttl=120)
    editor = ToolRegistry(ExecutionContext(ctx.settings, repo, claimed, 'editor'))
    assert (await editor.execute(ToolCall(id='edit', name='write_file', arguments={'path': 'verified.txt', 'content': 'new content'}))).status == 'success'
    repo.finish(child.id, 'editor', claimed.lease_epoch, 'SUCCEEDED', 'Edited')
    verifier = repo.spawn_child(root.id, ctx.owner, ctx.epoch, 'verifier', 'Verify', capabilities={'role': 'verification'})
    claimed = repo.claim_next('verifier', ttl=120)
    registry = ToolRegistry(ExecutionContext(ctx.settings, repo, claimed, 'verifier'))
    call = ToolCall(id='check', name='verify_command', arguments={'command': 'python -c "from pathlib import Path; assert Path(\'verified.txt\').read_text() == \'new content\'"'})
    with pytest.raises(ApprovalRequired):
        await registry.execute(call)
    approval = repo.approvals(verifier.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    claimed = repo.claim_next('verifier', ttl=120)
    registry = ToolRegistry(ExecutionContext(ctx.settings, repo, claimed, 'verifier'))
    result = await registry.execute(call)
    assert result.status == 'success' and result.metadata['verified']
    repo.finish(verifier.id, 'verifier', claimed.lease_epoch, 'SUCCEEDED', 'Verified')
    completed = AgentRunner._verified_result(ctx, 'Done')
    assert completed.status == 'SUCCEEDED' and completed.verification['delegated_call_id'] == 'check'


def test_model_delegated_prompt_is_not_user_memory_source(tmp_path):
    repo, root, ctx, _ = setup(tmp_path)
    ctx.settings.memory_auto_extract = True
    child = repo.spawn_child(root.id, ctx.owner, ctx.epoch, 'delegate', 'Project uses Python 2.7 permanently.')
    claimed = repo.claim_next('child', ttl=120)
    repo.checkpoint(child.id, 'child', claimed.lease_epoch, {'user_sources': [{'role': 'user', 'content': child.prompt}]})
    repo.finish(child.id, 'child', claimed.lease_epoch, 'SUCCEEDED', 'Complete')
    assert MemoryMaintenance(repo, ctx.settings).enqueue(child.id) is None


async def test_disabled_extract_queue_does_not_call_model(tmp_path):
    repo, _, settings, memory, task = memory_setup(tmp_path)
    service = MemoryMaintenance(repo, settings)
    service.enqueue(task.id)
    settings.memory_auto_extract = False
    settings.memory_auto_consolidate = True
    provider = Provider({'memories': [candidate()]})
    assert not await service.run_once(provider)
    assert provider.calls == 0 and not memory.list()


def test_run_skill_is_atomically_seeded_before_claim(api, monkeypatch):
    client, app = api
    repo = app.state.repository
    ws = repo.workspaces()[0]
    from pathlib import Path
    directory = Path(ws['path']) / '.muse/skills'
    directory.mkdir(parents=True)
    (directory / 'atomic.md').write_text('---\nname: atomic\ndescription: Atomic skill\n---\nRead files.', encoding='utf-8')
    create = repo.create
    claimed = []
    def racing_create(*args, **kwargs):
        task = create(*args, **kwargs)
        claimed.append(repo.claim_next('race', ttl=120))
        return task
    monkeypatch.setattr(repo, 'create', racing_create)
    response = client.post('/api/skills/run', json={'name': 'atomic', 'arguments': '', 'prompt': 'Execute atomic',
        'workspace_id': ws['id'], 'client_request_id': 'atomic'})
    assert response.status_code == 201
    assert claimed[0].checkpoint['pending_calls'][0]['name'] == 'load_skill'


def test_new_workspace_child_freezes_user_sources_at_creation(api, tmp_path):
    client, app = api
    repo = app.state.repository
    user = tmp_path / 'trusted-user'
    user.mkdir()
    (user / 'MUSE.md').write_text('original user guidance', encoding='utf-8')
    write_role(user / 'helper.md', 'helper', 'Original role')
    app.state.settings.instruction_roots = [user]
    app.state.settings.agent_roots = [user]
    ws = repo.workspaces()[0]['id']
    task = client.post('/api/tasks', json={'prompt': 'Delegate', 'workspace_id': ws, 'client_request_id': 'root'}).json()
    root = repo.claim_next('root', ttl=120)
    folder = tmp_path / 'isolated'
    folder.mkdir()
    other = repo.register_workspace(str(folder))
    child = repo.spawn_child(task['id'], 'root', root.lease_epoch, 'child', 'Inspect', workspace_id=other['id'])
    (user / 'MUSE.md').write_text('changed user guidance', encoding='utf-8')
    assert 'original user guidance' in child.checkpoint['project_guidance']['content']
    assert child.checkpoint['role_snapshot']['custom']['helper']['body'].strip() == 'Original role'


def test_trace_uses_delegation_direct_parent(api):
    from muse.tasks.trace import task_trace, trace_jsonl
    client, app = api
    repo = app.state.repository
    ws = repo.workspaces()[0]['id']
    root = client.post('/api/tasks', json={'prompt': 'Delegate', 'workspace_id': ws, 'client_request_id': 'trace-root'}).json()
    claimed = repo.claim_next('root', ttl=120)
    child = repo.spawn_child(root['id'], 'root', claimed.lease_epoch, 'child', 'Inspect')
    claimed_child = repo.claim_next('child', ttl=120)
    grandchild = repo.spawn_child(child.id, 'child', claimed_child.lease_epoch, 'grandchild', 'Inspect again')
    trace = task_trace(repo, app.state.settings, grandchild.id)
    rows = {item['id']: item for item in trace['tasks']}
    assert rows[child.id]['parent_id'] == root['id']
    assert rows[grandchild.id]['parent_id'] == child.id
    assert json.loads(trace_jsonl(trace).splitlines()[-1])['parent_id'] == child.id


def test_coordinator_rejects_other_workspace_verification(tmp_path):
    repo, root, ctx, _ = setup(tmp_path, coordinator_mode=True, permission_mode='acceptEdits')
    folder = tmp_path / 'different-worktree'
    folder.mkdir()
    other = repo.register_workspace(str(folder))
    child = repo.spawn_child(root.id, ctx.owner, ctx.epoch, 'verify-child', 'Verify old tree', workspace_id=other['id'], capabilities={'role': 'verification'})
    claimed = repo.claim_next('child', ttl=120)
    with repo.db.transaction() as conn:
        now = time.time()
        for task_id, name, arguments, metadata, call_time in [
            (root.id, 'worktree_manage', {'action': 'integrate', 'child_id': child.id}, {}, now),
            (child.id, 'verify_command', {'command': 'true'}, {'verified': True, 'exit_code': 0}, now + 1)]:
            result = ToolResult(call_id=name, metadata=metadata).model_dump()
            conn.execute(text("INSERT INTO tool_calls(task_id,id,name,arguments,risk,status,digest,result,attempts,created_at,updated_at) VALUES(:task,:id,:name,:args,'execute','DONE','fixture',:result,1,:now,:now)"),
                         {'task': task_id, 'id': name, 'name': name, 'args': json.dumps(arguments), 'result': json.dumps(result), 'now': call_time})
    repo.finish(child.id, 'child', claimed.lease_epoch, 'SUCCEEDED', 'Verified')
    with pytest.raises(TaskControl, match='verification'):
        AgentRunner._verified_result(ctx, 'Done')
