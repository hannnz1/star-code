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
            description='Call a tool from an approved MCP discovery. Every call requires separate approval.',
            parameters={'type': 'object', 'properties': {**common, 'tool': {'type': 'string'}, 'arguments': {'type': 'object'}},
                        'required': ['server', 'tool', 'arguments'], 'additionalProperties': False}), self.call)

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
        return ToolResult(call_id=call_id, content=json.dumps(catalog, ensure_ascii=False), metadata=metadata)

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
