import hashlib
import json
from dataclasses import asdict

import yaml

from mewcode.skills.parser import (
    SkillParseError,
    parse_skill_text,
    substitute_arguments,
)
from muse.contracts import ToolDefinition, ToolResult


def context_seed(messages, *, recent):
    """Bound a reference seed at complete exchanges, never at JSON byte offsets."""
    groups = []
    for message in messages:
        if message.get('role') == 'tool':
            if groups and groups[-1][0].get('tool_calls'):
                groups[-1].append(message)
        else:
            groups.append([message])
    complete = []
    for group in groups:
        calls = group[0].get('tool_calls', [])
        if calls and {call['id'] for call in calls} != {m.get('tool_call_id') for m in group[1:]}:
            continue
        complete.append(group)
    selected = []
    for group in reversed(complete):
        candidate = group + selected
        if len(json.dumps(candidate, ensure_ascii=False)) > 24000:
            break
        selected = candidate
        if recent and len(selected) >= 5:
            break
    return json.dumps(selected, ensure_ascii=False)


class DurableSkills:
    def __init__(self, registry):
        self.ctx = registry.context
        self.reload()
        def schema(properties, required=()):
            return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}
        registry.register(ToolDefinition(name='list_skills', description='List workspace skill descriptions and validation errors.', parameters=schema({})), self.list)
        props = {'name': {'type': 'string'}, 'arguments': {'type': 'string'}, '_source_sha256': {'type': 'string'}}
        registry.register(ToolDefinition(name='load_skill', description='Read an inline workspace skill. Fork skills return metadata only; use spawn_skill for isolated execution.', parameters=schema(props, ['name'])), self.load)
        registry.register(ToolDefinition(name='spawn_skill', risk='execute', description='Run a workspace skill in a durable child task, with approval and shared budgets. Does not change the model.',
            parameters=schema({**props, '_source_sha256': {'type': 'string'}}, ['name'])), self.spawn)
        registry.register(ToolDefinition(name='install_skill', risk='execute', description='Install a GitHub skill from a full pinned commit into .muse/skills after approval. Never overwrites an existing skill; no installed code is executed.',
            parameters=schema({key: {'type': 'string'} for key in ('repository', 'commit', 'path', 'name')},
                              ['repository', 'commit', 'path', 'name'])), self.install)

    def reload(self):
        self.skills = {}
        self.errors = []
        root = self.ctx.workspace.resolve()
        locations = [(root / relative, root) for relative in ('.muse/skills', '.mewcode/skills')]
        locations += [(path.absolute(), path.absolute()) for path in self.ctx.settings.skill_roots]
        for directory, boundary in locations:
            if not directory.exists():
                continue
            if directory.is_symlink() or not directory.resolve().is_relative_to(boundary):
                self.errors.append('Skill directory leaves workspace')
                continue
            candidates = list(directory.glob('*.md')) + list(directory.glob('*/skill.yaml'))
            candidates += [path for path in directory.glob('*/SKILL.md') if not (path.parent / 'skill.yaml').exists()]
            for path in sorted(candidates):
                try:
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(boundary) or resolved.stat().st_size > 256000:
                        raise ValueError('Skill is outside workspace or too large')
                    snapshot = resolved.read_bytes()
                    source = snapshot.decode('utf-8-sig').replace('\r\n', '\n')
                    if path.name == 'skill.yaml':
                        meta = yaml.safe_load(source)
                        if not isinstance(meta, dict):
                            raise ValueError('Skill YAML must be a mapping')
                        prompt_path = (resolved.parent / 'prompt.md').resolve(strict=True)
                        if not prompt_path.is_relative_to(boundary) or prompt_path.stat().st_size > 256000:
                            raise ValueError('Skill prompt is outside workspace or too large')
                        prompt_bytes = prompt_path.read_bytes()
                        snapshot += b'\0' + prompt_bytes
                        if len(snapshot) > 256000:
                            raise ValueError('Combined skill exceeds 256000 bytes')
                        prompt = prompt_bytes.decode('utf-8-sig').replace('\r\n', '\n')
                        meta.setdefault('name', path.parent.name.lower().replace(' ', '-'))
                        if not meta.get('description'):
                            meta['description'] = next((line.strip() for line in prompt.splitlines()
                                                        if line.strip() and not line.startswith(('#', '---'))), '')
                        source = '---\n' + yaml.safe_dump(meta) + '---\n' + prompt
                    skill = parse_skill_text(source, resolved)
                    if skill.name not in self.skills:
                        descriptor = asdict(skill)
                        descriptor['source_path'] = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
                        descriptor['sha256'] = hashlib.sha256(snapshot).hexdigest()
                        self.skills[skill.name] = descriptor
                except (ValueError, OSError, SkillParseError, yaml.YAMLError) as error:
                    self.errors.append(self.ctx.safe(str(error))[:500])

    def bind(self, call):
        if call.name in {'list_skills', 'load_skill', 'spawn_skill'}:
            self.reload()
        if call.name in {'load_skill', 'spawn_skill'} and call.arguments.get('name') in self.skills and '_source_sha256' not in call.arguments:
            return call.model_copy(update={'arguments': {**call.arguments, '_source_sha256': self.skills[call.arguments['name']]['sha256']}})
        return call

    async def list(self, args, call_id):
        return json.dumps({'skills': [{key: value[key] for key in ('name', 'description', 'mode', 'sha256')} for value in self.skills.values()], 'errors': self.errors}, ensure_ascii=False)

    def selected(self, args):
        if args['name'] not in self.skills:
            raise ValueError('Unknown workspace skill; use list_skills')
        skill = self.skills[args['name']]
        if args.get('_source_sha256') and args['_source_sha256'] != skill['sha256']:
            raise ValueError('Skill source changed; submit a new reviewed execution request')
        if skill.get('model') not in (None, '', 'inherit', self.ctx.settings.provider.model if self.ctx.settings.provider else None):
            raise ValueError('Skill requests a different model; the selected StarCode model is preserved')
        return skill

    async def load(self, args, call_id):
        skill = self.selected(args)
        result = {key: skill[key] for key in ('name', 'description', 'mode', 'sha256', 'source_path')}
        if skill['mode'] == 'fork':
            result['next_tool'] = 'spawn_skill'
        else:
            result['instructions'] = substitute_arguments(skill['prompt_body'], args.get('arguments', ''))
        return self.ctx.safe(json.dumps(result, ensure_ascii=False))

    async def spawn(self, args, call_id):
        skill = self.selected(args)
        prompt = substitute_arguments(skill['prompt_body'], args.get('arguments', ''))
        if skill['context'] != 'none':
            messages = self.ctx.cp.get('messages', [])
            prompt += '\nRead-only parent context (do not replay tools):\n' + context_seed(messages, recent=skill['context'] == 'recent')
        prompt = self.ctx.safe(prompt)
        if not prompt.strip() or len(prompt) > 50000:
            raise ValueError('Skill prompt is empty or too large')
        child = self.ctx.repo.spawn_child(self.ctx.task_id, self.ctx.owner, self.ctx.epoch, call_id, prompt)
        return ToolResult(call_id=call_id, content=json.dumps({'child_id': child.id, 'skill': skill['name'], 'sha256': skill['sha256']}))

    async def install(self, args, call_id):
        from muse.extensions.skill_install import download_archive, install_archive
        data = await self.ctx.controlled(download_archive(args))
        self.ctx.check()
        result = install_archive(self.ctx.workspace, args, data)
        self.reload()
        return ToolResult(call_id=call_id, content=json.dumps(result))
