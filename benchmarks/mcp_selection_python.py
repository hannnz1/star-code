"""Original ten synthetic MCP questions through the public Python Worker.

Uses real configured model and local HTTP MCP, not live business services.
"""
import argparse
import asyncio
import hashlib
import json
import socket
import threading
import time
from pathlib import Path

import uvicorn
import yaml
from mcp.server.fastmcp import FastMCP

from muse.agent.loop import AgentRunner
from muse.config import load_settings
from muse.contracts import TaskRequest
from muse.providers.compatible import HttpModelProvider
from muse.tasks.repository import TaskRepository
from muse.tasks.worker import Worker
from muse.tools.registry import ToolRegistry


async def run(args, registry_factory=ToolRegistry, mode='LAZY'):
    data = json.loads(args.fixture.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=False)
    service = FastMCP('original-selection-fixture', stateless_http=True, json_response=True)
    remote_calls = []
    for tool in data['tools']:
        def create(name):
            def lookup(entity_id: str) -> str:
                remote_calls.append({'tool': name, 'entity_id': entity_id})
                for case in data['tasks']:
                    if case['tool'] == name and case['entity_id'] == entity_id:
                        return case['expected_result']
                return 'NO_MATCH'
            return lookup
        service.add_tool(create(tool['name']), name=tool['name'], description=tool['description'])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(service.streamable_http_app(), host='127.0.0.1', port=port, log_level='error', timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    config = args.output / 'synthetic-mcp.yaml'
    config.write_text(yaml.safe_dump({'mcp_servers': [{'name': 'fixture', 'url': f'http://127.0.0.1:{port}/mcp'}]}))
    records = []
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.05)
        if not server.started:
            raise RuntimeError('Local fixture server did not start')
        for case in data['tasks']:
            target = args.output / case['id']
            target.mkdir()
            workspace = target / 'workspace'
            workspace.mkdir()
            settings = load_settings(args.config, data_dir=target / 'private-state').model_copy(update={'config_path': config})
            repo = TaskRepository(settings.data_dir / 'state.sqlite3')
            ws = repo.register_workspace(str(workspace))
            task = repo.create(TaskRequest(prompt=case['prompt'], workspace_id=ws['id'], scenario='general', client_request_id=case['id']))
            requests = []
            class RecordedProvider:
                async def stream(self, messages, definitions):
                    requests.append({'messages': messages, 'tools': [d.model_dump() for d in definitions]})
                    async for event in HttpModelProvider(settings.provider).stream(messages, definitions):
                        yield event
            worker = Worker(settings, repo, AgentRunner(RecordedProvider(), registry_factory=registry_factory))
            start, first = time.monotonic(), len(remote_calls)
            for _ in range(8):
                await worker.run_once()
                current = repo.get(task.id)
                if current.status != 'WAITING_APPROVAL':
                    break
                for approval in repo.approvals(task.id):
                    if approval['status'] == 'PENDING':
                        repo.decide_approval(approval['id'], approval['name'] in {'mcp_discover', 'mcp_call'} and approval['arguments'].get('server') == 'fixture', approval['action_digest'])
            current = repo.get(task.id)
            calls = repo.calls(task.id)
            actual = remote_calls[first:]
            checks = {'completed': current.status == 'SUCCEEDED',
                      'exact_result': case['expected_result'] in current.result,
                      'exact_remote_call': actual == [{'tool': case['tool'], 'entity_id': case['entity_id']}],
                      'schema_loaded': mode == 'FULL' or any(c['name'] == 'mcp_load' and c['result'] and c['result']['status'] == 'success' for c in calls),
                      'no_other_tools': all(c['name'] in {'mcp_discover', 'mcp_search', 'mcp_load', 'mcp_call'} for c in calls)}
            record = {'case': case['id'], 'mode': mode, 'checks': checks, 'passed': all(checks.values()),
                      'model': settings.provider.model, 'seconds': round(time.monotonic()-start, 3),
                      'model_requests': current.checkpoint.get('model_requests'), 'usage': current.checkpoint.get('usage'),
                      'answer': current.result, 'error': current.error, 'remote_calls': actual}
            (target / 'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            # Private catalogs contain only synthetic fixture data. Never export provider config or databases.
            (target / 'calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
            (target / 'requests.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding='utf-8')
            records.append(record)
            print(json.dumps(record), flush=True)
            (args.output / 'summary.json').write_text(json.dumps({'fixture_sha256': hashlib.sha256(args.fixture.read_bytes()).hexdigest(), 'planned': 10, 'records': records}, indent=2))
    finally:
        server.should_exit = True
        await asyncio.to_thread(thread.join, 5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
