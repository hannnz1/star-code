"""Estimate MCP-only schema costs with the same tokenizer version as StarCode.

Install optional benchmark dependency: tiktoken==0.12.0.
Input is one synthetic selection case's calls.json; no provider call is made.
"""
import argparse
import asyncio
import json
from pathlib import Path

import tiktoken

from benchmarks.legacy_metrics_audit import context
from muse.contracts import ToolResult
from muse.tools.registry import ToolRegistry


async def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    config = args.output / 'synthetic.yaml'
    config.write_text('mcp_servers:\n  - name: fixture\n    command: never-executed\n')
    ctx = context(args.output / 'runtime', config)
    registry = ToolRegistry(ctx)
    calls = json.loads(args.calls.read_text(encoding='utf-8'))
    discovery = next(c['result'] for c in calls if c['name'] == 'mcp_discover' and c['result'])
    discovery['metadata']['mcp_fingerprint'] = registry.mcp.fingerprint('fixture')
    registry.mcp.restore(ToolResult(**discovery))
    def wire():
        return [{'type': 'function', 'name': d.name, 'description': d.description,
                 'parameters': d.parameters, 'strict': False} for d in registry.definitions() if d.name.startswith('mcp_')]
    encoding = tiktoken.get_encoding('o200k_base')
    def size(value):
        return len(encoding.encode(json.dumps(value, ensure_ascii=False, separators=(',', ':'))))
    full = [{'type': 'function', 'name': name, 'description': value['description'],
             'parameters': value['schema'], 'strict': False} for name, value in discovery['metadata']['mcp_catalog'].items()]
    initial = size(wire())
    loaded = await registry.mcp.load({'server': 'fixture', 'tools': ['orders_get_status']}, 'probe')
    registry.mcp.restore(loaded)
    result = {'tokenizer': f'tiktoken {tiktoken.__version__} o200k_base', 'full_100_schema_tokens': size(full),
              'lazy_initial_schema_tokens': initial, 'one_active_schema_tokens': size(wire()),
              'discovery_index_content_tokens': size(json.loads(discovery['content'])),
              'initial_schema_reduction_percent': round(100 * (1 - initial / size(full)), 2),
              'note': 'MCP-only compact JSON; shared tools/messages excluded. Uses original selection fixture served by FastMCP, not original Java copied-builtins schema fixture. Index costs occur later. No total-bill or paired real-model FULL saving claimed.'}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--calls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
