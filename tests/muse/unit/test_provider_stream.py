import importlib.util
import json

import httpx
import pytest
from pydantic import SecretStr

from muse.config import ProviderSettings


def provider(client, protocol="openai-responses"):
    assert importlib.util.find_spec("muse.providers") is not None, "Model adapter is missing"
    from muse.providers.compatible import HttpModelProvider
    return HttpModelProvider(ProviderSettings(base_url="https://model.example/v1", model="fixture",
                              api_key=SecretStr("never-log-key"), protocol=protocol), client=client)


def sse(events):
    return "".join("data: " + json.dumps(event) + "\n\n" for event in events).encode()


async def test_responses_stream_only_emits_complete_calls_and_usage():
    received = []
    events = [
        {"type": "response.output_text.delta", "delta": "Reading"},
        {"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "name": "read_file", "call_id": "c1", "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '{"path":'},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '"README.md"}'},
        {"type": "response.output_item.done", "output_index": 0, "item": {"type": "function_call", "name": "read_file", "call_id": "c1", "arguments": '{"path":"README.md"}'}},
        {"type": "response.completed", "response": {"usage": {"input_tokens": 20, "output_tokens": 10}}},
    ]
    def handler(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, content=sse(events), headers={"content-type": "text/event-stream"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        actual = [event async for event in provider(client).stream([{"role": "user", "content": "Read"}], [])]
    calls = [e.call for e in actual if e.type == "call"]
    assert len(calls) == 1 and calls[0].arguments == {"path": "README.md"}
    assert next(e.usage for e in actual if e.type == "usage")["input_tokens"] == 20
    assert received[0]["model"] == "fixture" and received[0]["store"] is False


async def test_truncated_stream_does_not_yield_executable_call():
    event = {"type": "response.output_item.done", "output_index": 0,
             "item": {"type": "function_call", "name": "write_file", "call_id": "c1", "arguments": '{"path":"x"}'}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=sse([event])))) as client:
        instance = provider(client)
        output = []
        with pytest.raises(RuntimeError, match="incomplete"):
            async for item in instance.stream([], []):
                output.append(item)
        assert not [e for e in output if e.type == "call"]


async def test_invalid_function_json_fails_before_tool_dispatch():
    events = [{"type": "response.output_item.done", "output_index": 0,
               "item": {"type": "function_call", "name": "write_file", "call_id": "c1", "arguments": '{bad'}},
              {"type": "response.completed", "response": {}}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=sse(events)))) as client:
        instance = provider(client)
        with pytest.raises(RuntimeError, match="arguments"):
            _ = [e async for e in instance.stream([], [])]


async def test_tool_results_are_translated_to_responses_input():
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=sse([{"type": "response.completed", "response": {}}]))
    messages = [{"role": "user", "content": "Read"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "read_file", "arguments": {"path": "x"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "hello"}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _ = [e async for e in provider(client).stream(messages, [])]
    assert captured[0]["input"][1]["type"] == "function_call"
    assert captured[0]["input"][2] == {"type": "function_call_output", "call_id": "c1", "output": "hello"}


async def test_compat_stream_groups_multiple_calls_by_index():
    events = [
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "a", "function": {"name": "read_file", "arguments": '{"path":'}}, {"index": 1, "id": "b", "function": {"name": "read_file", "arguments": '{"path":"b"}'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"a"}'}}]}, "finish_reason": "tool_calls"}]},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=sse(events)+b'data: [DONE]\n\n'))) as client:
        output = [e async for e in provider(client, "openai-compat").stream([], [])]
    assert [(e.call.id, e.call.arguments) for e in output if e.type == "call"] == [("a", {"path": "a"}), ("b", {"path": "b"})]


async def test_http_failure_does_not_expose_response_or_key():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="never-log-key"))) as client:
        instance = provider(client)
        with pytest.raises(RuntimeError) as caught:
            _ = [e async for e in instance.stream([], [])]
        assert "401" in str(caught.value)
        assert "never-log-key" not in str(caught.value)
