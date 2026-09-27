import json
import sys
import yaml
from types import SimpleNamespace

from muse.agent.loop import AgentRunner
from muse.contracts import ModelEvent, ToolCall
from muse.tasks.worker import Worker
from test_agent_loop import ScriptedProvider, runtime


async def test_mcp_discovery_and_call_each_require_durable_approval(tmp_path, monkeypatch):
    calls = []
    class Client:
        def __init__(self, config):
            self.config = config
        async def connect(self):
            calls.append('connect')
        async def list_tools(self):
            return [SimpleNamespace(name='echo', description='echo input', inputSchema={
                'type': 'object', 'properties': {'value': {'type': 'integer'}}, 'required': ['value']})]
        async def call_tool(self, name, args):
            calls.append((name, args))
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text=str(args['value']))])
        async def close(self):
            calls.append('close')
    monkeypatch.setattr('mewcode.mcp.client.MCPClient', Client)
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='discover', name='mcp_discover', arguments={'server': 'local'}))],
        [ModelEvent(type='call', call=ToolCall(id='call', name='mcp_call', arguments={'server': 'local', 'tool': 'echo', 'arguments': {'value': 7}}))],
        [ModelEvent(type='text', text='Read the MCP result.')],
    ])
    repo, task, original = runtime(tmp_path, provider)
    config = tmp_path / 'extensions.yaml'
    config.write_text('''mcp_servers:
  - name: local
    command: fixture-command
''')
    settings = original.settings.model_copy(update={'config_path': config})
    worker = Worker(settings, repo, AgentRunner(provider))
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    assert calls == []
    first = repo.approvals(task.id)[0]
    repo.decide_approval(first['id'], True, first['action_digest'])
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    assert calls == ['connect', 'close']
    second = next(a for a in repo.approvals(task.id) if a['tool_call_id'] == 'call')
    repo.decide_approval(second['id'], True, second['action_digest'])
    await worker.run_once()
    assert ('echo', {'value': 7}) in calls
    saved = next(c for c in repo.calls(task.id) if c['id'] == 'call')
    assert saved['result']['content'] == '7'
    assert saved['attempts'] == 1


async def test_mcp_configuration_change_invalidates_pending_action(tmp_path, monkeypatch):
    provider = ScriptedProvider([[ModelEvent(type='call', call=ToolCall(id='d', name='mcp_discover', arguments={'server': 'local'}))]])
    repo, task, original = runtime(tmp_path, provider)
    path = tmp_path / 'extensions.yaml'
    path.write_text('mcp_servers:\n  - name: local\n    command: original\n')
    worker = Worker(original.settings.model_copy(update={'config_path': path}), repo, AgentRunner(provider))
    await worker.run_once()
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    path.write_text('mcp_servers:\n  - name: local\n    command: changed\n')
    await worker.run_once()
    assert repo.get(task.id).status == 'FAILED'
    assert repo.calls(task.id)[0]['attempts'] == 0


async def test_real_local_stdio_server_through_worker(tmp_path):
    server = tmp_path / 'server.py'
    server.write_text('from mcp.server.fastmcp import FastMCP\n'
        'app=FastMCP("local-test")\n'
        '@app.tool()\ndef echo(value: int) -> str:\n return f"value={value}"\n'
        'app.run(transport="stdio")\n')
    config = tmp_path / 'config.yaml'
    config.write_text(yaml.safe_dump({'mcp_servers': [{'name': 'local', 'command': sys.executable, 'args': [str(server)]}]}))
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='discover', name='mcp_discover', arguments={'server': 'local'}))],
        [ModelEvent(type='call', call=ToolCall(id='echo', name='mcp_call', arguments={'server': 'local', 'tool': 'echo', 'arguments': {'value': 19}}))],
        [ModelEvent(type='text', text='Local server returned value=19.')]])
    repo, task, original = runtime(tmp_path, provider)
    worker = Worker(original.settings.model_copy(update={'config_path': config}), repo, AgentRunner(provider))
    for _ in range(3):
        await worker.run_once()
        for approval in repo.approvals(task.id):
            if approval['status'] == 'PENDING':
                repo.decide_approval(approval['id'], True, approval['action_digest'])
    record = next(c for c in repo.calls(task.id) if c['id'] == 'echo')
    assert record['result']['content'] == 'value=19'
    assert record['attempts'] == 1
