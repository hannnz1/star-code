import asyncio
import json

import pytest

from test_api_contract import api


def test_old_entry_dispatches_to_shared_frontend(monkeypatch):
    import mewcode.__main__ as old
    import muse.compat_cli as compat
    calls = []
    monkeypatch.setattr(compat, 'main', lambda: calls.append('durable'))
    old.main()
    assert calls == ['durable']


@pytest.mark.parametrize('waiting', [False, True])
def test_prompt_entry_uses_worker_queue_and_returns_waiting_without_autoapproval(api, monkeypatch, capsys, waiting):
    from muse.compat_cli import execute_prompt
    from muse.terminal import TerminalClient
    from muse.agent.loop import AgentRunner
    from muse.contracts import ModelEvent, ToolCall
    from muse.tasks.worker import Worker
    from test_agent_loop import ScriptedProvider
    client, app = api
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    turn = ModelEvent(type='call', call=ToolCall(id='cmd', name='run_command', arguments={'command': 'echo fixture'})) if waiting else ModelEvent(type='text', text='Inspected successfully')
    worker = Worker(app.state.settings, app.state.repository, AgentRunner(ScriptedProvider([[turn]])))
    submit = terminal.submit
    def submit_and_work(*args, **kwargs):
        result = submit(*args, **kwargs)
        asyncio.run(worker.run_once())
        return result
    monkeypatch.setattr(terminal, 'submit', submit_and_work)
    result = execute_prompt(terminal, 'Inspect project', output_format='stream-json', wait_seconds=1)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert result == (2 if waiting else 0)
    assert events[-1]['task']['status'] == ('WAITING_APPROVAL' if waiting else 'SUCCEEDED')
    if waiting:
        assert app.state.repository.calls(terminal.task_id)[0]['attempts'] == 0


def test_prompt_wait_deadline_preserves_queued_task(api, capsys):
    from muse.compat_cli import execute_prompt
    from muse.terminal import TerminalClient
    client, app = api
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    assert execute_prompt(terminal, 'Continue in background', wait_seconds=0) == 3
    assert app.state.repository.get(terminal.task_id).status == 'QUEUED'
    assert terminal.task_id in capsys.readouterr().out
