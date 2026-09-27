import time
import uuid

from sqlalchemy import text

from muse.permissions.secrets import contains_secret


class MemoryService:
    def __init__(self, repository, settings):
        self.repo, self.settings = repository, settings
        with repository.db.transaction() as conn:
            conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS memories(
                id TEXT PRIMARY KEY,scope TEXT NOT NULL,workspace_id TEXT REFERENCES workspaces(id),
                title TEXT NOT NULL,content TEXT NOT NULL,source_task_id TEXT,updated_at REAL NOT NULL)""")

    def upsert(self, *, scope: str, content: str, title: str, workspace_id: str | None = None,
               memory_id: str | None = None, source_task_id: str | None = None) -> dict:
        if scope not in {"user", "project"} or not title.strip() or len(title) > 160 or not content.strip() or len(content) > 12000:
            raise ValueError("Invalid memory fields")
        secrets = [self.settings.access_token.get_secret_value()]
        if self.settings.provider:
            secrets.append(self.settings.provider.api_key.get_secret_value())
        if contains_secret(content) or contains_secret(title) or any(s and s in content + title for s in secrets):
            raise ValueError("Memory cannot contain secrets")
        if scope == "project":
            self.repo.workspace(workspace_id)
        elif workspace_id is not None:
            raise ValueError("User memory must not have a workspace")
        record = {"id": memory_id or uuid.uuid4().hex, "scope": scope, "workspace_id": workspace_id,
                  "title": title.strip(), "content": content.strip(), "source_task_id": source_task_id, "updated_at": time.time()}
        with self.repo.db.transaction() as conn:
            if memory_id and not conn.execute(text("SELECT id FROM memories WHERE id=:id"), {"id": memory_id}).first():
                raise ValueError("Unknown memory")
            conn.execute(text("""INSERT INTO memories(id,scope,workspace_id,title,content,source_task_id,updated_at)
                VALUES(:id,:scope,:workspace_id,:title,:content,:source_task_id,:updated_at)
                ON CONFLICT(id) DO UPDATE SET scope=excluded.scope,workspace_id=excluded.workspace_id,title=excluded.title,
                content=excluded.content,source_task_id=excluded.source_task_id,updated_at=excluded.updated_at"""), record)
        return record

    def for_task(self, workspace_id: str) -> list[dict]:
        return self.repo.db.rows("SELECT * FROM memories WHERE scope='user' OR (scope='project' AND workspace_id=:ws) ORDER BY updated_at DESC LIMIT 100", {"ws": workspace_id})

    def delete(self, memory_id: str):
        with self.repo.db.transaction() as conn:
            if conn.execute(text("DELETE FROM memories WHERE id=:id"), {"id": memory_id}).rowcount != 1:
                raise ValueError("Unknown memory")

    def list(self) -> list[dict]:
        return self.repo.db.rows("SELECT * FROM memories ORDER BY updated_at DESC")
