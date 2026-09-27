from muse.contracts import ModelEvent, ToolCall
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry
from test_agent_loop import ScriptedProvider, runtime


async def test_explore_child_has_enforced_read_only_role(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='spawn', name='spawn_task', arguments={'prompt': 'Inspect files', 'role': 'explore'}))],
        [ModelEvent(type='text', text='Waiting for exploration')]])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    child = repo.children(task.id)[0]
    assert child.read_only
    assert child.checkpoint['role'] == 'explore'
    assert all(tool.risk == 'read' for tool in ToolRegistry(ExecutionContext(worker.settings, repo, child, 'inspect')).definitions())


def test_child_tool_restrictions_cannot_be_expanded_by_delegation(tmp_path):
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent')
    repo.checkpoint(parent.id, 'parent', parent.lease_epoch, {'allowed_tools': ['read_file', 'spawn_task']})
    child = repo.spawn_child(parent.id, 'parent', parent.lease_epoch, 'spawn', 'Inspect',
                            capabilities={'allowed_tools': ['read_file', 'write_file']})
    assert child.checkpoint['allowed_tools'] == ['read_file']
