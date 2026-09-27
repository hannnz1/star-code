import yaml
from test_agent_loop import ScriptedProvider, runtime

from muse.agent.loop import AgentRunner
from muse.contracts import ModelEvent, ToolCall
from muse.tasks.worker import Worker


async def test_hook_rejects_write_before_file_mutation(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='write', name='write_file', arguments={'path': 'hello.txt', 'content': 'forbidden'}))],
        [ModelEvent(type='text', text='The configured hook blocked the write.')]])
    repo, _, original = runtime(tmp_path, provider)
    config = tmp_path / 'hooks.yaml'
    config.write_text(yaml.safe_dump({'hooks': [{'id': 'guard', 'event': 'pre_tool_use',
        'if': 'tool == "write_file"', 'reject': True, 'action': {'type': 'prompt', 'message': 'blocked by project hook'}}]}))
    worker = Worker(original.settings.model_copy(update={'config_path': config}), repo, AgentRunner(provider))
    await worker.run_once()
    assert (tmp_path / 'project/hello.txt').read_text() == 'local content'
    assert 'blocked by project hook' in str(provider.requests[-1])


async def test_command_hook_requires_approval_before_read(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='read', name='read_file', arguments={'path': 'hello.txt'}))],
        [ModelEvent(type='text', text='Read completed.')]])
    repo, task, original = runtime(tmp_path, provider, max_turns=2)
    config = tmp_path / 'hooks.yaml'
    config.write_text(yaml.safe_dump({'hooks': [{'id': 'notify', 'event': 'pre_tool_use',
        'if': 'tool == "read_file"', 'action': {'type': 'command', 'command': 'echo hook-evidence'}}]}))
    worker = Worker(original.settings.model_copy(update={'config_path': config}), repo, AgentRunner(provider))
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    assert not any(c['name'] == 'read_file' for c in repo.calls(task.id))
    pending = next(c for c in repo.calls(task.id) if c['name'].startswith('__hook_'))
    assert pending['arguments']['action_preview']['command'] == 'echo hook-evidence'
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    assert any('hook-evidence' in c['result']['content'] for c in repo.calls(task.id) if c['result'])
