import hashlib
import hmac
import json
import re
from dataclasses import asdict

import httpx
import yaml

from mewcode.hooks.loader import load_hooks
from mewcode.hooks.models import HookContext
from muse.contracts import ToolCall, ToolDefinition, ToolResult
from muse.tools.shell import run_command


class DurableHooks:
    def __init__(self, registry):
        self.registry, self.ctx = registry, registry.context
        path = self.ctx.settings.config_path
        raw = (yaml.safe_load(path.read_text(encoding='utf-8-sig')) or {}).get('hooks', []) if path else []
        self.hooks = load_hooks(raw)
        for hook in self.hooks:
            for key, value in hook.action.headers.items():
                if re.search(r'key|token|secret|password|authorization|cookie|credential', key, re.IGNORECASE) and value:
                    self.ctx.extension_secrets.add(value)
                    if value.lower().startswith('bearer '):
                        self.ctx.extension_secrets.add(value[7:])
        self.signatures = {}
        for index, hook in enumerate(self.hooks):
            name = f'__hook_{index}'
            signature = hmac.new(self.ctx.settings.access_token.get_secret_value().encode(),
                json.dumps(raw[index], sort_keys=True, ensure_ascii=False).encode(), hashlib.sha256).hexdigest()
            self.signatures[name] = signature
            async def handler(args, call_id, hook=hook, name=name):
                return await self.action(hook, name, args, call_id)
            registry.register(ToolDefinition(name=name, description=f'Configured hook: {hook.id} ({hook.event}, {hook.action.type})',
                risk='read' if hook.action.type == 'prompt' else 'execute', parameters={
                    'type': 'object', 'properties': {'payload': {'type': 'object'}, '_source': {'const': signature},
                        'action_preview': {'type': 'object'}},
                    'required': ['payload', '_source', 'action_preview'], 'additionalProperties': False}), handler)

    async def emit(self, event, identity, call=None, result=None):
        if self.ctx.cp.get('commerce'):
            return None  # Commerce roles never inherit executable project Hooks.
        payload = HookContext(event_name=event, tool_name=call.name if call else '', tool_args=call.arguments if call else {},
                              file_path=str(call.arguments.get('path', '')) if call else '', message=result.content if result else '',
                              error=self.ctx.cp.get('pending_failure', '') if event == 'error' else '')
        for index, hook in enumerate(self.hooks):
            name = f'__hook_{index}'
            if hook.event != event or (hook.condition and not hook.condition.evaluate(payload)):
                continue
            once_key = name + ':' + self.signatures[name]
            if once_key in self.ctx.cp.get('suppressed_hooks', []):
                continue
            if hook.once and once_key in self.ctx.cp.get('hooks_once', []):
                continue
            call_id = 'hook:' + hashlib.sha256(f'{name}:{event}:{identity}'.encode()).hexdigest()
            preview = {'type': hook.action.type, 'timeout_seconds': min(hook.action.timeout, 300)}
            if hook.async_exec:
                preview['async'] = True
            fields = {'command': ('command',), 'http': ('url', 'method', 'body'),
                      'agent': ('prompt',), 'prompt': ('message',)}[hook.action.type]
            preview.update({field: self.ctx.safe(payload.expand(getattr(hook.action, field))) for field in fields})
            action = ToolCall(id=call_id, name=name, arguments={'payload': asdict(payload),
                '_source': self.signatures[name], 'action_preview': preview})
            outcome = await self.registry._execute_core(action, internal=True)
            if event == 'pre_tool_use' and (hook.reject or outcome.status != 'success'):
                return outcome.content or 'Configured hook blocked the tool'
        return None

    async def action(self, hook, name, args, call_id):
        payload = HookContext(**args['payload'])
        action = hook.action
        metadata = {'hook_once_key': name + ':' + args['_source'] if hook.once else '', 'hook_id': hook.id}
        if hook.async_exec and not self.ctx.cp.get('hook_job'):
            job = ToolCall(id=call_id, name=name, arguments=args).model_dump()
            child = self.ctx.repo.spawn_child(self.ctx.task_id, self.ctx.owner, self.ctx.epoch, call_id,
                'Run configured asynchronous Hook: ' + hook.id, capabilities={'hook_job': job})
            metadata['hook_child_id'] = child.id
            return ToolResult(call_id=call_id, content=json.dumps({'child_id': child.id, 'async': True}), metadata=metadata)
        if action.type == 'prompt':
            content = self.ctx.safe(payload.expand(action.message))
            metadata['hook_prompt'] = content
            return ToolResult(call_id=call_id, content=content, metadata=metadata)
        if action.type == 'command':
            result = await run_command(self.ctx, {'command': payload.expand(action.command), 'timeout_seconds': min(action.timeout, 300)}, call_id)
            result.metadata.update(metadata)
            return result
        if action.type == 'agent':
            prompt = self.ctx.safe(payload.expand(action.prompt))
            if not prompt.strip() or len(prompt) > 50000:
                raise ValueError('Invalid Hook agent prompt')
            child = self.ctx.repo.spawn_child(self.ctx.task_id, self.ctx.owner, self.ctx.epoch, call_id, prompt,
                capabilities={'suppressed_hooks': [name + ':' + args['_source']]})
            return ToolResult(call_id=call_id, content=json.dumps({'child_id': child.id}), metadata=metadata)
        if action.type == 'http':
            async def request():
                async with (
                    httpx.AsyncClient(timeout=action.timeout, trust_env=False, follow_redirects=False) as client,
                    client.stream(action.method, payload.expand(action.url),
                        headers={key: payload.expand(value) for key, value in action.headers.items()},
                        content=payload.expand(action.body).encode()) as response,
                ):
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk[:max(0, 65536 - len(data))])
                        if len(data) >= 65536:
                            break
                    return response.status_code, data.decode('utf-8', errors='replace')
            status, content = await self.ctx.controlled(request())
            return ToolResult(call_id=call_id, content=self.ctx.safe(content), status='success' if 200 <= status < 300 else 'error', metadata=metadata)
        raise ValueError('Unsupported Hook action')

    def restore(self, result):
        if result.status != 'success':
            return
        if key := result.metadata.get('hook_once_key'):
            seen = self.ctx.cp.setdefault('hooks_once', [])
            if key not in seen:
                seen.append(key)
        if prompt := result.metadata.get('hook_prompt'):
            self.ctx.cp.setdefault('hook_prompts', {})[result.call_id] = prompt
