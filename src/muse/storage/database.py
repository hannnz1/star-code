from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text

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
]


class Database:
    def __init__(self, path: Path):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False, "timeout": 20})

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=20000")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")

        with self.transaction() as connection:
            for statement in SCHEMA:
                connection.exec_driver_sql(statement)
            if connection.exec_driver_sql("SELECT MAX(version) FROM schema_version").scalar() != 7:
                raise ValueError("Unsupported database schema version")
            columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(tasks)')}
            if 'read_only' not in columns:
                connection.exec_driver_sql('ALTER TABLE tasks ADD COLUMN read_only INTEGER NOT NULL DEFAULT 0')
            budget_columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(execution_budgets)')}
            for name, datatype in [('max_turns', 'INTEGER'), ('max_tool_calls', 'INTEGER'), ('max_active_seconds', 'REAL')]:
                if name not in budget_columns:
                    connection.exec_driver_sql(f'ALTER TABLE execution_budgets ADD COLUMN {name} {datatype}')

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
