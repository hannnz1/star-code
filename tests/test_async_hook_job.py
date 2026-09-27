import yaml
import pytest

from muse.contracts import ModelEvent
from test_agent_loop import ScriptedProvider, runtime


async def test_async_hook_is_a_durable_job_without_extra_model_request(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type='text', text='Waiting for Hook')],
                                 [ModelEvent(type='text', text='Reviewed Hook result')]])
    repo, task, worker = runtime(tmp_path, provider)
    config = tmp_path / 'hooks.yaml'
    config.write_text(yaml.safe_dump({'hooks': [{'id': 'notice', 'event': 'session_start', 'async': True,
        'action': {'type': 'prompt', 'message': 'Background notice'}}]}))
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    await worker.run_once()
    children = repo.children(task.id)
    assert len(children) == 1
    assert 'hook_job' in children[0].checkpoint
    await worker.run_once()
    assert repo.get(children[0].id).status == 'SUCCEEDED'
    assert 'Background notice' in repo.get(children[0].id).result
    assert len(provider.requests) == 1
    await worker.run_once()
    assert repo.get(task.id).status == 'SUCCEEDED'
    assert len(repo.children(task.id)) == 1


async def test_async_command_requires_job_approval_and_runs_once(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type='text', text='Done')], [ModelEvent(type='text', text='Still done without verification')]])
    repo, task, worker = runtime(tmp_path, provider)
    config = tmp_path / 'hooks.yaml'
    config.write_text(yaml.safe_dump({'hooks': [{'id': 'notice', 'event': 'session_start', 'async': True,
        'action': {'type': 'command', 'command': 'echo fixture-hook > changed.txt'}}]}))
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    await worker.run_once()
    assert repo.children(task.id) == []
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    child = repo.children(task.id)[0]
    await worker.run_once()
    assert repo.get(child.id).status == 'WAITING_APPROVAL'
    assert repo.calls(child.id)[0]['attempts'] == 0
    approval = repo.approvals(child.id)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    await worker.run_once()
    assert repo.get(task.id).status == 'FAILED'
    assert (tmp_path / 'project/changed.txt').exists()
    assert repo.calls(child.id)[0]['attempts'] == 1


async def test_async_agent_hook_waits_for_grandchild_and_propagates_failure(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type='text', text='Root done')]])
    repo, task, worker = runtime(tmp_path, provider)
    config = tmp_path / 'hooks.yaml'
    config.write_text(yaml.safe_dump({'hooks': [{'id': 'agent', 'event': 'session_start', 'async': True,
        'action': {'type': 'agent', 'prompt': 'Inspect the project'}}]}))
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    async def approve(identifier):
        item = repo.approvals(identifier)[0]
        repo.decide_approval(item['id'], True, item['action_digest'])
    await worker.run_once()
    await approve(task.id)
    await worker.run_once()
    job = repo.children(task.id)[0]
    await worker.run_once()
    await approve(job.id)
    await worker.run_once()
    grandchild = repo.children(job.id)[0]
    assert repo.get(job.id).status == 'PAUSED'
    assert repo.get(task.id).status == 'PAUSED'
    # Its inherited Hook must not recursively launch the same Hook forever.
    assert grandchild.checkpoint['suppressed_hooks']
    claimed = repo.claim_next('test-grandchild')
    assert claimed.id == grandchild.id
    repo.finish(claimed.id, 'test-grandchild', claimed.lease_epoch, 'FAILED', error='fixture failure')
    await worker.run_once()
    await worker.run_once()
    assert repo.get(job.id).status == repo.get(task.id).status == 'FAILED'


@pytest.mark.parametrize('timing', ['before', 'after'])
async def test_async_command_verification_must_follow_actual_job(timing, tmp_path):
    from muse.contracts import ToolCall
    verify = [ModelEvent(type='call', call=ToolCall(id='verify', name='verify_command', arguments={'command': 'echo verified-fixture'}))]
    done = [ModelEvent(type='text', text='Done')]
    provider = ScriptedProvider([verify, done, done] if timing == 'before' else [done, verify, done])
    repo, task, worker = runtime(tmp_path, provider)
    config = tmp_path / 'hooks.yaml'
    config.write_text(yaml.safe_dump({'hooks': [{'id': 'write', 'event': 'session_start', 'async': True,
        'action': {'type': 'command', 'command': 'echo fixture > changed.txt'}}]}))
    worker.settings = worker.settings.model_copy(update={'config_path': config})
    for _ in range(20):
        await worker.run_once()
        for candidate in repo.list():
            for item in repo.approvals(candidate.id):
                if item['status'] == 'PENDING':
                    repo.decide_approval(item['id'], True, item['action_digest'])
        if repo.get(task.id).status in {'SUCCEEDED', 'FAILED'}:
            break
    assert repo.get(task.id).status == ('FAILED' if timing == 'before' else 'SUCCEEDED')
    assert (tmp_path / 'project/changed.txt').exists()
