import json

from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider, runtime


async def test_large_output_offloaded_and_context_keeps_complete_tool_pairs(tmp_path):
    from muse.agent.context import compact_messages
    provider = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="large", name="read_file", arguments={"path": "hello.txt"}))],
        [ModelEvent(type="text", text="Read.")],
    ])
    repo, task, worker = runtime(tmp_path, provider)
    (tmp_path / "project" / "hello.txt").write_text("long text " * 10000)
    await worker.run_once()
    result = json.loads(provider.requests[1][-1]["content"])
    assert len(result["content"]) < 20000
    assert result["metadata"]["offload_id"]
    assert result["metadata"]["truncated"] is True
    assert repo.get(task.id).status == "SUCCEEDED"
    cp = repo.get(task.id).checkpoint
    messages = cp["messages"] + cp["messages"][1:] * 20
    compacted = compact_messages(messages, max_chars=20000)
    assert compacted[0] == messages[0]
    assert len(json.dumps(compacted)) < len(json.dumps(messages))
    active = set()
    for message in compacted:
        active.update(call["id"] for call in message.get("tool_calls", []))
        if message["role"] == "tool":
            assert message["tool_call_id"] in active

