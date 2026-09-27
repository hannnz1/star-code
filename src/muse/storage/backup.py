"""Local state snapshots; workspace files and original configurations are untouched."""
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

MAX_TOTAL = 512 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def backup_state(directory, output):
    root, output = Path(directory).absolute(), Path(output).absolute()
    if root.resolve() != root or root.is_symlink() or output.is_relative_to(root):
        raise ValueError('Backup requires a real state directory and an outside destination')
    if output.exists():
        raise ValueError('Backup destination already exists')
    database = root / 'state.sqlite3'
    if not database.is_file():
        raise ValueError('No MUSE state database found')
    with tempfile.TemporaryDirectory(prefix='muse-backup-', dir=root.parent) as temporary:
        snapshot = Path(temporary) / 'state.sqlite3'
        with closing(sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True)) as source, closing(sqlite3.connect(snapshot)) as target:
            if source.execute("SELECT COUNT(*) FROM tasks WHERE status='RUNNING'").fetchone()[0]:
                raise ValueError('Stop running Workers before taking a state backup')
            source.backup(target)
            if target.execute("SELECT COUNT(*) FROM tasks WHERE status='RUNNING'").fetchone()[0]:
                raise ValueError('Worker started during backup; stop it and retry')
        files, total = {}, 0
        for path in root.rglob('*'):
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) or not path.resolve().is_relative_to(root):
                raise ValueError('Linked state files cannot be backed up')
            if not path.is_file() or path.name in {'state.sqlite3-wal', 'state.sqlite3-shm'} or path.name.endswith('.pid'):
                continue
            name = path.relative_to(root).as_posix()
            origin = snapshot if name == 'state.sqlite3' else path
            if origin.stat().st_size > MAX_FILE:
                raise ValueError('State file exceeds backup size limit')
            data = origin.read_bytes()
            total += len(data)
            if total > MAX_TOTAL or len(files) >= 10000:
                raise ValueError('State backup exceeds size/count limit')
            files[name] = data
        manifest = {'format': 1, 'created_at': time.time(), 'state_root': str(root),
                    'files': {name: digest(data) for name, data in files.items()},
                    'workspace_files_included': False}
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr('manifest.json', json.dumps(manifest))
        output.chmod(0o600)
    return {'path': str(output), 'files': len(files), 'sha256': digest(output.read_bytes()), 'contains_local_access_token': True}


def restore_state(archive_path, destination):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Restore destination must not exist')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.resolve() != destination.parent:
        raise ValueError('Restore parent is linked')
    files, total = {}, 0
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) > 10001 or len({name.casefold() for name in names}) != len(names):
            raise ValueError('Duplicate or excessive backup entries')
        for member in archive.infolist():
            name = member.filename
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Unsafe backup path')
            total += member.file_size
            if member.file_size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError('Backup exceeds size limit')
            files[name] = archive.read(member)
    try:
        manifest = json.loads(files.pop('manifest.json'))
        if manifest['format'] != 1 or set(manifest['files']) != set(files) or 'state.sqlite3' not in files:
            raise ValueError('Invalid backup manifest')
        if any(digest(data) != manifest['files'][name] for name, data in files.items()):
            raise ValueError('Backup checksum mismatch')
        old_root = Path(manifest['state_root'])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid backup manifest') from error
    staging = Path(tempfile.mkdtemp(prefix='.muse-restore-', dir=destination.parent))
    try:
        for name, data in files.items():
            target = staging.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        from muse.storage.database import Database
        database = Database(staging / 'state.sqlite3')
        database.engine.dispose()
        with closing(sqlite3.connect(staging / 'state.sqlite3')) as conn, conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, column in [('artifacts', 'storage_path'), ('file_history', 'snapshot')]:
                if table not in tables:
                    continue
                for rowid, value in conn.execute(f'SELECT rowid,{column} FROM {table} WHERE {column} IS NOT NULL').fetchall():
                    path = Path(value)
                    if not path.is_relative_to(old_root):
                        raise ValueError('Stored state file path leaves original state root')
                    conn.execute(f'UPDATE {table} SET {column}=? WHERE rowid=?', (str(destination / path.relative_to(old_root)), rowid))
            conn.execute("UPDATE tool_calls SET status=CASE WHEN risk='read' THEN 'PREPARED' ELSE 'UNKNOWN' END WHERE status='EXECUTING'")
            conn.execute("UPDATE tasks SET status=CASE WHEN EXISTS(SELECT 1 FROM tool_calls c WHERE c.task_id=tasks.id AND c.status='UNKNOWN') THEN 'INTERRUPTED' ELSE 'PAUSED' END,lease_owner=NULL,lease_until=NULL,pause_requested=1,revision=revision+1 WHERE status NOT IN ('SUCCEEDED','FAILED','CANCELLED')")
            conn.execute("UPDATE approvals SET status='PENDING',expires_at=0 WHERE status='APPROVED'")
        if (staging / 'access-token').exists():
            (staging / 'access-token').chmod(0o600)
        if destination.exists():
            raise ValueError('Restore destination already exists')
        os.rename(staging, destination)
    finally:
        if staging.exists() and staging.resolve().parent == destination.parent and not staging.is_symlink():
            shutil.rmtree(staging)
    return {'path': str(destination), 'files': len(files), 'unfinished_tasks_paused': True, 'workspace_files_restored': False}
