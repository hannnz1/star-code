from test_task_lifecycle import make_repo, create


def test_readonly_interruption_is_requeued_and_budget_is_kept(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claim = repo.claim_next("old", now=100, ttl=20)
    repo.checkpoint(task.id, "old", claim.lease_epoch, {"model_requests": 7, "active_seconds": 11}, now=101)
    repo.prepare_call(task.id, "old", claim.lease_epoch, "read-1", "read_file", {"path": "x"}, "read", now=102)
    repo.begin_call(task.id, "old", claim.lease_epoch, "read-1", now=103)
    assert repo.recover_expired_tasks(now=121) == [task.id]
    recovered = repo.get(task.id)
    assert recovered.status == "QUEUED"
    assert recovered.checkpoint["model_requests"] == 7
    assert repo.calls(task.id)[0]["status"] == "PREPARED"
    new_claim = repo.claim_next("new", now=122)
    assert new_claim.lease_epoch > claim.lease_epoch


def test_unknown_write_is_not_replayed_or_claimed(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claim = repo.claim_next("old", now=100, ttl=20)
    repo.prepare_call(task.id, "old", claim.lease_epoch, "write-1", "write_file", {"path": "x"}, "write", now=101)
    repo.begin_call(task.id, "old", claim.lease_epoch, "write-1", now=102)
    repo.recover_expired_tasks(now=121)
    assert repo.get(task.id).status == "INTERRUPTED"
    assert repo.calls(task.id)[0]["status"] == "UNKNOWN"
    assert repo.claim_next("new", now=122) is None


def test_waiting_approval_survives_reopen(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claim = repo.claim_next("worker")
    repo.prepare_call(task.id, "worker", claim.lease_epoch, "shell-1", "run_command", {"command": "echo hello"}, "execute")
    approval = repo.request_approval(task.id, "worker", claim.lease_epoch, "shell-1")
    from muse.tasks.repository import TaskRepository
    other = TaskRepository(tmp_path / "state.sqlite3")
    assert other.get(task.id).status == "WAITING_APPROVAL"
    assert other.approvals(task.id)[0]["id"] == approval["id"]
    assert other.recover_expired_tasks(now=10**12) == []


def test_persisted_completed_call_is_never_started_twice(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claim = repo.claim_next("worker")
    repo.prepare_call(task.id, "worker", claim.lease_epoch, "call", "write_file", {"path": "x"}, "write")
    assert repo.begin_call(task.id, "worker", claim.lease_epoch, "call")
    repo.complete_call(task.id, "worker", claim.lease_epoch, "call", {"status": "success", "content": "saved"})
    assert repo.begin_call(task.id, "worker", claim.lease_epoch, "call") is False


async def test_unexpected_exception_after_effect_keeps_reconciliation_available(tmp_path):
    from test_agent_loop import runtime, ScriptedProvider
    from muse.tasks.worker import Worker
    repo, task, original = runtime(tmp_path, ScriptedProvider([]))

    class CrashRunner:
        async def run(self, task, context):
            repo.prepare_call(task.id, context.owner, context.epoch, 'effect', 'fixture_write', {}, 'write')
            repo.begin_call(task.id, context.owner, context.epoch, 'effect')
            (context.workspace / 'changed.txt').write_text('effect occurred')
            raise RuntimeError('Failure before durable result')

    await Worker(original.settings, repo, CrashRunner()).run_once()
    assert repo.get(task.id).status == 'INTERRUPTED'
    assert repo.calls(task.id)[0]['status'] == 'UNKNOWN'
    assert repo.claim_next('later') is None
