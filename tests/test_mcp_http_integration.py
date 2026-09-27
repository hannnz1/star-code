import asyncio
import socket
import threading

import uvicorn
import yaml
from mcp.server.fastmcp import FastMCP

from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider, runtime


async def test_real_http_mcp_discovery_call_and_approval(tmp_path):
    mcp = FastMCP('local-http-fixture', stateless_http=True, json_response=True)
    @mcp.tool()
    def echo(value: int) -> str:
        return f'http-value={value}'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(), host='127.0.0.1', port=port,
                                          log_level='error', timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.02)
        assert server.started
        config = tmp_path / 'http.yaml'
        config.write_text(yaml.safe_dump({'mcp_servers': [{'name': 'fixture', 'url': f'http://127.0.0.1:{port}/mcp'}]}))
        provider = ScriptedProvider([
            [ModelEvent(type='call', call=ToolCall(id='discover', name='mcp_discover', arguments={'server': 'fixture'}))],
            [ModelEvent(type='call', call=ToolCall(id='echo', name='mcp_call', arguments={'server': 'fixture', 'tool': 'echo', 'arguments': {'value': 23}}))],
            [ModelEvent(type='text', text='Received HTTP result')]])
        repo, task, worker = runtime(tmp_path, provider)
        worker.settings = worker.settings.model_copy(update={'config_path': config})
        for _ in range(3):
            await worker.run_once()
            for approval in repo.approvals(task.id):
                if approval['status'] == 'PENDING':
                    repo.decide_approval(approval['id'], True, approval['action_digest'])
        call = next(c for c in repo.calls(task.id) if c['id'] == 'echo')
        assert call['result']['content'] == 'http-value=23'
        assert call['attempts'] == 1
        assert len(repo.approvals(task.id)) == 2
    finally:
        server.should_exit = True
        await asyncio.to_thread(thread.join, 5)
        assert not thread.is_alive()
