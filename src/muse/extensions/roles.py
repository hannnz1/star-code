import hashlib
import json
import re
from pathlib import Path

import mewcode.agents
from mewcode.agents.parser import parse_agent_file
from muse.agent.instructions import (
    TrustedGuidancePolicy,
    expand_guidance,
    resource_text,
)
from muse.contracts import ToolDefinition


class DurableRoles:
    def __init__(self, registry):
        self.registry, self.ctx = registry, registry.context
        self.custom, self.errors = {}, []
        self.reload()
        registry.register(ToolDefinition(name='list_roles', description='List builtin and project roles with validation errors. All roles retain the selected provider.',
            parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}), self.list)

    def reload(self):
        if 'role_snapshot' in self.ctx.cp:
            snapshot = self.ctx.cp['role_snapshot']
            self.custom, self.errors, self.sources = snapshot['custom'], snapshot['errors'], snapshot['sources']
            return
        from mewcode.agents.parser import (
            AgentParseError,
            _validate_agent_meta,
            parse_frontmatter,
        )
        self.custom, self.errors, self.sources = {}, [], []
        root = self.ctx.workspace
        policy = TrustedGuidancePolicy([root, *self.ctx.settings.agent_roots, *self.ctx.settings.instruction_roots],
                                      [self.ctx.settings.data_dir] + ([self.ctx.settings.config_path] if self.ctx.settings.config_path else []))
        locations = [(directory, directory, 'user') for directory in self.ctx.settings.agent_roots]
        locations += [(root / directory, root, 'project') for directory in ('.mewcode/agents', '.muse/agents')]
        for directory, boundary, kind in locations:
            for path in sorted(directory.glob('*.md')):
                try:
                    source = resource_text(path, boundary)
                    meta, body = parse_frontmatter(source)
                    _validate_agent_meta(meta, str(path))
                    name = meta['name']
                    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name):
                        raise ValueError('Invalid role name')
                    if name in {'general', 'explore', 'plan', 'verification', 'store_manager', 'site_developer', 'product_content'}:
                        raise ValueError('Role name conflicts with an existing role')
                    if isinstance(meta.get('maxTurns'), bool):
                        raise TypeError('Role maxTurns must be positive and cannot be boolean')
                    body = self.ctx.safe(expand_guidance(body, path.parent, policy))
                    digest = hashlib.sha256((source + '\0' + body).encode()).hexdigest()
                    self.sources.append({'name': name, 'path': str(path), 'kind': kind, 'sha256': digest})
                    self.custom[name] = {'meta': meta, 'body': body,
                        'sha256': digest, 'source_path': str(path)}
                except (OSError, ValueError, TypeError, AgentParseError) as error:
                    self.errors.append(self.ctx.safe(str(error))[:500])
        self.ctx.cp['role_snapshot'] = {'custom': self.custom, 'errors': self.errors, 'sources': self.sources,
                                       'version': self.ctx.cp.get('source_version', 1)}
        if self.ctx.cp.get('commerce'):
            from muse.commerce.roles import role_snapshot
            self.ctx.cp['role_snapshot']['commerce'] = role_snapshot()

    async def list(self, args, call_id):
        self.reload()
        return json.dumps({'builtin': ['general', 'explore', 'plan', 'verification'],
                          'custom': [{'name': name, 'description': item['meta']['description'], 'sha256': item['sha256']}
                                     for name, item in self.custom.items()], 'errors': self.errors, 'sources': self.sources})

    def bind(self, call):
        if call.name not in {'spawn_task', 'spawn_worktree'}:
            return call
        self.reload()
        role = self.custom.get(call.arguments.get('role'))
        if role:
            return call.model_copy(update={'arguments': {**call.arguments, '_role_sha256': role['sha256']}})
        return call

    def prompt(self, name, prompt, *, isolated=False):
        if name in {'store_manager', 'site_developer', 'product_content'}:
            raise ValueError('Commerce roles require a durable business workflow, not generic delegation')
        if name not in self.custom:
            if name not in {'general', 'explore', 'plan', 'verification'}:
                raise ValueError('Unknown role. Builtin roles: general, explore, plan, verification. Use list_roles with {} for registered project roles, or omit role to use general. Role is not a worker display name.')
            return role_prompt(name, prompt)
        item = self.custom[name]
        meta = item['meta']
        model = meta.get('model', 'inherit')
        if model not in ('inherit', '', self.ctx.settings.provider.model if self.ctx.settings.provider else None):
            raise ValueError('Role model differs from the selected StarCode model')
        if meta.get('permissionMode') == 'bypassPermissions':
            raise ValueError('Roles cannot bypass approval')
        if meta.get('isolation') and not isolated:
            raise ValueError('Use spawn_worktree for isolated role work')
        aliases = {'Read': 'read_file', 'Write': 'write_file', 'Edit': 'edit_file', 'Bash': 'run_command',
                   'Grep': 'search_text', 'Glob': 'list_files', 'WebFetch': 'read_url', 'Agent': 'spawn_task'}
        def names(field):
            values = meta.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError('Role tools must be a list of names')
            mapped = [aliases.get(v, v) for v in values]
            if any(v not in self.registry.entries for v in mapped):
                raise ValueError('Role names an unavailable tool')
            return mapped
        allowed, denied = names('tools'), names('disallowedTools')
        available = [tool.name for tool in self.registry.definitions()]
        allowed = [name for name in (allowed or available) if name not in denied]
        result = item['body'] + '\n\nTask:\n' + prompt
        if len(result) > 50000:
            raise ValueError('Combined role prompt exceeds limit')
        return result, {'role': name, 'allowed_tools': allowed, 'max_local_turns': meta.get('maxTurns', 200)}


def role_prompt(role, prompt):
    filenames = {'general': 'general-purpose', 'explore': 'explore', 'plan': 'plan', 'verification': 'verification'}
    definition = parse_agent_file(Path(mewcode.agents.__file__).parent / 'builtins' / (filenames[role] + '.md'))
    capabilities = {'role': role, 'max_local_turns': definition.max_turns,
                    'read_only': role in {'explore', 'plan'}}
    if role == 'verification':
        capabilities['allowed_tools'] = ['list_files', 'read_file', 'search_text', 'read_document',
                                          'verify_command', 'read_offload', 'ask_user', 'save_artifact']
    if role != 'general':
        prompt = definition.system_prompt + '\n\nTask:\n' + prompt
    if len(prompt) > 50000:
        raise ValueError('Combined role and task prompt exceeds 50000 characters')
    # All durable roles use the selected StarCode provider. A builtin's model
    # preference never silently changes provider or credentials.
    return prompt, capabilities
