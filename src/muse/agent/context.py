import json


def compact_messages(messages: list[dict], max_chars: int = 120000) -> list[dict]:
    """Drop complete old turns, retaining the original goal and latest user input.

    Deterministic compaction deliberately does not invent a model-written summary.
    Original events and full tool outputs remain in the task store.
    """
    if len(json.dumps(messages, ensure_ascii=False)) <= max_chars:
        return messages
    groups = []
    for message in messages[1:]:
        if message["role"] == "tool" and groups:
            groups[-1].append(message)
        else:
            groups.append([message])
    kept, size = [], len(json.dumps(messages[0]))
    latest_user = next((m for m in reversed(messages[1:]) if m["role"] == "user"), None)
    for group in reversed(groups):
        amount = len(json.dumps(group, ensure_ascii=False))
        if kept and size + amount > max_chars:
            break
        kept.insert(0, group)
        size += amount
    tail = [message for group in kept for message in group]
    note = {"role": "user", "content": "Older complete turns were compacted. The original goal, recent turns, task budgets, sources, artifacts and pending tool calls are preserved. Full tool outputs remain available through read_offload."}
    if latest_user and latest_user not in tail:
        tail.insert(0, latest_user)
    return [messages[0], note, *tail]
