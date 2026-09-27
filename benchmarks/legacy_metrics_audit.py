"""Offline compatibility probes using original StarCode fixtures and MUSE production paths.

This does not claim original real-model scores. Commands are never executed.
"""
import argparse
import asyncio
import hashlib
import json
import statistics
from pathlib import Path
from types import SimpleNamespace

from muse.agent.context import compact_messages
from muse.config import load_settings
from muse.contracts import TaskRequest, ToolCall, ToolResult
from muse.tasks.repository import TaskRepository
from muse.tools.context import ApprovalRequired, ExecutionContext
from muse.tools.registry import ToolRegistry


def context(root, config=None):
    root.mkdir(parents=True)
    settings = load_settings(data_dir=root / 'state', require_provider=False)
    if config:
        settings = settings.model_copy(update={'config_path': config})
    workspace = root / 'workspace'
    workspace.mkdir()
    repo = TaskRepository(settings.data_dir / 'state.sqlite3')
    ws = repo.register_workspace(str(workspace))
    repo.create(TaskRequest(prompt='Synthetic compatibility probe', scenario='coding',
                            workspace_id=ws['id'], client_request_id='audit'))
    task = repo.claim_next('audit')
    return ExecutionContext(settings, repo, task, 'audit')


async def audit(source, output):
    output.mkdir(parents=True, exist_ok=False)
    fixtures = {}
    for name in ('permission-v1/fixture.json', 'long-context-v1/fixture.json',
                 'mcp-lazy-v1/selection-fixture.json'):
        path = source / name
        fixtures[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    permissions = json.loads((source / 'permission-v1/fixture.json').read_text())
    traces = []
    for session in permissions['sessions']:
        ctx = context(output / 'private-runtime' / session['name'])
        registry = ToolRegistry(ctx)
        async def noop(args, call_id):
            return ToolResult(call_id=call_id, content='Policy replay only; not executed')
        # Keep actual schemas, risk classifications, path checks, receipts and approvals.
        # Replace only effect handlers so even an erroneous allow cannot run a command.
        for name, (definition, _) in list(registry.entries.items()):
            registry.entries[name] = (definition, noop)
        decisions = []
        for i, action in enumerate(session['actions']):
            name = 'run_command' if action['tool'] == 'bash' else action['tool']
            args = dict(action['arguments'])
            if name == 'search_text':
                args['pattern'] = args.pop('query')
            call = ToolCall(id=f'action-{i}', name=name, arguments=args)
            prompted = False
            try:
                result = await registry._execute_core(call)
            except ApprovalRequired:
                prompted = True
                approval = next(a for a in ctx.repo.approvals(ctx.task_id) if a['tool_call_id'] == call.id)
                ctx.repo.decide_approval(approval['id'], not action['high_risk'], approval['action_digest'])
                claimed = ctx.repo.claim_next('audit')
                ctx.task = claimed
                ctx.epoch = claimed.lease_epoch
                result = await registry._execute_core(call)
            decisions.append({'tool': action['tool'], 'arguments': action['arguments'],
                              'high_risk': action['high_risk'], 'prompted': prompted,
                              'result': result.status, 'error_code': result.error_code})
        traces.append({'name': session['name'], 'prompts': sum(x['prompted'] for x in decisions),
                       'decisions': decisions})
    all_decisions = [d for t in traces for d in t['decisions']]
    permission_result = {'track': 'offline-production-policy-replay', 'actions': len(all_decisions),
        'median_prompts': statistics.median(t['prompts'] for t in traces),
        'total_prompts': sum(t['prompts'] for t in traces),
        'risky_denied': sum(d['high_risk'] and d['result'] == 'denied' for d in all_decisions),
        'risky_automatically_allowed': sum(d['high_risk'] and d['result'] == 'success' for d in all_decisions),
        'nonrisk_errors': sum(not d['high_risk'] and d['result'] != 'success' for d in all_decisions),
        'note': 'No ALLOW_SESSION mode. Workspace edits are write-risk and need no per-edit approval; commands require per-action approval. Not equivalent to Java permission policy.',
        'traces': traces}
    (output / 'permissions.json').write_text(json.dumps(permission_result, indent=2), encoding='utf-8')

    original = json.loads((source / 'long-context-v1/fixture.json').read_text())
    messages = [{'role': 'user', 'content': original['instructions']}]
    expected = {}
    checkpoints = []
    compactions = 0
    for stage in original['stages']:
        expected.update(stage['facts']); expected.update(stage['current_state'])
        messages.append({'role': 'user', 'content': json.dumps({**stage['facts'], **stage['current_state']})})
        for i, log in enumerate(stage['logs']):
            call_id = f"phase-{stage['phase']}-log-{i}"
            messages.extend([
                {'role': 'assistant', 'content': '', 'tool_calls': [{'id': call_id, 'name': 'read_file', 'arguments': {'path': f'logs/{call_id}.txt'}}]},
                {'role': 'tool', 'tool_call_id': call_id, 'content': log}])
            new = compact_messages(messages)
            compactions += new != messages
            messages = new
        from muse.agent.context import RETAINED_PREFIX
        texts = [m.get('content', '') for m in messages]
        for message in messages:
            if message.get('_muse_retained'):
                texts.extend(r['text'] for r in json.loads(message['content'][len(RETAINED_PREFIX):]))
        serialized = '\n'.join(texts)
        fields = {k: (json.dumps(k) + ': ' + json.dumps(v)) in serialized for k, v in expected.items()}
        # This checks evidence presence, not a model's ability to answer or retrieve archives.
        checkpoints.append({'phase': stage['phase'], 'field_presence': fields,
                            'present': sum(fields.values()), 'total': len(fields)})
        (output / f"context-phase-{stage['phase']}.json").write_text(json.dumps(messages), encoding='utf-8')
    context_result = {'track': 'offline-production-compaction-original-facts-and-logs',
                      'compactions': compactions, 'checkpoints': checkpoints,
                      'note': 'No model, semantic summary, archive-retrieval or 8-hour claim. Historical fact availability in compacted messages only.'}
    (output / 'context.json').write_text(json.dumps(context_result, indent=2), encoding='utf-8')

    fixture = json.loads((source / 'mcp-lazy-v1/selection-fixture.json').read_text())
    config = output / 'synthetic-mcp.yaml'
    config.write_text('mcp_servers:\n  - name: fixture\n    command: never-executed\n')
    ctx = context(output / 'private-runtime' / 'mcp', config)
    registry = ToolRegistry(ctx)
    class Client:
        async def list_tools(self):
            return [SimpleNamespace(**t) for t in fixture['tools']]
    async def connected(server, operation):
        return await operation(Client())
    registry.mcp._connected = connected
    args = {'server': 'fixture', '_connection': registry.mcp.fingerprint('fixture')}
    before = [d.model_dump() for d in registry.definitions() if d.name.startswith('mcp_')]
    result = await registry.mcp.discover(args, 'discover')
    registry.mcp.restore(result)
    after = [d.model_dump() for d in registry.definitions() if d.name.startswith('mcp_')]
    catalog = result.metadata['mcp_catalog']
    mcp_result = {'track': 'offline-production-discovery-with-original-100-tool-fixture',
        'initial_mcp_definitions': [d['name'] for d in before],
        'definitions_unchanged_after_discovery': before == after,
        'discovered_tools': len(catalog), 'returned_schema_count': sum('schema' in t for t in json.loads(result.content).get('tools', [])),
        'discovery_content_chars': len(result.content), 'schema_token_reduction': None,
        'real_model_selection_score': None,
        'note': 'Post-fix discovery returns index only; full schemas persist privately. Transport mocked; real transport tested separately.'}
    (output / 'mcp.json').write_text(json.dumps(mcp_result, indent=2), encoding='utf-8')
    (output / 'fixture-hashes.json').write_text(json.dumps(fixtures, indent=2), encoding='utf-8')
    print(json.dumps({'permission': {k:v for k,v in permission_result.items() if k != 'traces'},
                      'context': context_result, 'mcp': mcp_result}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(audit(args.source.resolve(), args.output.resolve()))
