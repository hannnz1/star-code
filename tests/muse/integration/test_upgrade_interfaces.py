import json
import uuid

import pytest
from test_api_contract import api as api  # noqa: PLC0414 -- pytest fixture re-export
from test_permission_modes import setup

from muse.contracts import TaskRequest, ToolCall
from muse.terminal import TerminalClient


async def test_coordinator_cannot_write_or_run_wrapped_actions(tmp_path):
    repo, task, ctx, tools = setup(tmp_path, coordinator_mode=True)
    assert task.coordinator_mode
    assert 'spawn_task' in {tool.name for tool in tools.definitions()}
    for name, args in [('write_file', {'path': 'bad', 'content': 'x'}),
                       ('run_command', {'command': 'echo bad'}),
                       ('verify_command', {'command': 'echo bad'}),
                       ('install_skill', {'repository': 'a/b', 'commit': 'a' * 40, 'path': '.', 'name': 'bad'})]:
        assert (await tools.execute(ToolCall(id=name, name=name, arguments=args))).status != 'success'
    assert not (ctx.workspace / 'bad').exists() and not repo.approvals(task.id)


def test_api_trace_and_reviewed_plan_provenance(api):
    client, app = api
    repo = app.state.repository
    ws = repo.workspaces()[0]['id']
    plan = repo.create(TaskRequest(prompt='Inspect plan', workspace_id=ws, client_request_id='plan-link', read_only=True))
    claim = repo.claim_next('test', ttl=120)
    repo.finish(plan.id, 'test', claim.lease_epoch, 'SUCCEEDED', 'Implement a safe change')
    terminal = TerminalClient(client, ws)
    terminal.task_id = plan.id
    executed = json.loads(terminal.handle('/do Follow the approved plan'))
    trace = client.get(f"/api/tasks/{executed['id']}/trace").json()
    assert trace['schema_version'] == 1
    assert trace['tasks'][0]['plan']['task_id'] == plan.id
    assert len(trace['tasks'][0]['plan']['sha256']) == 64
    assert 'provider_states' not in json.dumps(trace)


def test_run_skill_creates_durable_tool_request(api):
    client, app = api
    repo = app.state.repository
    ws = repo.workspaces()[0]['id']
    root = repo.workspace(ws)['path']
    from pathlib import Path
    folder = Path(root) / '.muse' / 'skills'
    folder.mkdir(parents=True)
    (folder / 'safe.md').write_text('---\nname: safe\ndescription: Test skill\n---\nUse Python for $ARGUMENTS\n', encoding='utf-8')
    terminal = TerminalClient(client, ws)
    output = json.loads(terminal.handle('/run-skill safe a $(danger) "b c"'))
    cp = repo.get(output['id']).checkpoint
    assert cp['pending_calls'][0]['arguments']['arguments'] == 'a $(danger) "b c"'
    assert cp['pending_calls'][0]['name'] == 'load_skill'
    assert len(cp['pending_calls'][0]['arguments']['_source_sha256']) == 64


def test_unknown_plan_hash_and_both_rewind_rejected(api):
    client, app = api
    ws = app.state.repository.workspaces()[0]['id']
    response = client.post('/api/tasks', json={'prompt': 'Do it', 'workspace_id': ws,
        'client_request_id': uuid.uuid4().hex, 'plan_task_id': 'missing', 'plan_sha256': 'x' * 64})
    assert response.status_code in {404, 409, 422}
    terminal = TerminalClient(client, ws)
    with pytest.raises(ValueError, match='separate|unsupported'):
        terminal.handle('/rewind both')
