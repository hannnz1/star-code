import json
import sqlite3
import time
import uuid

import pytest
from pydantic import ValidationError
from test_api_contract import api as api  # noqa: PLC0414 -- pytest fixture re-export
from test_task_lifecycle import make_repo

from muse.config import load_settings
from muse.contracts import TaskRequest, ToolCall
from muse.tasks.repository import TaskRepository
from muse.tools.context import ApprovalRequired, ExecutionContext
from muse.tools.registry import ToolRegistry


def setup(tmp_path, **options):
    repo, workspace = make_repo(tmp_path)
    request = TaskRequest(prompt='Edit a file', workspace_id=workspace, client_request_id=uuid.uuid4().hex, **options)
    task = repo.create(request)
    claim = repo.claim_next('worker', ttl=120)
    settings = load_settings(data_dir=tmp_path / 'data', require_provider=False)
    ctx = ExecutionContext(settings, repo, claim, 'worker')
    return repo, task, ctx, ToolRegistry(ctx)


@pytest.mark.parametrize('mode', ['default', 'acceptEdits', 'plan'])
async def test_write_policy_is_persisted_and_enforced(tmp_path, mode):
    repo, task, ctx, tools = setup(tmp_path, permission_mode=mode)
    call = ToolCall(id='write', name='write_file', arguments={'path': 'new.txt', 'content': 'new'})
    assert task.permission_mode == mode and not task.legacy_policy
    assert TaskRepository(repo.db.engine.url.database).get(task.id).permission_mode == mode
    if mode == 'default':
        with pytest.raises(ApprovalRequired):
            await tools.execute(call)
        assert not (ctx.workspace / 'new.txt').exists()
        approval = repo.approvals(task.id)[0]
        assert approval['permission_mode'] == mode and approval['policy_version'] == 1
    else:
        result = await tools.execute(call)
        assert result.status == ('success' if mode == 'acceptEdits' else 'error')
        assert (ctx.workspace / 'new.txt').exists() == (mode == 'acceptEdits')


def test_new_default_and_read_only_compatibility(tmp_path):
    repo, task, _, _ = setup(tmp_path)
    assert task.permission_mode == 'default'
    request = TaskRequest(prompt='Inspect', workspace_id=task.workspace_id, client_request_id='readonly', read_only=True)
    assert repo.create(request).permission_mode == 'plan'
    with pytest.raises(ValidationError):
        TaskRequest(prompt='Inspect', workspace_id=task.workspace_id, client_request_id='conflict',
                    read_only=True, permission_mode='acceptEdits')


@pytest.mark.parametrize('mode', ['default', 'acceptEdits', 'plan'])
async def test_command_still_needs_approval_and_plan_cannot_delegate(tmp_path, mode):
    repo, task, _, tools = setup(tmp_path, permission_mode=mode)
    call = ToolCall(id='command', name='run_command', arguments={'command': 'echo test'})
    if mode == 'plan':
        assert (await tools.execute(call)).status == 'error'
        denied = await tools.execute(ToolCall(id='child', name='spawn_agent', arguments={'prompt': 'Edit files'}))
        assert denied.status == 'error' and repo.children(task.id) == []
    else:
        with pytest.raises(ApprovalRequired):
            await tools.execute(call)


def test_children_and_conversation_forks_preserve_policy(tmp_path):
    repo, task, ctx, _ = setup(tmp_path, permission_mode='default')
    child = repo.spawn_child(task.id, 'worker', ctx.epoch, 'child', 'Edit component')
    assert child.permission_mode == 'default' and child.policy_version == task.policy_version


async def test_policy_change_invalidates_unconsumed_approval(tmp_path):
    repo, task, _, tools = setup(tmp_path)
    with pytest.raises(ApprovalRequired):
        await tools.execute(ToolCall(id='write', name='write_file', arguments={'path': 'new.txt', 'content': 'new'}))
    approval = repo.approvals(task.id)[0]
    current = repo.get(task.id)
    changed = repo.set_permission_mode(task.id, 'plan', expected_revision=current.revision)
    assert changed.policy_version == 2 and changed.permission_mode == 'plan'
    with pytest.raises(ValueError):
        repo.decide_approval(approval['id'], True, approval['action_digest'])
    assert repo.approvals(task.id)[0]['status'] == 'INVALIDATED'


def test_running_policy_cannot_be_changed(tmp_path):
    repo, task, _, _ = setup(tmp_path)
    with pytest.raises(ValueError, match='running'):
        repo.set_permission_mode(task.id, 'plan', expected_revision=repo.get(task.id).revision)


def test_v8_migration_preserves_legacy_effective_policy_and_approval(tmp_path):
    from muse.permissions.task_policy import action_digest
    from muse.storage.database import SCHEMA
    path = tmp_path / 'old.sqlite3'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    now = time.time()
    args = {'command': 'echo legacy'}
    digest = action_digest({'id': 'old', 'workspace_id': 'w', 'legacy_policy': True}, 'run_command', args)
    with sqlite3.connect(path) as conn:
        for statement in SCHEMA[:-1]:
            conn.execute(statement)
        conn.execute('ALTER TABLE tasks ADD COLUMN read_only INTEGER NOT NULL DEFAULT 0')
        conn.execute('INSERT INTO workspaces VALUES(?,?,?,?)', ('w', 'Workspace', str(workspace), now))
        for identifier, read_only in [('old', 0), ('inspection', 1)]:
            conn.execute("INSERT INTO tasks(id,prompt,workspace_id,scenario,client_request_id,status,created_at,updated_at,read_only) VALUES(?,?,?,?,?,'QUEUED',?,?,?)",
                         (identifier, 'Inspect', 'w', 'coding', identifier, now, now, read_only))
        conn.execute("INSERT INTO tool_calls(task_id,id,name,arguments,risk,status,digest,created_at,updated_at) VALUES('old','cmd','run_command',?,'execute','PREPARED',?,?,?)", (json.dumps(args), digest, now, now))
        conn.execute("INSERT INTO approvals VALUES('approval','old','cmd',?,'APPROVED',?,?)", (digest, now + 3600, now))
    repo = TaskRepository(path)
    assert repo.get('old').permission_mode == 'acceptEdits' and repo.get('old').legacy_policy
    assert repo.get('inspection').permission_mode == 'plan' and repo.get('inspection').legacy_policy
    assert repo.approvals('old')[0]['action_digest'] == digest
    assert repo.approvals('old')[0]['permission_mode'] == 'acceptEdits'
    claimed = repo.claim_next('worker')
    assert claimed.id == 'old'
    assert repo.begin_call('old', 'worker', claimed.lease_epoch, 'cmd') is True


async def test_changed_mode_requires_new_approval_before_write(tmp_path):
    repo, task, ctx, tools = setup(tmp_path)
    call = ToolCall(id='write', name='write_file', arguments={'path': 'new.txt', 'content': 'new'})
    with pytest.raises(ApprovalRequired):
        await tools.execute(call)
    old = repo.approvals(task.id)[0]
    current = repo.get(task.id)
    changed = repo.set_permission_mode(task.id, 'default', expected_revision=current.revision)
    assert changed.policy_version == 1  # No-op policy change is idempotent.
    changed = repo.set_permission_mode(task.id, 'acceptEdits', expected_revision=current.revision)
    assert changed.policy_version == 2
    changed = repo.set_permission_mode(task.id, 'default', expected_revision=changed.revision)
    repo.control(task.id, 'resume', expected_revision=changed.revision)
    claim = repo.claim_next('second')
    second = ToolRegistry(ExecutionContext(ctx.settings, repo, claim, 'second'))
    with pytest.raises(ApprovalRequired):
        await second.execute(call)
    pending = next(row for row in repo.approvals(task.id) if row['status'] == 'PENDING')
    assert pending['action_digest'] != old['action_digest']
    assert pending['policy_version'] == 3 and not (ctx.workspace / 'new.txt').exists()


def test_api_and_terminal_use_same_mode_and_revision(api):
    from muse.terminal import TerminalClient
    client, app = api
    workspace = client.get('/api/workspaces').json()[0]
    terminal = TerminalClient(client, workspace['id'])
    terminal.handle('/mode acceptEdits')
    terminal.submit('Edit file')
    task = app.state.repository.get(terminal.task_id)
    assert task.permission_mode == 'acceptEdits'
    terminal.handle('/mode plan')
    shown = client.get('/api/tasks/' + task.id).json()
    assert shown['permission_mode'] == 'plan' and shown['policy_version'] == 2
    response = client.post('/api/tasks/' + task.id + '/policy', json={'permission_mode': 'default', 'expected_revision': task.revision})
    assert response.status_code == 409
