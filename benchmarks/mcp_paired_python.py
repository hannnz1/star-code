"""Experiment-only FULL exposure; production execution and approval stay unchanged."""
import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from muse.tools.registry import ToolRegistry

from .mcp_selection_python import run as selection_run


class FullCatalogRegistry(ToolRegistry):
    fixture_tools = None

    def __init__(self, context):
        super().__init__(context)
        if self.fixture_tools is not None:
            self.context.cp.setdefault('mcp_catalogs', {})['fixture'] = {
                'fingerprint': self.mcp.fingerprint('fixture'),
                'tools': {tool['name']: {'description': tool['description'], 'schema': tool['inputSchema']}
                          for tool in self.fixture_tools},
            }

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


def paired_report(records, case_ids):
    if len(case_ids) != len(set(case_ids)):
        raise ValueError('Frozen MCP case ids must be unique')
    expected = Counter((mode, case) for mode in ('FULL', 'LAZY') for case in case_ids)
    actual = Counter((record['mode'], record['case']) for record in records)
    return {'planned': sum(expected.values()), 'records': records,
            'passed': actual == expected and all(record['passed'] for record in records)}


def mode_sequence(order):
    if order == 'FULL_LAZY':
        return [('FULL', FullCatalogRegistry), ('LAZY', ToolRegistry)]
    if order == 'LAZY_FULL':
        return [('LAZY', ToolRegistry), ('FULL', FullCatalogRegistry)]
    raise ValueError(f'Unknown MCP mode order: {order}')


async def run(args):
    import tiktoken
    encoding = tiktoken.get_encoding('o200k_base')
    fixture = json.loads(args.fixture.read_text(encoding='utf-8'))
    case_ids = [task['id'] for task in fixture['tasks']]
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    for mode, registry in mode_sequence(args.mode_order):
        directory = args.output / mode.lower()
        FullCatalogRegistry.fixture_tools = fixture['tools'] if mode == 'FULL' else None
        try:
            await selection_run(SimpleNamespace(fixture=args.fixture, config=args.config, output=directory), registry, mode)
        finally:
            FullCatalogRegistry.fixture_tools = None
        summary = json.loads((directory / 'summary.json').read_text())
        for record in summary['records']:
            requests = json.loads((directory / record['case'] / 'requests.json').read_text(encoding='utf-8'))
            schemas = [len(encoding.encode(json.dumps(item['tools'], ensure_ascii=False, separators=(',', ':')))) for item in requests]
            record['schema_tokens_each_request'] = schemas
            record['cumulative_schema_tokens'] = sum(schemas)
            record['initial_schema_tokens'] = schemas[0] if schemas else None
            record['cost'] = None
            records.append(record)
        (args.output / 'summary.json').write_text(json.dumps({**paired_report(records, case_ids),
            'order': args.mode_order,
            'tokenizer': 'tiktoken/o200k_base; compact JSON tool definitions; actual server usage reported separately',
            'old_67_20_percent': 'NOT_COMPARABLE: original copied-six-builtins fixture differs'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('fixture', 'config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--mode-order', choices=('FULL_LAZY', 'LAZY_FULL'), default='FULL_LAZY')
    asyncio.run(run(parser.parse_args()))
