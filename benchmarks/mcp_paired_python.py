"""Experiment-only FULL exposure; production execution and approval stay unchanged."""
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from muse.tools.registry import ToolRegistry

from .mcp_selection_python import run as selection_run


class FullCatalogRegistry(ToolRegistry):
    def definitions(self):
        cp = self.context.cp
        old = cp.get('mcp_active')
        cp['mcp_active'] = {server: {'fingerprint': record['fingerprint'], 'tools': list(record['tools'])}
                            for server, record in cp.get('mcp_catalogs', {}).items()}
        try:
            definitions = super().definitions()
            return [d.model_copy(update={'description': 'Call a discovered MCP tool using its exact exposed schema. Separate approval is required.'})
                    if d.name == 'mcp_call' else d for d in definitions]
        finally:
            if old is None:
                cp.pop('mcp_active', None)
            else:
                cp['mcp_active'] = old


async def run(args):
    import tiktoken
    encoding = tiktoken.get_encoding('o200k_base')
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    # Fixed order registered before requests; all ten questions in each mode.
    for mode, registry in [('FULL', FullCatalogRegistry), ('LAZY', ToolRegistry)]:
        directory = args.output / mode.lower()
        await selection_run(SimpleNamespace(fixture=args.fixture, config=args.config, output=directory), registry, mode)
        summary = json.loads((directory / 'summary.json').read_text())
        for record in summary['records']:
            requests = json.loads((directory / record['case'] / 'requests.json').read_text(encoding='utf-8'))
            schemas = [len(encoding.encode(json.dumps(item['tools'], ensure_ascii=False, separators=(',', ':')))) for item in requests]
            record['schema_tokens_each_request'] = schemas
            record['cumulative_schema_tokens'] = sum(schemas)
            record['initial_schema_tokens'] = schemas[0] if schemas else None
            record['cost'] = None
            records.append(record)
        (args.output / 'summary.json').write_text(json.dumps({'planned': 20, 'records': records,
            'order': 'FULL ten original tasks, then LAZY ten original tasks',
            'tokenizer': 'tiktoken/o200k_base; compact JSON tool definitions; actual server usage reported separately',
            'old_67_20_percent': 'NOT_COMPARABLE: original copied-six-builtins fixture differs',
            'passed': len(records) == 20 and all(r['passed'] for r in records)}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('fixture', 'config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
