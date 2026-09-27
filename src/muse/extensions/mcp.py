import asyncio
import hashlib
import hmac
import json
import re
from dataclasses import asdict

import jsonschema
import yaml

from mewcode.config import MCPServerConfig, resolve_env_vars
from mewcode.validator import validate_mcp_servers
from muse.contracts import ToolDefinition, ToolResult


def _local_references(value):
    if isinstance(value, dict):
        if '$ref' in value and not str(value['$ref']).startswith('#'):
            raise ValueError('External MCP schema references are unsupported')
        for child in value.values():
            _local_references(child)
    elif isinstance(value, list):
        for child in value:
            _local_references(child)


def _embedded_schema(value, pointer):
    def walk(node, location, scope):
        if isinstance(node, list):
            return [walk(item, location + '/' + str(i), scope) for i, item in enumerate(node)]
        if not isinstance(node, dict):
            return node
        if '$id' in node:
            scope = location
        result = {key: walk(item, location + '/' + key.replace('~', '~0').replace('/', '~1'), scope)
                  for key, item in node.items() if key != '$id'}
        if '$ref' in result:
            ref = result['$ref']
            if ref != '#' and not ref.startswith('#/'):
                raise ValueError('Activated MCP schemas require JSON-pointer local references')
            result['$ref'] = scope + ref[1:]
        return result
    return walk(value, pointer, pointer)


class DurableMCP:
    def __init__(self, registry):
        self.registry = registry
        self.ctx = registry.context
        self.configs = {}
        path = self.ctx.settings.config_path
        if path:
            raw = yaml.safe_load(path.read_text(encoding='utf-8-sig')) or {}
            for config in validate_mcp_servers(raw.get('mcp_servers')):
                cfg = MCPServerConfig(**config)
                if cfg.name in self.configs:
                    raise ValueError('Duplicate MCP server name')
                self.configs[cfg.name] = cfg
                for key, value in {**cfg.env, **cfg.headers}.items():
                    if re.search(r'key|token|secret|password|authorization|cookie|credential', key, re.IGNORECASE):
                        resolved = resolve_env_vars(value)
                        if resolved:
                            self.ctx.extension_secrets.add(resolved)
                            if resolved.lower().startswith('bearer '):
                                self.ctx.extension_secrets.add(resolved[7:])
        if not self.configs:
            return
        common = {'server': {'type': 'string', 'enum': list(self.configs)}, '_connection': {'type': 'string'}}
        registry.register(ToolDefinition(name='mcp_discover', risk='execute',
            description='Connect to one configured MCP server and list tools; explicit approval required even for discovery.',
            parameters={'type': 'object', 'properties': common, 'required': ['server'], 'additionalProperties': False}), self.discover)
        registry.register(ToolDefinition(name='mcp_call', risk='execute',
            description='Call a tool after mcp_search and mcp_load provide its exact schema. Every remote call requires separate approval.',
            parameters={'type': 'object', 'properties': {**common, 'tool': {'type': 'string'}, 'arguments': {'type': 'object'}},
                        'required': ['server', 'tool', 'arguments'], 'additionalProperties': False}), self.call)
        registry.register(ToolDefinition(name='mcp_search', description='Search an already approved MCP catalog by tool name or description. Returns up to five short matches; use mcp_load to activate exact schemas.',
            parameters={'type': 'object', 'properties': {'server': common['server'], 'query': {'type': 'string', 'minLength': 1, 'maxLength': 200}},
                        'required': ['server', 'query'], 'additionalProperties': False}), self.search)
        registry.register(ToolDefinition(name='mcp_load', description='Load up to five tool schemas from an approved MCP catalog into this task. No remote call or execution authorization. At most ten tools active per task.',
            parameters={'type': 'object', 'properties': {'server': common['server'], 'tools': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 5, 'uniqueItems': True}},
                        'required': ['server', 'tools'], 'additionalProperties': False}), self.load)

    def catalog(self, server):
        record = self.ctx.cp.get('mcp_catalogs', {}).get(server, {})
        if server not in self.configs or record.get('fingerprint') != self.fingerprint(server):
            raise ValueError('MCP catalog missing or configuration changed; rediscover with approval')
        return record

    async def search(self, args, call_id):
        catalog = self.catalog(args['server'])['tools']
        terms = re.findall(r'\w+', args['query'].casefold())
        scored = []
        for name, item in catalog.items():
            score = (100 if args['query'].casefold() == name.casefold() else 0)
            score += sum(term in (name + ' ' + item['description']).casefold() for term in terms)
            if score:
                scored.append((score, name))
        names = [name for _, name in sorted(scored, key=lambda item: (-item[0], item[1]))[:5]]
        return ToolResult(call_id=call_id, content=json.dumps([{'name': name, 'description': catalog[name]['description'][:160]} for name in names], ensure_ascii=False))

    async def load(self, args, call_id):
        record = self.catalog(args['server'])
        names = args['tools']
        if not 1 <= len(names) <= 5 or len(set(names)) != len(names) or any(name not in record['tools'] for name in names):
            raise ValueError('Choose one to five distinct discovered tools')
        active = self.ctx.cp.get('mcp_active', {})
        count = 0
        for server, item in active.items():
            if server in self.configs and item['fingerprint'] == self.fingerprint(server):
                count += len(set(item['tools']) | set(names)) if server == args['server'] else len(item['tools'])
        if args['server'] not in active or active[args['server']]['fingerprint'] != record['fingerprint']:
            count += len(names)
        if count > 10:
            raise ValueError('At most ten MCP schemas may be active in a task')
        selected = {name: record['tools'][name] for name in names}
        for item in selected.values():
            _embedded_schema(item['schema'], '#')
        if len(json.dumps(selected)) > 24000:
            raise ValueError('Selected schema payload exceeds 24000 characters; choose fewer tools')
        combined = {}
        for server, item in active.items():
            if server in self.configs and item['fingerprint'] == self.fingerprint(server):
                tools = self.catalog(server)['tools']
                combined[server] = {name: tools[name] for name in item['tools'] if name in tools}
        combined.setdefault(args['server'], {}).update(selected)
        if len(json.dumps(combined)) > 24000:
            raise ValueError('Total activated schema payload exceeds 24000 characters')
        return ToolResult(call_id=call_id, content=json.dumps(selected, ensure_ascii=False),
                          metadata={'mcp_activation': {'server': args['server'], 'fingerprint': record['fingerprint'], 'tools': names}})

    def refresh_definition(self):
        if not self.configs:
            return
        variants = []
        for server, active in self.ctx.cp.get('mcp_active', {}).items():
            try:
                record = self.catalog(server)
            except ValueError:
                continue
            if active['fingerprint'] != record['fingerprint']:
                continue
            for name in active['tools']:
                if name in record['tools']:
                    variants.append({'type': 'object', 'properties': {'server': {'type': 'string', 'const': server},
                        'tool': {'type': 'string', 'const': name}, 'arguments': _embedded_schema(record['tools'][name]['schema'], f'#/oneOf/{len(variants)}/properties/arguments'), '_connection': {'type': 'string'}},
                        'required': ['server', 'tool', 'arguments'], 'additionalProperties': False})
        definition, handler = self.registry.entries['mcp_call']
        parameters = {'type': 'object', 'properties': {
            'server': {'type': 'string', 'enum': list(self.configs)}, 'tool': {'type': 'string'},
            'arguments': {'type': 'object'}, '_connection': {'type': 'string'}},
            'required': ['server', 'tool', 'arguments'], 'additionalProperties': False}
        if variants:
            parameters['oneOf'] = variants
        self.registry.entries['mcp_call'] = (definition.model_copy(update={'parameters': parameters}), handler)

    def fingerprint(self, server):
        cfg = self.configs[server]
        values = asdict(cfg)
        values['env'] = {key: resolve_env_vars(value) for key, value in cfg.env.items()}
        values['headers'] = {key: resolve_env_vars(value) for key, value in cfg.headers.items()}
        payload = json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
        key = self.ctx.settings.access_token.get_secret_value().encode()
        return hmac.new(key, payload, hashlib.sha256).hexdigest()

    def bind(self, call):
        if call.name not in {'mcp_discover', 'mcp_call'}:
            return call
        server = call.arguments.get('server')
        if server not in self.configs:
            return call
        return call.model_copy(update={'arguments': {**call.arguments, '_connection': self.fingerprint(server)}})

    async def _connected(self, server, operation):
        from mewcode.mcp.client import MCPClient
        from muse.extensions.stdio import controlled_stdio
        client = MCPClient(self.configs[server])
        client.stdio_transport = controlled_stdio
        client.cwd = self.ctx.workspace
        async def run():
            try:
                await client.connect()
                return await operation(client)
            finally:
                await client.close()
        return await self.ctx.controlled(asyncio.wait_for(run(), timeout=60))

    async def discover(self, args, call_id):
        async def operation(client):
            tools = await client.list_tools()
            if len(tools) > 100:
                raise ValueError('MCP catalog exceeds 100 tools')
            catalog = {}
            for tool in tools:
                schema = tool.inputSchema
                _local_references(schema)
                jsonschema.Draft202012Validator.check_schema(schema)
                if tool.name in catalog:
                    raise ValueError('Duplicate MCP tool name')
                catalog[tool.name] = {'description': tool.description or '', 'schema': schema}
            if len(json.dumps(catalog)) > 120000:
                raise ValueError('MCP catalog is too large')
            return catalog
        catalog = await self._connected(args['server'], operation)
        metadata = {'mcp_server': args['server'], 'mcp_fingerprint': args['_connection'], 'mcp_catalog': catalog}
        index = [{'name': name, 'description': item['description'][:120]} for name, item in catalog.items()]
        return ToolResult(call_id=call_id, content=json.dumps({'tools': index, 'next': 'Use mcp_search then mcp_load for exact schemas before mcp_call.'}, ensure_ascii=False), metadata=metadata)

    async def call(self, args, call_id):
        record = self.ctx.cp.get('mcp_catalogs', {}).get(args['server'], {})
        if record.get('fingerprint') != args['_connection']:
            raise ValueError('MCP server configuration changed or has not been discovered')
        definition = record.get('tools', {}).get(args['tool'])
        if definition is None:
            raise ValueError('MCP tool was not discovered')
        jsonschema.validate(args['arguments'], definition['schema'])
        async def operation(client):
            return await client.call_tool(args['tool'], args['arguments'])
        result = await self._connected(args['server'], operation)
        content = '\n'.join(block.text for block in result.content if hasattr(block, 'text'))
        return ToolResult(call_id=call_id, status='error' if result.isError else 'success', content=content,
                          error_code='MCP_ERROR' if result.isError else None)

    def restore(self, result):
        metadata = result.metadata
        if result.status == 'success' and 'mcp_catalog' in metadata:
            self.ctx.cp.setdefault('mcp_catalogs', {})[metadata['mcp_server']] = {
                'fingerprint': metadata['mcp_fingerprint'], 'tools': metadata['mcp_catalog']}
        if result.status == 'success' and 'mcp_activation' in metadata:
            active = metadata['mcp_activation']
            record = self.ctx.cp.get('mcp_catalogs', {}).get(active['server'], {})
            if record.get('fingerprint') == active['fingerprint']:
                states = self.ctx.cp.setdefault('mcp_active', {})
                previous = states.get(active['server'], {})
                names = previous.get('tools', []) if previous.get('fingerprint') == active['fingerprint'] else []
                states[active['server']] = {'fingerprint': active['fingerprint'], 'tools': sorted(set(names) | set(active['tools']))}
