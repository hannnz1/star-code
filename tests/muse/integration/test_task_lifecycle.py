import importlib.util
from concurrent.futures import ThreadPoolExecutor

import pytest


def make_repo(tmp_path):
    assert importlib.util.find_spec("muse.tasks") is not None, "Durable task repository is missing"
    from muse.tasks.repository import TaskRepository
    repo = TaskRepository(tmp_path / "state.sqlite3")
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    ws = repo.register_workspace(str(workspace), "Test workspace")
    return repo, ws["id"]


def create(repo, workspace_id, request_id="request-1"):
    from muse.contracts import TaskRequest
    return repo.create(TaskRequest(prompt="Read the local project", workspace_id=workspace_id,
                                   client_request_id=request_id, scenario="coding"))


def test_create_deduplicates_same_request_and_rejects_changed_payload(tmp_path):
    repo, ws = make_repo(tmp_path)
    one = create(repo, ws)
    two = create(repo, ws)
    assert one.id == two.id
    from muse.contracts import TaskRequest
    with pytest.raises(ValueError, match="request"):
        repo.create(TaskRequest(prompt="Different task", workspace_id=ws, client_request_id="request-1"))
    assert len(repo.list()) == 1


def test_two_workers_cannot_claim_same_task(tmp_path):
    repo, ws = make_repo(tmp_path)
    create(repo, ws)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda name: repo.claim_next(name, now=100, ttl=20), ["worker-a", "worker-b"]))
    assert sum(item is not None for item in claimed) == 1
    assert len(repo.events(claimed[0].id if claimed[0] else claimed[1].id)) == 2


def test_revision_conflicts_do_not_change_task_or_append_event(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    paused = repo.control(task.id, "pause", expected_revision=task.revision)
    assert paused.status == "PAUSED"
    events = repo.events(task.id)
    with pytest.raises(ValueError, match="revision"):
        repo.control(task.id, "resume", expected_revision=task.revision)
    assert repo.events(task.id) == events


def test_cancel_queued_task_never_gets_claimed(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    assert repo.control(task.id, "cancel", expected_revision=task.revision).status == "CANCELLED"
    assert repo.claim_next("worker") is None


def test_completed_follow_up_creates_linked_task_without_mutating_parent(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claimed = repo.claim_next("worker")
    repo.finish(claimed.id, "worker", claimed.lease_epoch, "SUCCEEDED", "done")
    from muse.contracts import TaskRequest
    followup = repo.create(TaskRequest(prompt="Now add detail", workspace_id=ws,
                                      client_request_id="next", parent_task_id=task.id))
    assert followup.parent_task_id == task.id
    assert repo.get(task.id).status == "SUCCEEDED"
    with pytest.raises(ValueError):
        repo.control(task.id, "resume", expected_revision=repo.get(task.id).revision)


def test_events_are_ordered_and_resumable(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    repo.claim_next("worker")
    repo.add_event(task.id, "progress", {"text": "reading"})
    assert [event["sequence"] for event in repo.events(task.id)] == [1, 2, 3]
    assert [event["sequence"] for event in repo.events(task.id, after=2)] == [3]


def test_checkpoint_is_preserved_when_database_reopens(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claimed = repo.claim_next("worker")
    checkpoint = {"messages": [{"role": "user", "content": "hello"}], "model_requests": 4, "active_seconds": 23}
    repo.checkpoint(task.id, "worker", claimed.lease_epoch, checkpoint)
    from muse.tasks.repository import TaskRepository
    reopened = TaskRepository(tmp_path / "state.sqlite3")
    assert reopened.get(task.id).checkpoint == checkpoint


def test_expired_owner_cannot_checkpoint_or_begin_side_effect(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claim = repo.claim_next("old", now=10, ttl=5)
    with pytest.raises(ValueError, match="lease"):
        repo.checkpoint(task.id, "old", claim.lease_epoch, {"text": "wrong"}, now=16)
    with pytest.raises(ValueError, match="lease"):
        repo.prepare_call(task.id, "old", claim.lease_epoch, "c1", "write_file", {"path": "x"}, "write", now=16)


def test_unknown_workspace_is_rejected(tmp_path):
    repo, _ = make_repo(tmp_path)
    with pytest.raises(ValueError, match="workspace"):
        create(repo, "not-registered")
