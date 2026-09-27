from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider, runtime


async def test_project_guidance_includes_are_bounded_and_snapshotted(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type='text', text='Done')]])
    repo, task, worker = runtime(tmp_path, provider)
    root = tmp_path / 'project'
    (root / 'AGENTS.md').write_text('Use Chinese.\n@./guide.md\n@../private.txt\n@./.env', encoding='utf-8')
    (root / 'guide.md').write_text('Run local tests.', encoding='utf-8')
    (root / '.env').write_text('PRIVATE_CANARY')
    (tmp_path / 'private.txt').write_text('OUTSIDE_CANARY')
    await worker.run_once()
    system = provider.requests[0][0]['content']
    assert 'Use Chinese.' in system and 'Run local tests.' in system
    assert 'PRIVATE_CANARY' not in system and 'OUTSIDE_CANARY' not in system
    assert repo.get(task.id).checkpoint['project_guidance']['sources']


async def test_custom_role_constraints_are_bound_and_retained(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='spawn', name='spawn_task', arguments={'prompt': 'Inspect', 'role': 'auditor'}))],
        [ModelEvent(type='text', text='Waiting')]])
    repo, task, worker = runtime(tmp_path, provider)
    directory = tmp_path / 'project/.muse/agents'
    directory.mkdir(parents=True)
    (directory / 'auditor.md').write_text('---\nname: auditor\ndescription: Read-only audit\ntools: [Read, Grep]\nmaxTurns: 3\n---\nReport concrete findings.', encoding='utf-8')
    await worker.run_once()
    assert repo.get(task.id).status == 'WAITING_APPROVAL'
    approval = repo.approvals(task.id)[0]
    assert '_role_sha256' in approval['arguments']
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    child = repo.children(task.id)[0]
    assert child.checkpoint['allowed_tools'] == ['read_file', 'search_text']
    assert child.checkpoint['max_local_turns'] == 3
    assert 'Report concrete findings.' in child.prompt
