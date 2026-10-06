import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text

from muse.commerce.schema import SCHEMA as COMMERCE_SCHEMA

SCHEMA_VERSION = 12

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY)",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(1)",
    """CREATE TABLE IF NOT EXISTS workspaces(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE, created_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS tasks(
        id TEXT PRIMARY KEY, prompt TEXT NOT NULL, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        scenario TEXT NOT NULL, client_request_id TEXT NOT NULL UNIQUE, parent_task_id TEXT REFERENCES tasks(id),
        status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        cancel_requested INTEGER NOT NULL DEFAULT 0, pause_requested INTEGER NOT NULL DEFAULT 0,
        lease_owner TEXT, lease_epoch INTEGER NOT NULL DEFAULT 0, lease_until REAL,
        checkpoint TEXT NOT NULL DEFAULT '{}', result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
        event_sequence INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS events(
        task_id TEXT NOT NULL REFERENCES tasks(id), sequence INTEGER NOT NULL, type TEXT NOT NULL,
        payload TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(task_id,sequence))""",
    """CREATE TABLE IF NOT EXISTS tool_calls(
        task_id TEXT NOT NULL REFERENCES tasks(id), id TEXT NOT NULL, name TEXT NOT NULL, arguments TEXT NOT NULL,
        risk TEXT NOT NULL, status TEXT NOT NULL, digest TEXT NOT NULL, result TEXT, attempts INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(task_id,id))""",
    """CREATE TABLE IF NOT EXISTS approvals(
        id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), tool_call_id TEXT NOT NULL,
        action_digest TEXT NOT NULL, status TEXT NOT NULL, expires_at REAL NOT NULL, created_at REAL NOT NULL,
        UNIQUE(task_id,tool_call_id,action_digest))""",
    "CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status,created_at)",
    """CREATE TABLE IF NOT EXISTS task_delegations(
        parent_id TEXT NOT NULL REFERENCES tasks(id), child_id TEXT PRIMARY KEY REFERENCES tasks(id),
        root_id TEXT NOT NULL REFERENCES tasks(id), call_id TEXT NOT NULL, UNIQUE(parent_id,call_id))""",
    "CREATE TABLE IF NOT EXISTS execution_budgets(root_id TEXT PRIMARY KEY REFERENCES tasks(id), model_requests INTEGER NOT NULL DEFAULT 0)",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(2)",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(3)",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(4)",
    """CREATE TABLE IF NOT EXISTS team_messages(
        id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES tasks(id), sender_id TEXT NOT NULL REFERENCES tasks(id),
        recipient_id TEXT NOT NULL REFERENCES tasks(id), call_id TEXT NOT NULL, message TEXT NOT NULL,
        created_at REAL NOT NULL, UNIQUE(sender_id,call_id))""",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(5)",
    """CREATE TABLE IF NOT EXISTS team_work_items(
        id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES tasks(id), title TEXT NOT NULL,
        dependencies TEXT NOT NULL, owner_id TEXT REFERENCES tasks(id), status TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS team_work_actions(
        task_id TEXT NOT NULL REFERENCES tasks(id), call_id TEXT NOT NULL, arguments TEXT NOT NULL,
        result TEXT NOT NULL, PRIMARY KEY(task_id,call_id))""",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(6)",
    """CREATE TABLE IF NOT EXISTS conversation_checkpoints(
        task_id TEXT NOT NULL REFERENCES tasks(id), sequence INTEGER NOT NULL, messages TEXT NOT NULL,
        created_at REAL NOT NULL, PRIMARY KEY(task_id,sequence))""",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(7)",
    """CREATE TABLE IF NOT EXISTS conversation_archives(
        task_id TEXT NOT NULL REFERENCES tasks(id), revision INTEGER NOT NULL,
        sequence INTEGER NOT NULL, messages TEXT NOT NULL, created_at REAL NOT NULL,
        PRIMARY KEY(task_id,revision))""",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(8)",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(9)",
    "INSERT OR IGNORE INTO schema_version(version) VALUES(10)",
]


class Database:
    def __init__(self, path: Path):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        migration_backup = None
        if path.exists():
            with closing(sqlite3.connect(path)) as source:
                table = source.execute("SELECT name FROM sqlite_master WHERE name='schema_version'").fetchone()
                prior = source.execute('SELECT MAX(version) FROM schema_version').fetchone()[0] if table else 0
                if prior and prior > SCHEMA_VERSION:
                    raise ValueError('Unsupported database schema version')
                if prior and prior < SCHEMA_VERSION:
                    directory = path.parent / 'migration-backups'
                    if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
                        raise ValueError('Migration backup directory must not be linked')
                    directory.mkdir(exist_ok=True)
                    migration_backup = directory / f'v{prior}-before-v{SCHEMA_VERSION}-{uuid.uuid4().hex[:12]}.sqlite3'
                    with closing(sqlite3.connect(migration_backup)) as target:
                        source.backup(target)
                    with closing(sqlite3.connect(migration_backup)) as check:
                        if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise ValueError('Migration backup integrity check failed')
        self.engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False, "timeout": 20})

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=20000")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")

        with self.transaction() as connection:
            for statement in [*SCHEMA, *COMMERCE_SCHEMA]:
                connection.exec_driver_sql(statement)
            if connection.exec_driver_sql("SELECT MAX(version) FROM schema_version").scalar() != SCHEMA_VERSION:
                raise ValueError("Unsupported database schema version")
            columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(tasks)')}
            if 'read_only' not in columns:
                connection.exec_driver_sql('ALTER TABLE tasks ADD COLUMN read_only INTEGER NOT NULL DEFAULT 0')
            if 'permission_mode' not in columns:
                connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN permission_mode TEXT NOT NULL DEFAULT 'acceptEdits'")
                connection.exec_driver_sql("UPDATE tasks SET permission_mode='plan' WHERE read_only=1")
            for name, datatype in [('policy_version', 'INTEGER NOT NULL DEFAULT 1'),
                                   ('legacy_policy', 'INTEGER NOT NULL DEFAULT 1'),
                                   ('coordinator_mode', 'INTEGER NOT NULL DEFAULT 0'),
                                   ('plan_task_id', 'TEXT'), ('plan_sha256', 'TEXT'),
                                   ('current_directory', "TEXT NOT NULL DEFAULT '.'")]:
                if name not in columns:
                    connection.exec_driver_sql(f'ALTER TABLE tasks ADD COLUMN {name} {datatype}')
            approval_columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(approvals)')}
            for name, datatype in [('permission_mode', "TEXT NOT NULL DEFAULT 'acceptEdits'"),
                                   ('policy_version', 'INTEGER NOT NULL DEFAULT 1'), ('workspace_id', 'TEXT')]:
                if name not in approval_columns:
                    connection.exec_driver_sql(f'ALTER TABLE approvals ADD COLUMN {name} {datatype}')
                    connection.exec_driver_sql(f'UPDATE approvals SET {name}=(SELECT {name} FROM tasks WHERE tasks.id=approvals.task_id)')
            budget_columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(execution_budgets)')}
            for name, datatype in [('max_turns', 'INTEGER'), ('max_tool_calls', 'INTEGER'), ('max_active_seconds', 'REAL')]:
                if name not in budget_columns:
                    connection.exec_driver_sql(f'ALTER TABLE execution_budgets ADD COLUMN {name} {datatype}')
            connection.exec_driver_sql('''CREATE TABLE IF NOT EXISTS migration_audit(
                id TEXT PRIMARY KEY,version INTEGER NOT NULL,backup_path TEXT NOT NULL,created_at REAL NOT NULL)''')
            if migration_backup:
                connection.execute(text('INSERT INTO migration_audit VALUES(:id,:version,:path,:now)'),
                                   {'id': uuid.uuid4().hex, 'version': SCHEMA_VERSION,
                                    'path': str(migration_backup), 'now': time.time()})

    @contextmanager
    def transaction(self):
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def rows(self, sql: str, parameters: dict | None = None) -> list[dict]:
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(sql), parameters or {}).mappings()]
