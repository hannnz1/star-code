import time

from sqlalchemy import text
from test_agent_loop import ScriptedProvider, runtime


def test_shared_budget_counts_running_sibling_before_next_checkpoint(tmp_path):
    repo, task, _ = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent')
    child = repo.spawn_child(task.id, 'parent', parent.lease_epoch, 'child', 'Inspect')
    repo.claim_next('child')
    with repo.db.transaction() as conn:
        conn.execute(text('UPDATE tasks SET updated_at=:then,checkpoint=:cp WHERE id=:id'),
                     {'id': child.id, 'then': time.time() - 6, 'cp': '{"active_seconds":2}'})
    assert repo.group_active_seconds(task.id) >= 8


def test_expired_lease_charges_uncheckpointed_active_time(tmp_path):
    repo, task, _ = runtime(tmp_path, ScriptedProvider([]))
    repo.claim_next('worker')
    now = time.time()
    with repo.db.transaction() as conn:
        conn.execute(text('UPDATE tasks SET updated_at=:start,lease_until=:end,checkpoint=:cp WHERE id=:id'),
                     {'id': task.id, 'start': now - 10, 'end': now - 2, 'cp': '{"active_seconds":3}'})
    repo.recover_expired_tasks(now=now)
    assert repo.get(task.id).checkpoint['active_seconds'] == 11
