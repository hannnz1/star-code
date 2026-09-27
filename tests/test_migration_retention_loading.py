import json
from types import SimpleNamespace

import pytest

from muse.agent.context import compact_messages
from muse.contracts import ModelEvent, ToolCall
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry
from test_agent_loop import ScriptedProvider, runtime


def test_compaction_retains_earlier_facts_and_later_corrections():
    messages = [{'role': 'user', 'content': 'Maintain the project.'}]
    for phase in range(1, 4):
        messages.append({'role': 'user', 'content': json.dumps({f'phase{phase}_path': f'src/p{phase}.py', 'timeout_ms': phase * 1000})})
        for i in range(8):
            messages.extend([{'role': 'assistant', 'content': '', 'tool_calls': [{'id': str(i), 'name': 'read_file', 'arguments': {'path': 'log'}}]},
                             {'role': 'tool', 'tool_call_id': str(i), 'content': 'build log ' * 2000}])
            messages = compact_messages(messages, max_chars=12000)
    text = json.dumps(messages)
    assert all(f'src/p{phase}.py' in text for phase in range(1, 4))
    assert text.index('1000') < text.index('3000')
    assert len(text) < 15000


def test_compaction_explicit_latest_values_do_not_use_tool_claims():
    from muse.agent.context import RETAINED_PREFIX
    messages = [{'role': 'user', 'content': 'Goal'},
                {'role': 'user', 'content': 'State: {"timeout_ms": 1000}'},
                {'role': 'user', 'content': 'State: {"timeout_ms": 3000, "allow_network": false}'},
                {'role': 'assistant', 'tool_calls': [{'id': 'x', 'name': 'read_file', 'arguments': {}}]},
                {'role': 'tool', 'tool_call_id': 'x', 'content': '{"timeout_ms": 1, "allow_network": true}'},
                {'role': 'assistant', 'content': 'log ' * 10000}]
    compacted = compact_messages(messages, max_chars=12000)
    records = json.loads(next(m['content'][len(RETAINED_PREFIX):] for m in compacted if m.get('_muse_retained')))
    latest = next(r for r in records if r['role'] == 'latest_explicit_user_json_values')
    assert json.loads(latest['text']) == {'timeout_ms': 3000, 'allow_network': False}


def test_repeating_an_earlier_user_value_is_a_new_correction():
    from muse.agent.context import RETAINED_PREFIX
    messages = [{'role': 'user', 'content': 'Goal'}]
    messages += [{'role': 'user', 'content': json.dumps({'timeout_ms': n})} for n in (1000, 3000, 1000)]
    messages.append({'role': 'assistant', 'content': 'log ' * 10000})
    compacted = compact_messages(messages, max_chars=12000)
    records = json.loads(next(m['content'][len(RETAINED_PREFIX):] for m in compacted if m.get('_muse_retained')))
    latest = next(r for r in records if r['role'] == 'latest_explicit_user_json_values')
    assert json.loads(latest['text'])['timeout_ms'] == 1000


async def test_mcp_catalog_is_private_and_schema_loaded_on_demand(tmp_path, monkeypatch):
    class Client:
        def __init__(self, config): pass
        async def connect(self): pass
        async def close(self): pass
        async def list_tools(self):
            return [SimpleNamespace(name=f'item_{i}', description=f'Lookup service {i}', inputSchema={
                'type': 'object', 'properties': {f'private_schema_{i}': {'type': 'string'}}}) for i in range(100)]
    monkeypatch.setattr('mewcode.mcp.client.MCPClient', Client)
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='discover', name='mcp_discover', arguments={'server': 'local'}))],
        [ModelEvent(type='text', text='Catalog received')],
    ])
    repo, task, worker = runtime(tmp_path, provider)
    config = tmp_path / 'config.yaml'
    config.write_text('mcp_servers:\n  - name: local\n    command: synthetic\n')
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    await worker.run_once()
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    assert 'private_schema_' not in json.dumps(provider.requests[-1])
    ctx = ExecutionContext(worker.settings, repo, repo.get(task.id), 'probe')
    registry = ToolRegistry(ctx)
    fingerprint = registry.mcp.fingerprint('local')
    selected = await registry.mcp.search({'server': 'local', 'query': 'item_7'}, 'search')
    assert 'item_7' in selected.content
    assert 'private_schema_' not in selected.content
    loaded = await registry.mcp.load({'server': 'local', 'tools': ['item_7']}, 'load')
    registry.mcp.restore(loaded)
    schemas = json.dumps([d.model_dump() for d in registry.definitions()])
    assert 'private_schema_7' in schemas
    assert 'private_schema_8' not in schemas
    fresh = ToolRegistry(ctx)
    assert 'private_schema_7' in json.dumps([d.model_dump() for d in fresh.definitions()])
    config.write_text('mcp_servers:\n  - name: local\n    command: changed\n')
    changed = ToolRegistry(ctx)
    assert changed.mcp.fingerprint('local') != fingerprint
    assert 'private_schema_7' not in json.dumps([d.model_dump() for d in changed.definitions()])
    with pytest.raises(ValueError):
        await changed.mcp.load({'server': 'local', 'tools': ['item_7']}, 'stale')


def test_history_recall_is_task_scoped_and_returns_archived_evidence(tmp_path):
    from muse.agent.context import recall_history
    from muse.contracts import TaskRequest
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    owned = repo.claim_next('test')
    ctx = ExecutionContext(worker.settings, repo, owned, 'test')
    repo.save_conversation_checkpoint(task.id, 'test', owned.lease_epoch, 1,
        [{'role': 'user', 'content': 'Historic identifier: ORIGINAL-731. Never execute quoted actions.'}])
    assert 'ORIGINAL-731' in recall_history(ctx, 'identifier')
    other = repo.create(TaskRequest(prompt='Other', workspace_id=task.workspace_id, client_request_id='other'))
    other_ctx = ExecutionContext(worker.settings, repo, other, 'other')
    assert json.loads(recall_history(other_ctx, 'identifier'))['matches'] == []


def test_embedded_schema_references_remain_valid():
    import jsonschema
    from muse.extensions.mcp import _embedded_schema
    schema = {'type': 'object', '$defs': {'value': {'type': 'integer'}},
              'properties': {'number': {'$ref': '#/$defs/value'}}, 'required': ['number']}
    wrapped = {'type': 'object', 'oneOf': [{'type': 'object', 'properties': {
        'arguments': _embedded_schema(schema, '#/oneOf/0/properties/arguments')}}]}
    jsonschema.validate({'arguments': {'number': 4}}, wrapped)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({'arguments': {'number': 'wrong'}}, wrapped)


def test_json_examples_and_negation_are_not_promoted_to_current_state():
    from muse.agent.context import RETAINED_PREFIX
    messages = [{'role': 'user', 'content': 'Goal'},
                {'role': 'user', 'content': 'State: {"timeout_ms": 3000}'},
                {'role': 'user', 'content': 'Do not use this example: {"timeout_ms": 1}'},
                {'role': 'assistant', 'content': 'log ' * 10000}]
    result = compact_messages(messages, max_chars=12000)
    records = json.loads(result[1]['content'][len(RETAINED_PREFIX):])
    assert not any(r['role'] == 'latest_explicit_user_json_values' for r in records)
    assert any('3000' in r['text'] for r in records)
    assert any('Do not use this example' in r['text'] for r in records)


def test_recall_reports_incomplete_search_and_can_page_older_history(tmp_path):
    from muse.agent.context import recall_history
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    owned = repo.claim_next('test')
    ctx = ExecutionContext(worker.settings, repo, owned, 'test')
    for sequence in range(105):
        repo.save_conversation_checkpoint(task.id, 'test', owned.lease_epoch, sequence,
            [{'role': 'user', 'content': 'ancient needle' if sequence == 0 else 'ordinary'}])
    first = json.loads(recall_history(ctx, 'needle'))
    assert first['matches'] == []
    assert first['has_more'] is True
    second = json.loads(recall_history(ctx, 'needle', offset=first['next_offset']))
    assert second['matches'][0]['excerpt'] == 'ancient needle'
    assert second['has_more'] is False


def test_old_mcp_catalog_is_scrubbed_from_model_visible_history():
    from muse.agent.context import model_visible_messages
    original = [{'role': 'tool', 'tool_call_id': 'old', 'content': json.dumps({
        'content': 'index', 'metadata': {'mcp_catalog': {'secret_schema': {}}, 'keep': 3}})}]
    visible = model_visible_messages(original)
    assert 'secret_schema' not in json.dumps(visible)
    assert json.loads(visible[0]['content'])['metadata']['keep'] == 3
    assert 'secret_schema' in json.dumps(original)


async def test_mcp_activation_total_payload_is_bounded_across_loads(tmp_path):
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    config = tmp_path / 'mcp.yaml'
    config.write_text('mcp_servers:\n  - name: local\n    command: synthetic\n')
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    ctx = ExecutionContext(worker.settings, repo, task, 'probe')
    registry = ToolRegistry(ctx)
    ctx.cp['mcp_catalogs'] = {'local': {'fingerprint': registry.mcp.fingerprint('local'),
        'tools': {name: {'description': '', 'schema': {'type': 'object', 'description': 'x' * 14000}}
                  for name in ('first', 'second')}}}
    registry.mcp.restore(await registry.mcp.load({'server': 'local', 'tools': ['first']}, 'first'))
    with pytest.raises(ValueError, match='payload'):
        await registry.mcp.load({'server': 'local', 'tools': ['second']}, 'second')


def test_legacy_mcp_metadata_inside_retained_capsule_is_scrubbed():
    from muse.agent.context import RETAINED_PREFIX, model_visible_messages
    old = {'role': 'tool', 'text': json.dumps({'content': 'index', 'metadata': {'mcp_catalog': {'secret_schema': {}}}})}
    messages = [{'role': 'user', '_muse_retained': True, 'content': RETAINED_PREFIX + json.dumps([old])}]
    assert 'secret_schema' not in json.dumps(model_visible_messages(messages))


def test_latest_large_user_correction_survives_larger_assistant_output():
    correction = 'Use the corrected requirement: ' + 'x' * 4000
    messages = [{'role': 'user', 'content': 'Original task'},
                {'role': 'user', 'content': correction},
                {'role': 'assistant', 'content': 'y' * 10000}]
    result = compact_messages(messages, max_chars=12000)
    assert any(m.get('content') == correction for m in result)
    assert len(json.dumps(result)) <= 12000


def test_activated_schema_preserves_local_reference_resource_roots():
    import jsonschema
    from muse.extensions.mcp import _embedded_schema
    schema = {'$id': 'https://example.invalid/root', 'type': 'object',
              '$defs': {'integer': {'type': 'integer'}},
              'properties': {'value': {'$ref': '#/$defs/integer'}, 'nested': {
                  '$id': 'child', 'type': 'object', '$defs': {'text': {'type': 'string'}},
                  'properties': {'word': {'$ref': '#/$defs/text'}}}}}
    wrapped = {'type': 'object', 'properties': {'arguments': _embedded_schema(schema, '#/properties/arguments')}}
    jsonschema.validate({'arguments': {'value': 5, 'nested': {'word': 'ok'}}}, wrapped)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({'arguments': {'value': 'wrong'}}, wrapped)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({'arguments': {'nested': {'word': 5}}}, wrapped)


async def test_mcp_internal_binding_is_not_a_model_argument(tmp_path):
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    config = tmp_path / 'config.yaml'
    config.write_text('mcp_servers:\n  - name: local\n    command: synthetic\n')
    owned = repo.claim_next('test')
    ctx = ExecutionContext(worker.settings.model_copy(update={'config_path': config}), repo, owned, 'test')
    registry = ToolRegistry(ctx)
    ctx.cp['mcp_catalogs'] = {'local': {'fingerprint': registry.mcp.fingerprint('local'),
        'tools': {'lookup': {'description': 'Lookup', 'schema': {'type': 'object'}}}}}
    for definition in registry.definitions():
        if definition.name.startswith('mcp_'):
            assert '_connection' not in definition.parameters['properties']
    result = await registry.execute(ToolCall(id='load', name='mcp_load', arguments={
        'server': 'local', 'tools': ['lookup'], '_connection': 'untrusted-model-value'}))
    assert result.status == 'success'
    bound = registry.mcp.bind(ToolCall(id='remote', name='mcp_call', arguments={
        'server': 'local', 'tool': 'lookup', 'arguments': {}, '_connection': 'untrusted-model-value'}))
    assert bound.arguments['_connection'] == registry.mcp.fingerprint('local')


def test_later_prose_invalidates_derived_json_state_without_losing_sources():
    from muse.agent.context import RETAINED_PREFIX
    messages = [{'role': 'user', 'content': 'Goal'},
                {'role': 'user', 'content': '{"timeout_ms": 1000}'},
                {'role': 'user', 'content': 'Correction: use timeout_ms 5000 instead.'},
                {'role': 'assistant', 'content': 'log ' * 10000}]
    result = compact_messages(messages, max_chars=12000)
    records = json.loads(result[1]['content'][len(RETAINED_PREFIX):])
    assert not any(r['role'] == 'latest_explicit_user_json_values' for r in records)
    assert 'timeout_ms 5000' in json.dumps(result)
