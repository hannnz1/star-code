"""Private protocol replay attached only to ephemeral transport messages."""
import json
import uuid

MAX_PROTOCOL_BYTES = 16 * 1024 * 1024


def attach_states(messages, checkpoint):
    result = []
    for message in messages:
        message = dict(message)
        marker = message.get('_muse_turn_id')
        if marker:
            state = checkpoint.get('provider_states', {}).get(marker)
            if state is None:
                raise ValueError('Required private protocol state is unavailable; start a new task')
            message['_protocol_state'] = state
        result.append(message)
    return result


def store_state(checkpoint, message, state):
    if state is None:
        return
    states = dict(checkpoint.get('provider_states', {}))
    marker = uuid.uuid4().hex
    states[marker] = state
    if len(json.dumps(states, ensure_ascii=False).encode('utf-8')) > MAX_PROTOCOL_BYTES:
        raise ValueError('Private protocol state exceeds its storage budget; no new tools dispatched')
    message['_muse_turn_id'] = marker
    checkpoint['provider_states'] = states
