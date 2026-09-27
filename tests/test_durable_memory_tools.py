from muse.contracts import ModelEvent, ToolCall
from muse.memory.service import MemoryService
from test_agent_loop import ScriptedProvider, runtime


async def test_memory_write_requires_approval_and_reaches_shared_memory_store(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='remember', name='save_memory', arguments={'scope': 'project', 'title': 'Testing', 'content': 'Run local tests before finishing.'}))],
        [ModelEvent(type='text', text='Preference saved')]])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    memory = MemoryService(repo, worker.settings)
    assert memory.list() == []
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    assert repo.get(task.id).status == 'SUCCEEDED'
    assert memory.for_task(task.workspace_id)[0]['content'] == 'Run local tests before finishing.'
