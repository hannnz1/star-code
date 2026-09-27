import pytest
from test_agent_loop import ScriptedProvider, runtime

from muse.tasks.repository import TaskRepository


def test_shared_board_dependencies_ownership_revisions_and_replay(tmp_path):
    repo, _, _ = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent')
    child = repo.spawn_child(parent.id, 'parent', parent.lease_epoch, 'spawn', 'Work')
    child = repo.claim_next('child')
    def act(actor, owner, call, **args):
        return repo.team_work(actor.id, owner, actor.lease_epoch, call, args)
    first = act(parent, 'parent', 'create1', action='create', title='Inspect', dependencies=[])
    second = act(parent, 'parent', 'create2', action='create', title='Implement', dependencies=[first['id']])
    with pytest.raises(ValueError, match='dependenc'):
        act(child, 'child', 'claim2', action='claim', item_id=second['id'], expected_revision=1)
    claimed = act(child, 'child', 'claim1', action='claim', item_id=first['id'], expected_revision=1)
    assert claimed['owner_id'] == child.id
    assert act(child, 'child', 'claim1', action='claim', item_id=first['id'], expected_revision=1) == claimed
    with pytest.raises(ValueError, match='revision'):
        act(parent, 'parent', 'stale', action='cancel', item_id=first['id'], expected_revision=1)
    with pytest.raises(ValueError, match='owner'):
        act(parent, 'parent', 'complete', action='complete', item_id=first['id'], expected_revision=2)
    finished = act(child, 'child', 'complete1', action='complete', item_id=first['id'], expected_revision=2)
    assert finished['status'] == 'completed'
    claimed2 = act(parent, 'parent', 'claim2', action='claim', item_id=second['id'], expected_revision=1)
    assert claimed2['status'] == 'in_progress'
    reopened = TaskRepository(repo.db.engine.url.database)
    assert len(reopened.team_board(child.id)) == 2
    assert reopened.team_board(child.id)[0]['status'] == 'completed'


def test_board_does_not_cross_task_groups(tmp_path):
    from muse.contracts import TaskRequest
    repo, task, _ = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent')
    item = repo.team_work(parent.id, 'parent', parent.lease_epoch, 'new', {'action': 'create', 'title': 'Private group'})
    repo.create(TaskRequest(prompt='Other', workspace_id=task.workspace_id, client_request_id='other'))
    other = repo.claim_next('other')
    assert repo.team_board(other.id) == []
    with pytest.raises(ValueError, match='group'):
        repo.team_work(other.id, 'other', other.lease_epoch, 'claim', {'action': 'claim', 'item_id': item['id'], 'expected_revision': 1})


def test_board_keeps_creation_order_when_timestamps_match(tmp_path, monkeypatch):
    from types import SimpleNamespace

    repo, _, _ = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent')
    monkeypatch.setattr('muse.tasks.teams.time.time', lambda: parent.created_at + 1)
    identifiers = iter(['f' * 32, '0' * 32])
    monkeypatch.setattr('muse.tasks.teams.uuid.uuid4', lambda: SimpleNamespace(hex=next(identifiers)))
    first = repo.team_work(parent.id, 'parent', parent.lease_epoch, 'first',
                           {'action': 'create', 'title': 'First'})
    second = repo.team_work(parent.id, 'parent', parent.lease_epoch, 'second',
                            {'action': 'create', 'title': 'Second'})
    assert [item['id'] for item in repo.team_board(parent.id)] == [first['id'], second['id']]


def test_finished_member_releases_unfinished_work_for_lead(tmp_path):
    repo, _, _ = runtime(tmp_path, ScriptedProvider([]))
    lead = repo.claim_next('lead')
    repo.spawn_child(lead.id, 'lead', lead.lease_epoch, 'spawn', 'Work')
    child = repo.claim_next('child')
    item = repo.team_work(child.id, 'child', child.lease_epoch, 'create', {'action': 'create', 'title': 'Inspect'})
    repo.team_work(child.id, 'child', child.lease_epoch, 'claim', {'action': 'claim', 'item_id': item['id'], 'expected_revision': 1})
    repo.finish(child.id, 'child', child.lease_epoch, 'FAILED')
    row = repo.team_board(lead.id)[0]
    assert row['status'] == 'pending' and row['owner_id'] is None
    repo.team_work(lead.id, 'lead', lead.lease_epoch, 'claim', {'action': 'claim', 'item_id': item['id'], 'expected_revision': row['revision']})


def test_lead_cannot_report_success_with_unfinished_board(tmp_path):
    from muse.agent.loop import AgentRunner
    from muse.tools.context import ExecutionContext, TaskControl
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    lead = repo.claim_next('lead')
    repo.team_work(lead.id, 'lead', lead.lease_epoch, 'create', {'action': 'create', 'title': 'Unfinished'})
    from muse.tools.registry import ToolRegistry
    context = ExecutionContext(worker.settings, repo, lead, 'lead')
    ToolRegistry(context)
    with pytest.raises(TaskControl, match='work'):
        AgentRunner._verified_result(context, 'All done')
