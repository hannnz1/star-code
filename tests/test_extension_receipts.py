import pytest

from test_agent_loop import ScriptedProvider, runtime


@pytest.mark.parametrize('name', ['spawn_skill', '__hook_0', '__hook_async', 'team_work', 'team_message'])
def test_committed_extension_receipt_recovers_without_replaying(tmp_path, name):
    repo, _, _ = runtime(tmp_path, ScriptedProvider([]))
    task = repo.claim_next('worker')
    args = {'action_preview': {'type': 'agent'}, '_source': 'fixture'} if name == '__hook_0' else {'action': 'create', 'title': 'Inspect'} if name == 'team_work' else {}
    if name == '__hook_async':
        args = {'action_preview': {'type': 'prompt', 'async': True}, '_source': 'fixture'}
    if name == 'team_message':
        child = repo.spawn_child(task.id, 'worker', task.lease_epoch, 'other', 'Recipient')
        args = {'recipient_id': child.id, 'message': 'Inspect files'}
    repo.prepare_call(task.id, 'worker', task.lease_epoch, 'call', name, args, 'execute')
    approval = repo.request_approval(task.id, 'worker', task.lease_epoch, 'call')
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    task = repo.claim_next('worker')
    repo.begin_call(task.id, 'worker', task.lease_epoch, 'call')
    if name == 'team_work':
        repo.team_work(task.id, 'worker', task.lease_epoch, 'call', args)
    elif name == 'team_message':
        repo.send_team_message(task.id, 'worker', task.lease_epoch, 'call', child.id, args['message'])
    else:
        repo.spawn_child(task.id, 'worker', task.lease_epoch, 'call', 'Child')
    repo.abandon(task.id, 'worker', task.lease_epoch)
    assert repo.calls(task.id)[0]['status'] == 'DONE'
    assert repo.calls(task.id)[0]['attempts'] == 1
    assert repo.get(task.id).status == 'QUEUED'
    if name == '__hook_async':
        assert repo.calls(task.id)[0]['result']['metadata']['hook_child_id']
