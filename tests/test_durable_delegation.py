from muse.contracts import ModelEvent, ToolCall
from muse.tasks.repository import TaskRepository
from test_agent_loop import ScriptedProvider, runtime


def test_restarted_worker_cannot_expand_root_budgets(tmp_path):
    from muse.tools.context import ExecutionContext
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]), max_turns=2, max_tool_calls=3, max_active_seconds=4)
    claimed = repo.claim_next('first')
    first = ExecutionContext(worker.settings, repo, claimed, 'first', enforce_budgets=True)
    repo.abandon(task.id, 'first', claimed.lease_epoch)
    claimed = repo.claim_next('second')
    expanded = worker.settings.model_copy(update={'max_turns': 200, 'max_tool_calls': 300, 'max_active_seconds': 400})
    second = ExecutionContext(expanded, repo, claimed, 'second', enforce_budgets=True)
    assert (second.settings.max_turns, second.settings.max_tool_calls, second.settings.max_active_seconds) == (2, 3, 4)
    assert first.settings.max_turns == 2


def test_concurrent_workers_share_atomic_model_budget(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from muse.tools.context import ExecutionContext
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]), max_turns=2)
    parent = repo.claim_next('parent')
    ExecutionContext(worker.settings, repo, parent, 'parent', enforce_budgets=True)
    repo.spawn_child(task.id, 'parent', parent.lease_epoch, 'spawn', 'child')
    child = repo.claim_next('child')
    ExecutionContext(worker.settings, repo, child, 'child', enforce_budgets=True)

    def reserve(index):
        current, owner = (parent, 'parent') if index % 2 else (child, 'child')
        try:
            repo.reserve_model_request(current.id, owner, current.lease_epoch, 100)
            return True
        except ValueError as error:
            assert 'budget' in str(error)
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(8))) == 2


async def test_spawn_commit_survives_worker_crash_without_duplicate_child(tmp_path, monkeypatch):
    import asyncio
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='spawn', name='spawn_task', arguments={'prompt': 'child'}))],
        [ModelEvent(type='text', text='waiting')]])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    complete = repo.complete_call

    def crash(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(repo, 'complete_call', crash)
    import pytest
    with pytest.raises(asyncio.CancelledError):
        await worker.run_once()
    monkeypatch.setattr(repo, 'complete_call', complete)
    assert repo.get(task.id).status == 'QUEUED'
    assert repo.calls(task.id)[0]['status'] == 'DONE'
    assert repo.calls(task.id)[0]['attempts'] == 1
    await worker.run_once()
    assert len(repo.children(task.id)) == 1
    assert repo.get(task.id).status == 'PAUSED'


async def test_child_is_persistent_and_parent_waits_for_result(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='spawn', name='spawn_task', arguments={'prompt': 'Read hello.txt and summarize'}))],
        [ModelEvent(type='text', text='Delegated the inspection.')],
        [ModelEvent(type='text', text='Child inspected the project.')],
        [ModelEvent(type='text', text='Reviewed the child result.')],
    ])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    assert repo.get(task.id).status == 'PAUSED'
    reopened = TaskRepository(worker.settings.data_dir / 'state.sqlite3')
    assert len(reopened.children(task.id)) == 1
    await worker.run_once()
    assert reopened.children(task.id)[0].status == 'SUCCEEDED'
    await worker.run_once()
    assert repo.get(task.id).status == 'SUCCEEDED'
    assert 'Child inspected' in str(provider.requests[-1])


async def test_parent_cancel_cancels_queued_child(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='spawn', name='spawn_task', arguments={'prompt': 'child'}))],
        [ModelEvent(type='text', text='waiting')]])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    repo.control(task.id, 'cancel', expected_revision=repo.get(task.id).revision)
    assert all(child.status == 'CANCELLED' for child in repo.children(task.id))
    assert await worker.run_once() is False


async def test_delegation_cannot_multiply_model_budget(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='spawn', name='spawn_task', arguments={'prompt': 'child'}))],
        [ModelEvent(type='text', text='waiting')],
        [ModelEvent(type='text', text='must not request this')]])
    repo, task, worker = runtime(tmp_path, provider, max_turns=2)
    await worker.run_once()
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    await worker.run_once()
    assert len(provider.requests) == 2
    assert repo.children(task.id)[0].status == 'FAILED'
