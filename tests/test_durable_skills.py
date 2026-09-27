import json
from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider, runtime


async def test_inline_skill_uses_baseline_parser_and_records_source(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='load', name='load_skill', arguments={'name': 'inspect'}))],
        [ModelEvent(type='text', text='Loaded the inspection instructions.')]])
    repo, task, worker = runtime(tmp_path, provider)
    skills = tmp_path / 'project/.muse/skills'
    skills.mkdir(parents=True)
    (skills / 'inspect.md').write_text('---\nname: inspect\ndescription: Inspect files\n---\nRead hello.txt before proposing changes.')
    await worker.run_once()
    call = next(c for c in repo.calls(task.id) if c['id'] == 'load')
    result = json.loads(call['result']['content'])
    assert 'Read hello.txt' in result['instructions']
    assert len(result['sha256']) == 64


async def test_fork_skill_does_not_leak_body_into_parent(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='load', name='load_skill', arguments={'name': 'inspect'}))],
        [ModelEvent(type='text', text='Fork is required.')]])
    repo, task, worker = runtime(tmp_path, provider)
    skills = tmp_path / 'project/.muse/skills'
    skills.mkdir(parents=True)
    (skills / 'inspect.md').write_text('---\nname: inspect\ndescription: Inspect files\nmode: fork\n---\nFORK-ONLY-INSTRUCTIONS')
    await worker.run_once()
    call = next(c for c in repo.calls(task.id) if c['id'] == 'load')
    assert 'FORK-ONLY-INSTRUCTIONS' not in call['result']['content']
    assert 'spawn_skill' in call['result']['content']


def test_parser_can_parse_an_immutable_source_snapshot():
    from mewcode.skills.parser import parse_skill_text
    skill = parse_skill_text('---\nname: inspect\ndescription: test\n---\nsnapshot body')
    assert skill.prompt_body == 'snapshot body'


async def test_yaml_skill_layout_loads_prompt_and_binds_both_files(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='load', name='load_skill', arguments={'name': 'inspect'}))],
        [ModelEvent(type='text', text='Loaded YAML skill')]])
    repo, task, worker = runtime(tmp_path, provider)
    directory = tmp_path / 'project/.mewcode/skills/inspect'
    directory.mkdir(parents=True)
    (directory / 'skill.yaml').write_text('name: inspect\ndescription: Inspect files\ncontext: none\n')
    (directory / 'prompt.md').write_text('Read the YAML layout fixture.')
    await worker.run_once()
    call = repo.calls(task.id)[0]
    result = json.loads(call['result']['content'])
    assert result['instructions'] == 'Read the YAML layout fixture.'
    assert len(result['sha256']) == 64


async def test_skill_refresh_sees_edits_between_calls(tmp_path):
    from muse.tools.context import ExecutionContext
    from muse.tools.registry import ToolRegistry
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    directory = tmp_path / 'project/.muse/skills'
    directory.mkdir(parents=True)
    path = directory / 'inspect.md'
    header = '---\nname: inspect\ndescription: fixture\n---\n'
    path.write_text(header + 'first')
    claimed = repo.claim_next('worker')
    registry = ToolRegistry(ExecutionContext(worker.settings, repo, claimed, 'worker'))
    first = await registry.execute(ToolCall(id='first', name='load_skill', arguments={'name': 'inspect'}))
    path.write_text(header + 'second')
    second = await registry.execute(ToolCall(id='second', name='load_skill', arguments={'name': 'inspect'}))
    assert json.loads(second.content)['instructions'] == 'second'
    assert json.loads(first.content)['sha256'] != json.loads(second.content)['sha256']


def test_recent_skill_seed_keeps_tool_exchange_complete_and_valid_json():
    from muse.extensions.skills import context_seed
    messages = [{'role': 'user', 'content': 'Goal'},
                {'role': 'assistant', 'tool_calls': [{'id': 'read', 'name': 'read_file', 'arguments': {}}]},
                {'role': 'tool', 'tool_call_id': 'read', 'content': 'Evidence'}]
    messages += [{'role': 'assistant', 'content': 'x' * 20} for _ in range(4)]
    selected = json.loads(context_seed(messages, recent=True))
    assert selected[0]['role'] != 'tool'
    assert any(m.get('tool_calls') for m in selected)
    large = json.loads(context_seed([{'role': 'user', 'content': 'x' * 30000}], recent=False))
    assert large == []  # Never slice serialized JSON or half a tool exchange.
