import json
import zipfile

import pytest

from muse.tasks.repository import TaskRepository
from test_agent_loop import ScriptedProvider, runtime


def test_state_backup_restores_to_new_directory_and_pauses_work(tmp_path):
    from muse.storage.backup import backup_state, restore_state
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    output = tmp_path / 'backup.zip'
    result = backup_state(worker.settings.data_dir, output)
    assert result['files'] >= 2
    restored = tmp_path / 'restored'
    restore_state(output, restored)
    recovered = TaskRepository(restored / 'state.sqlite3')
    assert recovered.get(task.id).status == 'PAUSED'
    assert recovered.claim_next('worker') is None
    assert repo.get(task.id).status == 'QUEUED'
    assert (restored / 'access-token').read_bytes() == (worker.settings.data_dir / 'access-token').read_bytes()
    with pytest.raises(ValueError, match='empty|exist'):
        restore_state(output, restored)


def test_backup_refuses_active_worker_and_restore_refuses_tampered_archive(tmp_path):
    from muse.storage.backup import backup_state, restore_state
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    repo.claim_next('worker')
    with pytest.raises(ValueError, match='Worker|running'):
        backup_state(worker.settings.data_dir, tmp_path / 'active.zip')
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('../outside.txt', 'tamper')
        z.writestr('manifest.json', json.dumps({'files': {'../outside.txt': 'bad'}}))
    with pytest.raises(ValueError):
        restore_state(bad, tmp_path / 'new')
    assert not (tmp_path / 'outside.txt').exists()


def test_backup_relocation_preserves_artifact_and_original_state(tmp_path):
    from pathlib import Path
    from muse.artifacts.service import ArtifactService
    from muse.storage.backup import backup_state, restore_state
    from muse.tools.context import ExecutionContext
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    task = repo.claim_next('backup-worker')
    ctx = ExecutionContext(worker.settings, repo, task, 'backup-worker')
    item = ArtifactService(ctx).save('report.md', b'Recoverable report', 'text/markdown')
    repo.finish(ctx.task_id, ctx.owner, ctx.epoch, 'SUCCEEDED')
    archive = tmp_path / 'state.zip'
    backup_state(ctx.settings.data_dir, archive)
    destination = tmp_path / 'restored-state'
    restore_state(archive, destination)
    restored = TaskRepository(destination / 'state.sqlite3')
    row = restored.db.rows('SELECT * FROM artifacts WHERE id=:id', {'id': item['id']})[0]
    assert Path(row['storage_path']).is_relative_to(destination)
    assert Path(row['storage_path']).read_bytes() == b'Recoverable report'
    assert Path(item['storage_path']).read_bytes() == b'Recoverable report'
    assert restored.get(ctx.task_id).status == repo.get(ctx.task_id).status == 'SUCCEEDED'


def test_v1_backup_upgrades_to_v7_without_changing_rollback_copy(tmp_path):
    import hashlib
    import sqlite3
    from contextlib import closing
    from muse.storage.backup import backup_state, restore_state
    original = tmp_path / 'v1'
    original.mkdir()
    database = original / 'state.sqlite3'
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.executescript('''
            CREATE TABLE schema_version(version INTEGER PRIMARY KEY);
            INSERT INTO schema_version VALUES(1);
            CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT,path TEXT UNIQUE,created_at REAL);
            INSERT INTO workspaces VALUES('workspace','fixture','fixture',1);
            CREATE TABLE tasks(id TEXT PRIMARY KEY,prompt TEXT,workspace_id TEXT,scenario TEXT,
              client_request_id TEXT UNIQUE,parent_task_id TEXT,status TEXT,revision INTEGER DEFAULT 1,
              created_at REAL,updated_at REAL,cancel_requested INTEGER DEFAULT 0,pause_requested INTEGER DEFAULT 0,
              lease_owner TEXT,lease_epoch INTEGER DEFAULT 0,lease_until REAL,
              checkpoint TEXT DEFAULT '{}',result TEXT DEFAULT '',error TEXT DEFAULT '',event_sequence INTEGER DEFAULT 0);
            INSERT INTO tasks(id,prompt,workspace_id,scenario,client_request_id,status,created_at,updated_at,checkpoint)
              VALUES('old-task','Old goal','workspace','coding','old-request','SUCCEEDED',1,1,'{"model_requests":3}');
        ''')
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    archive = tmp_path / 'legacy-backup.zip'
    backup_state(original, archive)
    restored = tmp_path / 'upgraded'
    restore_state(archive, restored)
    repo = TaskRepository(restored / 'state.sqlite3')
    assert repo.db.rows('SELECT MAX(version) AS version FROM schema_version')[0]['version'] == 7
    assert repo.get('old-task').checkpoint['model_requests'] == 3
    assert repo.get('old-task').read_only is False
    assert repo.conversation_checkpoints('old-task') == []
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    with closing(sqlite3.connect(database)) as conn:
        assert conn.execute('SELECT version FROM schema_version').fetchall() == [(1,)]
