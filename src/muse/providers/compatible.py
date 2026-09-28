from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from muse.config import ProviderSettings
from muse.contracts import ModelEvent, ToolCall, ToolDefinition


class ProviderError(RuntimeError):
    pass


def failure_code(value):
    known = {'rate_limit_exceeded', 'insufficient_quota', 'invalid_api_key', 'server_error',
             'invalid_prompt', 'context_length_exceeded', 'max_output_tokens', 'content_filter',
             'invalid_request_error', 'model_not_found', 'unsupported_parameter', 'quota_exceeded',
             'billing_hard_limit_reached'}
    return value if isinstance(value, str) and value in known else 'unknown'


def responses_input(messages: list[dict]) -> list[dict]:
    result = []
    for message in messages:
        role = message["role"]
        if role == "tool":
            result.append({"type": "function_call_output", "call_id": message["tool_call_id"], "output": message["content"]})
        else:
            state = message.get('_protocol_state')
            if role == 'assistant' and state and state.get('protocol') == 'openai-responses':
                result.extend(state['items'])
                continue
            if message.get("content"):
                result.append({"role": role, "content": message["content"]})
            for call in message.get("tool_calls", []):
                result.append({"type": "function_call", "call_id": call["id"], "name": call["name"],
                               "arguments": json.dumps(call["arguments"], ensure_ascii=False)})
    return result


def chat_input(messages: list[dict]) -> list[dict]:
    result = []
    for message in messages:
        item = {"role": message["role"], "content": message.get("content", "")}
        if message.get("tool_call_id"):
            item["tool_call_id"] = message["tool_call_id"]
        if message.get("tool_calls"):
            item["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                "name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False),
            }} for c in message["tool_calls"]]
        result.append(item)
    return result


async def sse_data(response: httpx.Response) -> AsyncIterator[str]:
    parts = []
    size = 0
    async for line in response.aiter_lines():
        size += len(line)
        if size > 32 * 1024 * 1024:
            raise ProviderError("Model stream exceeds the response size limit")
        if not line:
            if parts:
                yield "\n".join(parts)
                parts = []
        elif line.startswith("data:"):
            parts.append(line[5:].lstrip())
    if parts:
        yield "\n".join(parts)


def checked_calls(calls: list[dict]) -> list[ToolCall]:
    parsed = []
    ids = set()
    for item in calls:
        try:
            arguments = json.loads(item.get("arguments") or "{}")
            if not isinstance(arguments, dict) or not item.get("name") or not item.get("call_id"):
                raise ValueError()
            if item["call_id"] in ids:
                raise ValueError()
            ids.add(item["call_id"])
            parsed.append(ToolCall(id=item["call_id"], name=item["name"], arguments=arguments))
        except (ValueError, TypeError, KeyError):
            raise ProviderError("Model supplied invalid or duplicate tool arguments") from None
    return parsed


class HttpModelProvider:
    def __init__(self, settings: ProviderSettings, *, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def stream(self, messages: list[dict], tools: list[ToolDefinition]) -> AsyncIterator[ModelEvent]:
        if self.settings.protocol not in {'openai-responses', 'openai-compat', 'anthropic'}:
            raise ProviderError('Unsupported provider protocol')
        from muse.providers.thinking import thinking_parameters
        thinking = thinking_parameters(self.settings)
        own = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.settings.timeout, proxy=self.settings.proxy_url,
                                                trust_env=False, follow_redirects=False)
        response_mode = self.settings.protocol == "openai-responses"
        tool_defs = [{"type": "function", "name": tool.name, "description": tool.description,
                      "parameters": tool.parameters, "strict": False} for tool in tools]
        payload = {"model": self.settings.model, "stream": True}
        if self.settings.protocol == 'anthropic':
            from muse.providers.anthropic import anthropic_payload
            payload = anthropic_payload(self.settings, messages, tools)
            suffix = '/messages'
        elif response_mode:
            payload.update(input=responses_input(messages), store=False, max_output_tokens=self.settings.max_output_tokens)
            if tools:
                payload["tools"] = tool_defs
            suffix = "/responses"
        else:
            payload.update(messages=chat_input(messages), max_completion_tokens=self.settings.max_output_tokens,
                           stream_options={"include_usage": True})
            if tools:
                payload["tools"] = [{"type": "function", "function": {k: v for k, v in tool.items() if k != "type"}} for tool in tool_defs]
            suffix = "/chat/completions"
        payload.update(thinking)
        url = self.settings.base_url if self.settings.base_url.endswith(suffix) else self.settings.base_url + suffix
        headers = {'Content-Type': 'application/json'}
        if self.settings.protocol == 'anthropic':
            headers.update({'x-api-key': self.settings.api_key.get_secret_value(), 'anthropic-version': '2023-06-01'})
        else:
            headers['Authorization'] = f'Bearer {self.settings.api_key.get_secret_value()}'
        try:
            async with client.stream("POST", url, json=payload,
                                     headers=headers) as response:
                if response.status_code >= 300:
                    raise ProviderError(f"Model service returned HTTP {response.status_code}")
                if self.settings.protocol == 'anthropic':
                    from muse.providers.anthropic import parse_anthropic
                    parser = parse_anthropic(response)
                else:
                    parser = self._responses(response) if response_mode else self._chat(response)
                summary_seen = False
                async for item in parser:
                    if item.type == 'summary':
                        if self.settings.thinking and self.settings.thinking_summary:
                            summary_seen |= bool(item.text)
                            yield item
                    elif item.type == 'done':
                        if self.settings.thinking and not summary_seen:
                            yield ModelEvent(type='summary', text='')
                        yield item
                    else:
                        yield item
        except httpx.TimeoutException:
            raise ProviderError("Model request timed out") from None
        except httpx.HTTPError:
            raise ProviderError("Model service connection failed") from None
        except json.JSONDecodeError:
            raise ProviderError("Model stream contained malformed JSON") from None
        finally:
            if own:
                await client.aclose()

    async def _responses(self, response: httpx.Response) -> AsyncIterator[ModelEvent]:
        calls: dict[int, dict] = {}
        complete = False
        usage = None
        output_items = {}
        summary_streamed = False
        async for data in sse_data(response):
            if data == "[DONE]":
                break
            event = json.loads(data)
            kind = event.get("type")
            if kind == "response.output_text.delta":
                yield ModelEvent(type="text", text=event.get("delta", ""))
            elif kind == 'response.reasoning_summary_text.delta':
                summary_streamed = True
                yield ModelEvent(type='summary', text=event.get('delta', ''))
            elif kind == "response.output_item.done":
                item = event.get("item", {})
                output_items[event.get('output_index', len(output_items))] = item
                if item.get("type") == "function_call":
                    calls[event.get("output_index", len(calls))] = item
            elif kind == "response.completed":
                complete = True
                result = event.get("response", {})
                usage = result.get("usage")
                for index, item in enumerate(result.get("output", [])):
                    output_items[index] = item
                    if item.get("type") == "function_call":
                        calls[index] = item
            elif kind in {"response.failed", "response.incomplete", "error"}:
                details = event.get('response') or event
                error = details.get('error') or {}
                incomplete = details.get('incomplete_details') or {}
                code = failure_code(error.get('code') if isinstance(error, dict) else None)
                reason = failure_code(incomplete.get('reason') if isinstance(incomplete, dict) else None)
                raise ProviderError(f'Model response failed or was incomplete (event={kind}, code={code}, reason={reason})')
        if not complete:
            raise ProviderError("Model stream was incomplete; no tools were dispatched")
        parsed = checked_calls([calls[key] for key in sorted(calls)])
        if not summary_streamed:
            for key in sorted(output_items):
                item = output_items[key]
                if item.get('type') == 'reasoning':
                    for part in item.get('summary', []):
                        if part.get('type') == 'summary_text' and isinstance(part.get('text'), str):
                            yield ModelEvent(type='summary', text=part['text'])
        if any(item.get('type') == 'reasoning' for item in output_items.values()):
            yield ModelEvent(type='protocol_state', protocol_state={'protocol': 'openai-responses',
                'items': [output_items[key] for key in sorted(output_items)]})
        for call in parsed:
            yield ModelEvent(type="call", call=call)
        yield ModelEvent(type="usage", usage=usage)
        yield ModelEvent(type="done")

    async def _chat(self, response: httpx.Response) -> AsyncIterator[ModelEvent]:
        calls = {}
        complete = False
        finish_reason = None
        usage = None
        async for data in sse_data(response):
            if data == "[DONE]":
                complete = True
                break
            chunk = json.loads(data)
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices", []):
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta", {})
                if delta.get("content"):
                    yield ModelEvent(type="text", text=delta["content"])
                for part in delta.get("tool_calls", []):
                    item = calls.setdefault(part["index"], {"call_id": "", "name": "", "arguments": ""})
                    if part.get("id"):
                        item["call_id"] = part["id"]
                    function = part.get("function", {})
                    item["name"] += function.get("name", "")
                    item["arguments"] += function.get("arguments", "")
        if not complete or finish_reason not in {"stop", "tool_calls"}:
            raise ProviderError("Model stream was incomplete; no tools were dispatched")
        for call in checked_calls([calls[key] for key in sorted(calls)]):
            yield ModelEvent(type="call", call=call)
        normalized = None if usage is None else {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}
        yield ModelEvent(type="usage", usage=normalized)
        yield ModelEvent(type="done")
