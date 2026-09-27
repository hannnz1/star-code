import pytest
from sqlalchemy import text

from muse.contracts import ModelEvent, TaskRequest
from muse.extensions.roles import role_prompt
from muse.terminal import TerminalClient
from test_agent_loop import ScriptedProvider, runtime
from test_api_contract import api


@pytest.mark.parametrize('scenario', ['research', 'documents'])
@pytest.mark.parametrize('role', ['explore', 'plan', 'verification'])
async def test_restricted_child_can_return_reference_but_parent_still_needs_deliverable(tmp_path, scenario, role):
    provider = ScriptedProvider([[ModelEvent(type='text', text='Inspected: no changes needed.')],
                                 [ModelEvent(type='text', text='Parent answer without report')],
                                 [ModelEvent(type='text', text='Reviewed children without report')]])
    repo, original, worker = runtime(tmp_path, provider)
    repo.control(original.id, 'cancel', expected_revision=original.revision)
    parent = repo.create(TaskRequest(prompt='Prepare report', scenario=scenario,
                         workspace_id=original.workspace_id, client_request_id='parent'))
    parent = repo.claim_next('parent-worker')
    prompt, caps = role_prompt(role, 'Inspect this task')
    child = repo.spawn_child(parent.id, 'parent-worker', parent.lease_epoch, 'spawn', prompt, capabilities=caps)
    await worker.run_once()
    assert repo.get(child.id).status == 'SUCCEEDED'
    assert 'reference' in provider.requests[0][0]['content'].lower()
    repo.abandon(parent.id, 'parent-worker', parent.lease_epoch)
    await worker.run_once()
    # First the parent pauses to collect child results; then the final gate runs.
    await worker.run_once()
    assert repo.get(parent.id).status == 'FAILED'
    assert repo.get(parent.id).error == 'Task has no saved deliverable'


def test_expired_approval_renewal_requires_new_review_and_decision(api):
    client, app = api
    repo = app.state.repository
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    terminal.handle('Run tests')
    task = repo.claim_next('worker')
    repo.prepare_call(task.id, 'worker', task.lease_epoch, 'cmd', 'run_command', {'command': 'echo fixture'}, 'execute')
    approval = repo.request_approval(task.id, 'worker', task.lease_epoch, 'cmd')
    with repo.db.transaction() as conn:
        conn.execute(text('UPDATE approvals SET expires_at=1 WHERE id=:id'), {'id': approval['id']})
    body = {'action_digest': approval['action_digest']}
    assert client.post(f"/api/approvals/{approval['id']}/decision", json={**body, 'allow': True}).status_code == 409
    assert client.post(f"/api/approvals/{approval['id']}/renew", json={'action_digest': 'wrong'}).status_code == 409
    with pytest.raises(ValueError, match='approvals'):
        terminal.handle('/renew ' + approval['id'])
    terminal.handle('/approvals')
    terminal.handle('/renew ' + approval['id'])
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    assert repo.claim_next('worker') is None
    assert repo.calls(task.id)[0]['attempts'] == 0
    with pytest.raises(ValueError, match='approvals'):
        terminal.handle('/approve ' + approval['id'])
    terminal.handle('/approvals')
    terminal.handle('/approve ' + approval['id'])
    assert repo.get(task.id).status == 'QUEUED'
    assert client.post(f"/api/approvals/{approval['id']}/renew", json=body).status_code == 409
