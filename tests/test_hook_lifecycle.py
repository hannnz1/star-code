import yaml

from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider, runtime


async def test_system_and_file_hook_events_are_persistent(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='write', name='write_file', arguments={'path': 'hello.txt', 'content': 'changed'}))],
        [ModelEvent(type='text', text='Done')]])
    repo, task, worker = runtime(tmp_path, provider)
    config = tmp_path / 'hooks.yaml'
    events = ['startup', 'shutdown', 'file_change']
    config.write_text(yaml.safe_dump({'hooks': [{'id': event, 'event': event,
        'action': {'type': 'prompt', 'message': event + ' event'}} for event in events]}))
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    await worker.run_once()
    actual = {c['arguments']['payload']['event_name'] for c in repo.calls(task.id) if c['name'].startswith('__hook_')}
    assert actual == set(events)


async def test_error_hook_records_provider_failure_without_retry(tmp_path):
    class Broken:
        calls = 0
        async def stream(self, messages, tools):
            self.calls += 1
            raise RuntimeError('fixture provider failure')
            yield
    provider = Broken()
    repo, task, worker = runtime(tmp_path, provider)
    config = tmp_path / 'hooks.yaml'
    config.write_text(yaml.safe_dump({'hooks': [{'event': 'error', 'action': {'type': 'prompt', 'message': '$ERROR'}}]}))
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    await worker.run_once()
    assert repo.get(task.id).status == 'FAILED'
    assert provider.calls == 1
    assert any(c['result'] and 'fixture provider failure' in c['result']['content'] for c in repo.calls(task.id))
