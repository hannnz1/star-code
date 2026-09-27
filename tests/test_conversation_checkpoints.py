import pytest

from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider, runtime


async def test_rewind_forks_complete_conversation_without_replaying_tools(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='read', name='read_file', arguments={'path': 'hello.txt'}))],
        [ModelEvent(type='text', text='Read the file')],
        [ModelEvent(type='text', text='Continued with historical context')]])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    points = repo.conversation_checkpoints(task.id)
    assert len(points) >= 2
    source = repo.get(task.id)
    fork = repo.fork_checkpoint(task.id, points[-1]['sequence'], source.revision, 'Explain the earlier result', 'fork-once')
    assert repo.fork_checkpoint(task.id, points[-1]['sequence'], source.revision, 'Explain the earlier result', 'fork-once').id == fork.id
    assert repo.get(task.id).status == 'SUCCEEDED'
    await worker.run_once()
    assert repo.get(fork.id).status == 'SUCCEEDED'
    assert repo.calls(fork.id) == []
    assert 'local content' in str(provider.requests[-1])
    assert (tmp_path / 'project/hello.txt').read_text() == 'local content'
    with pytest.raises(ValueError):
        repo.fork_checkpoint(task.id, points[-1]['sequence'], source.revision, 'Changed prompt', 'fork-once')
