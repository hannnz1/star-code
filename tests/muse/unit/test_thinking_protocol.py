import json

import httpx
import pytest
from pydantic import SecretStr
from test_provider_stream import sse

from muse.config import ProviderSettings
from muse.providers.compatible import HttpModelProvider, ProviderError


async def test_responses_summary_in_completed_item_without_deltas():
    def handler(request):
        return httpx.Response(200, content=sse([{'type': 'response.completed', 'response': {'output': [
            {'type': 'reasoning', 'id': 'r', 'encrypted_content': 'OPAQUE',
             'summary': [{'type': 'summary_text', 'text': 'Checked dependencies'}]}]}}]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpModelProvider(settings('openai-responses', 'openai-reasoning'), client=client)
        events = [event async for event in provider.stream([{'role': 'user', 'content': 'Inspect'}], [])]
    assert ''.join(event.text for event in events if event.type == 'summary') == 'Checked dependencies'


def settings(protocol, capability, thinking=True, **options):
    return ProviderSettings(base_url='https://fixture.invalid/v1', api_key=SecretStr('fixture-key'),
                            model='preserve-selected-model', protocol=protocol, thinking=thinking,
                            thinking_capability=capability, **options)


@pytest.mark.parametrize('protocol,capability', [('openai-responses', 'openai-reasoning'),
    ('openai-compat', 'openai-reasoning'), ('anthropic', 'anthropic-manual'), ('anthropic', 'anthropic-adaptive')])
@pytest.mark.parametrize('enabled', [False, True])
async def test_thinking_payload_uses_declared_capability(protocol, capability, enabled):
    received = []
    def handler(request):
        received.append(json.loads(request.content))
        if protocol == 'openai-responses':
            data = sse([{'type': 'response.completed', 'response': {'output': []}}])
        elif protocol == 'openai-compat':
            data = sse([{'choices': [{'finish_reason': 'stop', 'delta': {}}]}]) + b'data: [DONE]\n\n'
        else:
            data = sse([{'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}}, {'type': 'message_stop'}])
        return httpx.Response(200, content=data)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        instance = HttpModelProvider(settings(protocol, capability, enabled), client=client)
        events = [event async for event in instance.stream([{'role': 'user', 'content': 'Inspect'}], [])]
    payload = received[0]
    assert payload['model'] == 'preserve-selected-model'
    if not enabled:
        assert not any(key in payload for key in ['reasoning', 'reasoning_effort', 'thinking'])
    elif protocol == 'openai-responses':
        assert payload['reasoning'] == {'effort': 'medium', 'summary': 'auto'}
        assert payload['include'] == ['reasoning.encrypted_content']
    elif protocol == 'openai-compat':
        assert payload['reasoning_effort'] == 'medium'
    else:
        assert payload['thinking']['type'] == ('enabled' if capability == 'anthropic-manual' else 'adaptive')
    if enabled:
        assert any(event.type == 'summary' and not event.text for event in events)


@pytest.mark.parametrize('capability,output', [('unsupported', 8192), ('anthropic-manual', 1024)])
async def test_unsupported_or_insufficient_thinking_budget_fails_before_network(capability, output):
    requests = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: requests.append(request))) as client:
        instance = HttpModelProvider(settings('anthropic', capability, max_output_tokens=output), client=client)
        with pytest.raises(ProviderError, match='UNSUPPORTED_THINKING|THINKING_BUDGET'):
            _ = [event async for event in instance.stream([], [])]
    assert requests == []


async def test_responses_summary_and_encrypted_state_are_replayed_without_duplication():
    requests = []
    reasoning = {'id': 'r1', 'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': 'Checking inputs'}],
                 'encrypted_content': 'OPAQUE_FIXTURE'}
    call = {'type': 'function_call', 'call_id': 'read', 'name': 'read_file', 'arguments': '{"path":"a.txt"}'}
    def handler(request):
        requests.append(json.loads(request.content))
        events = [{'type': 'response.reasoning_summary_text.delta', 'delta': 'Checking inputs'},
                  {'type': 'response.completed', 'response': {'output': [reasoning, call], 'usage': {'input_tokens': 2, 'output_tokens': 4}}}]
        return httpx.Response(200, content=sse(events))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        instance = HttpModelProvider(settings('openai-responses', 'openai-reasoning'), client=client)
        first = [event async for event in instance.stream([], [])]
        state = next(event.protocol_state for event in first if event.type == 'protocol_state')
        messages = [{'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'read', 'name': 'read_file', 'arguments': {'path': 'a.txt'}}], '_protocol_state': state},
                    {'role': 'tool', 'tool_call_id': 'read', 'content': 'text'}]
        _ = [event async for event in instance.stream(messages, [])]
    assert next(event.text for event in first if event.type == 'summary') == 'Checking inputs'
    assert requests[1]['input'] == [reasoning, call, {'type': 'function_call_output', 'call_id': 'read', 'output': 'text'}]


async def test_anthropic_signed_blocks_preserve_order_and_exact_signature():
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        events = [
            {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': '', 'signature': ''}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': 'Check input'}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'signature_delta', 'signature': 'EXACT_'}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'signature_delta', 'signature': 'SIGNATURE'}},
            {'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'redacted_thinking', 'data': 'OPAQUE_BLOCK'}},
            {'type': 'content_block_start', 'index': 2, 'content_block': {'type': 'tool_use', 'id': 'read', 'name': 'read_file', 'input': {}}},
            {'type': 'content_block_delta', 'index': 2, 'delta': {'type': 'input_json_delta', 'partial_json': '{"path":"a.txt"}'}},
            {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use'}, 'usage': {'output_tokens': 4}},
            {'type': 'message_stop'},
        ]
        return httpx.Response(200, content=sse(events))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        instance = HttpModelProvider(settings('anthropic', 'anthropic-manual'), client=client)
        events = [event async for event in instance.stream([], [])]
        state = next(event.protocol_state for event in events if event.type == 'protocol_state')
        messages = [{'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'read', 'name': 'read_file', 'arguments': {'path': 'a.txt'}}], '_protocol_state': state},
                    {'role': 'tool', 'tool_call_id': 'read', 'content': 'data'}]
        _ = [event async for event in instance.stream(messages, [])]
    assert requests[1]['messages'][0]['content'] == [
        {'type': 'thinking', 'thinking': 'Check input', 'signature': 'EXACT_SIGNATURE'},
        {'type': 'redacted_thinking', 'data': 'OPAQUE_BLOCK'},
        {'type': 'tool_use', 'id': 'read', 'name': 'read_file', 'input': {'path': 'a.txt'}},
    ]
    assert sum(event.type == 'call' for event in events) == 1


async def test_worker_restart_replays_opaque_state_without_public_leak(tmp_path):
    from test_agent_loop import ScriptedProvider, runtime

    from muse.agent.loop import AgentRunner
    from muse.main import public_task
    from muse.tasks.worker import Worker
    repo, task, original = runtime(tmp_path, ScriptedProvider([]))
    requests = []
    reasoning = {'type': 'reasoning', 'id': 'r', 'encrypted_content': 'PRIVATE_OPAQUE_FIXTURE', 'summary': []}
    call = {'type': 'function_call', 'call_id': 'question', 'name': 'ask_user', 'arguments': '{"question":"Which folder?"}'}
    def handler(request):
        requests.append(json.loads(request.content))
        output = [reasoning, call] if len(requests) == 1 else []
        events = [] if output else [{'type': 'response.output_text.delta', 'delta': 'Done'}]
        events.append({'type': 'response.completed', 'response': {'output': output}})
        return httpx.Response(200, content=sse(events))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpModelProvider(settings('openai-responses', 'openai-reasoning'), client=client)
        await Worker(original.settings, repo, AgentRunner(provider)).run_once()
        waiting = repo.get(task.id)
        assert waiting.status == 'WAITING_INPUT' and waiting.checkpoint['provider_states']
        assert 'PRIVATE_OPAQUE_FIXTURE' not in json.dumps(public_task(waiting))
        assert 'PRIVATE_OPAQUE_FIXTURE' not in json.dumps(repo.events(task.id))
        repo.control(task.id, 'input', expected_revision=waiting.revision, content='src')
        await Worker(original.settings, repo, AgentRunner(provider)).run_once()
    assert repo.get(task.id).status == 'SUCCEEDED'
    assert reasoning in requests[1]['input']
    assert '未返回摘要' in json.dumps(repo.events(task.id), ensure_ascii=False)
