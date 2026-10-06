import sqlite3
from contextlib import closing

import pytest

from muse.config import load_settings
from muse.contracts import TaskRequest
from muse.memory.service import MemoryService
from muse.storage.database import Database
from muse.tasks.repository import TaskRepository


def v10_fixture(tmp_path):
    settings = load_settings(data_dir=tmp_path / 'state', require_provider=False)
    path = settings.data_dir / 'state.sqlite3'
    repo = TaskRepository(path)
    (tmp_path / 'project').mkdir()
    workspace = repo.register_workspace(str(tmp_path / 'project'))
    task = repo.create(TaskRequest(prompt='Keep this coding task', workspace_id=workspace['id'],
                                   client_request_id='original', scenario='coding'))
    memory = MemoryService(repo, settings)
    memory.upsert(scope='project', workspace_id=workspace['id'], title='Brand', content='Natural green')
    claimed = repo.claim_next('fixture')
    repo.prepare_call(task.id, 'fixture', claimed.lease_epoch, 'call', 'run_command', {'command': 'echo hello'}, 'execute')
    repo.request_approval(task.id, 'fixture', claimed.lease_epoch, 'call')
    before = {table: repo.db.rows(f'SELECT * FROM {table}') for table in ('tasks', 'workspaces', 'memories', 'approvals')}
    repo.db.engine.dispose()
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'commerce_%'").fetchall():
            conn.execute('DROP TABLE ' + name)
        conn.execute('DELETE FROM schema_version WHERE version>10')
    return path, before


def test_v10_migration_preserves_tasks_memories_and_approvals(tmp_path):
    path, before = v10_fixture(tmp_path)
    upgraded = Database(path)
    assert upgraded.rows('SELECT MAX(version) AS v FROM schema_version')[0]['v'] == 12
    for table, expected in before.items():
        assert upgraded.rows(f'SELECT * FROM {table}') == expected
    records = upgraded.rows('SELECT * FROM migration_audit WHERE version=12')
    assert len(records) == 1
    with closing(sqlite3.connect(records[0]['backup_path'])) as backup:
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert backup.execute('SELECT MAX(version) FROM schema_version').fetchone()[0] == 10
    upgraded.engine.dispose()


def test_failed_commerce_migration_is_atomic(tmp_path, monkeypatch):
    import muse.storage.database as module
    path, before = v10_fixture(tmp_path)
    monkeypatch.setattr(module, 'COMMERCE_SCHEMA', [*module.COMMERCE_SCHEMA, 'INVALID SQL FOR MIGRATION TEST'])
    from sqlalchemy.exc import OperationalError
    with pytest.raises(OperationalError):
        Database(path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0] == 10
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='commerce_projects'").fetchone() is None
        assert conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == len(before['tasks'])
