import pytest

from test_agent_loop import ScriptedProvider, runtime


def test_explicit_external_reconciliation_never_reexecutes_or_fabricates_verification(tmp_path):
    repo, task, _ = runtime(tmp_path, ScriptedProvider([]))
    lease = repo.claim_next('worker')
    repo.prepare_call(task.id, 'worker', lease.lease_epoch, 'cmd', 'verify_command', {'command': 'echo fixture'}, 'execute')
    approval = repo.request_approval(task.id, 'worker', lease.lease_epoch, 'cmd')
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    lease = repo.claim_next('worker')
    repo.begin_call(task.id, 'worker', lease.lease_epoch, 'cmd')
    repo.abandon(task.id, 'worker', lease.lease_epoch)
    interrupted = repo.get(task.id)
    with pytest.raises(ValueError, match='digest'):
        repo.reconcile_external(task.id, 'cmd', 'wrong', interrupted.revision, True, 'Checked locally')
    repo.reconcile_external(task.id, 'cmd', approval['action_digest'], interrupted.revision, True, 'Checked locally')
    call = repo.calls(task.id)[0]
    assert call['status'] == 'DONE' and call['attempts'] == 1
    assert call['result']['metadata']['verified'] is False
    assert 'exit_code' not in call['result']['metadata']
    assert repo.get(task.id).status == 'INTERRUPTED'
    repo.control(task.id, 'resume', expected_revision=repo.get(task.id).revision)
    assert repo.get(task.id).status == 'QUEUED'
