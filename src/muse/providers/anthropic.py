"""Anthropic transport using the baseline's message serializer."""
import json

from mewcode.conversation import Message, ToolResultBlock, ToolUseBlock
from mewcode.serialization import build_anthropic_messages
from muse.contracts import ModelEvent


def anthropic_payload(settings, messages, tools):
    system = '\n'.join(m.get('content', '') for m in messages if m['role'] == 'system')
    converted = []
    for message in messages:
        if message['role'] == 'system':
            continue
        if message['role'] == 'tool':
            converted.append(Message(role='user', content='', tool_results=[ToolResultBlock(
                message['tool_call_id'], message.get('content', ''))]))
        else:
            converted.append(Message(role=message['role'], content=message.get('content', ''), tool_uses=[
                ToolUseBlock(call['id'], call['name'], call['arguments']) for call in message.get('tool_calls', [])]))
    payload = {'model': settings.model, 'stream': True, 'max_tokens': settings.max_output_tokens,
               'messages': build_anthropic_messages(converted), 'system': system}
    states = iter(message.get('_protocol_state') for message in messages if message['role'] == 'assistant')
    for message in payload['messages']:
        if message['role'] == 'assistant':
            state = next(states)
            if state and state.get('protocol') == 'anthropic':
                message['content'] = state['items']
    if tools:
        payload['tools'] = [{'name': t.name, 'description': t.description, 'input_schema': t.parameters} for t in tools]
    return payload


async def parse_anthropic(response):
    from muse.providers.compatible import ProviderError, checked_calls, sse_data
    calls, input_tokens, output_tokens = {}, None, None
    blocks = {}
    completed, reason = False, None
    async for data in sse_data(response):
        event = json.loads(data)
        kind = event.get('type')
        if kind == 'message_start':
            usage = event.get('message', {}).get('usage', {})
            value = usage.get('input_tokens')
            if value is not None:
                input_tokens = value + (usage.get('cache_read_input_tokens') or 0) + (usage.get('cache_creation_input_tokens') or 0)
        elif kind == 'content_block_start':
            block = event.get('content_block', {})
            blocks[event['index']] = dict(block)
            if block.get('type') == 'tool_use':
                index = event['index']
                if index in calls:
                    raise ProviderError('Duplicate Anthropic content block')
                calls[index] = {'call_id': block.get('id'), 'name': block.get('name'),
                                'arguments': '', 'initial': block.get('input', {})}
        elif kind == 'content_block_delta':
            delta = event.get('delta', {})
            index = event.get('index')
            block = blocks.get(index)
            if block is None:
                raise ProviderError('Content delta without a content block')
            if delta.get('type') == 'text_delta':
                block['text'] = block.get('text', '') + delta.get('text', '')
                yield ModelEvent(type='text', text=delta.get('text', ''))
            elif delta.get('type') == 'thinking_delta':
                block['thinking'] = block.get('thinking', '') + delta.get('thinking', '')
                yield ModelEvent(type='summary', text=delta.get('thinking', ''))
            elif delta.get('type') == 'signature_delta':
                block['signature'] = block.get('signature', '') + delta.get('signature', '')
            elif delta.get('type') == 'input_json_delta':
                if event.get('index') not in calls:
                    raise ProviderError('Tool delta without a content block')
                calls[event['index']]['arguments'] += delta.get('partial_json', '')
        elif kind == 'message_delta':
            reason = event.get('delta', {}).get('stop_reason')
            output_tokens = event.get('usage', {}).get('output_tokens')
        elif kind == 'message_stop':
            completed = True
            break
        elif kind == 'error':
            raise ProviderError('Anthropic stream reported an error')
    if not completed or reason not in {'end_turn', 'tool_use', 'stop_sequence'}:
        raise ProviderError('Anthropic stream was incomplete or reached its output limit')
    for call in calls.values():
        if not call['arguments']:
            call['arguments'] = json.dumps(call['initial'])
    parsed = checked_calls(list(calls.values()))
    for index, call in calls.items():
        blocks[index]['input'] = json.loads(call['arguments'])
    if any(block.get('type') in {'thinking', 'redacted_thinking'} for block in blocks.values()):
        if any(block.get('type') == 'thinking' and not block.get('signature') for block in blocks.values()):
            raise ProviderError('Thinking block is missing its protocol signature')
        yield ModelEvent(type='protocol_state', protocol_state={'protocol': 'anthropic',
            'items': [blocks[key] for key in sorted(blocks)]})
    for call in parsed:
        yield ModelEvent(type='call', call=call)
    yield ModelEvent(type='usage', usage={'input_tokens': input_tokens, 'output_tokens': output_tokens})
    yield ModelEvent(type='done')
