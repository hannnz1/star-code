import json
import httpx
import pytest
from test_provider_stream import provider, sse


@pytest.mark.parametrize('stop_reason', ['tool_use', 'max_tokens'])
async def test_anthropic_complete_calls_only_and_protocol_headers(stop_reason):
    received = []
    events = [
        {'type': 'message_start', 'message': {'usage': {'input_tokens': 12, 'output_tokens': 0}}},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'tool_use', 'id': 'c1', 'name': 'read_file', 'input': {}}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'input_json_delta', 'partial_json': '{"path":"hello.txt"}'}},
        {'type': 'content_block_stop', 'index': 0},
        {'type': 'message_delta', 'delta': {'stop_reason': stop_reason}, 'usage': {'output_tokens': 5}},
        {'type': 'message_stop'},
    ]
    def handler(request):
        received.append(request)
        return httpx.Response(200, content=sse(events))
    actual = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        try:
            async for event in provider(client, 'anthropic').stream([
                {'role': 'system', 'content': 'system prompt'}, {'role': 'user', 'content': 'Read'}], []):
                actual.append(event)
        except RuntimeError:
            assert stop_reason == 'max_tokens'
    assert str(received[0].url).endswith('/messages')
    assert received[0].headers['x-api-key'] == 'never-log-key'
    body = json.loads(received[0].content)
    assert body['system'] == 'system prompt'
    calls = [event.call for event in actual if event.type == 'call']
    if stop_reason == 'max_tokens':
        assert not calls and not any(e.type == 'done' for e in actual)
    else:
        assert calls[0].arguments == {'path': 'hello.txt'}
        assert next(e.usage for e in actual if e.type == 'usage') == {'input_tokens': 12, 'output_tokens': 5}
