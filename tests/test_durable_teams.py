import pytest

from muse.contracts import TaskRequest
from test_agent_loop import runtime, ScriptedProvider


def test_team_messages_are_durable_scoped_and_idempotent(tmp_path):
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('lead')
    child = repo.spawn_child(task.id, 'lead', parent.lease_epoch, 'spawn', 'inspect')
    unrelated = repo.create(TaskRequest(prompt='unrelated', workspace_id=task.workspace_id, client_request_id='other'))
    first = repo.send_team_message(task.id, 'lead', parent.lease_epoch, 'message', child.id, 'Inspect the tests')
    assert repo.send_team_message(task.id, 'lead', parent.lease_epoch, 'message', child.id, 'Inspect the tests') == first
    from muse.tasks.repository import TaskRepository
    reopened = TaskRepository(worker.settings.data_dir / 'state.sqlite3')
    assert reopened.team_inbox(child.id) == [first]
    assert reopened.team_inbox(task.id) == []
    with pytest.raises(ValueError, match='group'):
        repo.send_team_message(task.id, 'lead', parent.lease_epoch, 'escape', unrelated.id, 'not allowed')
    with pytest.raises(ValueError, match='different'):
        repo.send_team_message(task.id, 'lead', parent.lease_epoch, 'message', child.id, 'changed')


async def test_worker_consumes_team_message_once_across_model_turns(tmp_path):
    from muse.contracts import ModelEvent, ToolCall
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='read', name='read_file', arguments={'path': 'hello.txt'}))],
        [ModelEvent(type='text', text='Reviewed team instructions and the file')]])
    repo, task, worker = runtime(tmp_path, provider)
    parent = repo.claim_next('lead')
    child = repo.spawn_child(task.id, 'lead', parent.lease_epoch, 'spawn', 'inspect')
    message = repo.send_team_message(task.id, 'lead', parent.lease_epoch, 'msg', child.id, 'fixture-team-instruction')
    repo.finish(task.id, 'lead', parent.lease_epoch, 'PAUSED')
    await worker.run_once()
    assert repo.get(child.id).status == 'SUCCEEDED'
    cp = repo.get(child.id).checkpoint
    assert cp['team_message_ids'] == [message['id']]
    assert sum('fixture-team-instruction' in m.get('content', '') for m in cp['messages']) == 1
    assert all('fixture-team-instruction' in str(request) for request in provider.requests)
