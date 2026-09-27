from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from sqlalchemy import text


class ArtifactService:
    def __init__(self, context):
        self.ctx = context
        self.directory = context.settings.data_dir / "artifacts"
        self.directory.mkdir(parents=True, exist_ok=True)
        with context.repo.db.transaction() as conn:
            conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS artifacts(
                id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id),name TEXT NOT NULL,
                media_type TEXT NOT NULL,storage_path TEXT NOT NULL,sha256 TEXT NOT NULL,
                version INTEGER NOT NULL,created_at REAL NOT NULL)""")
            conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS sources(
                id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id),url TEXT NOT NULL,title TEXT NOT NULL,
                text TEXT NOT NULL,sha256 TEXT NOT NULL,retrieved_at REAL NOT NULL,UNIQUE(task_id,url))""")

    def save(self, name: str, content: bytes, media_type: str = "text/markdown") -> dict:
        if not name or any(c in name for c in '/\\:\x00') or name in {".", ".."} or len(name) > 160:
            raise ValueError("Artifact name must be a plain filename")
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("Artifact exceeds 8 MiB")
        if media_type not in {"text/markdown", "text/plain", "application/json", "text/csv", "application/pdf"}:
            raise ValueError("Unsupported artifact media type")
        identifier = uuid.uuid4().hex
        path = self.directory / f"{identifier}.bin"
        digest = hashlib.sha256(content).hexdigest()
        with self.ctx.repo.db.transaction() as conn:
            version = conn.execute(text("SELECT COALESCE(MAX(version),0)+1 FROM artifacts WHERE task_id=:task AND name=:name"),
                                   {"task": self.ctx.task_id, "name": name}).scalar_one()
            record = {"id": identifier, "task_id": self.ctx.task_id, "name": name, "media_type": media_type,
                      "storage_path": str(path), "sha256": digest, "version": version, "created_at": time.time()}
            path.write_bytes(content)
            conn.execute(text("INSERT INTO artifacts(id,task_id,name,media_type,storage_path,sha256,version,created_at) VALUES(:id,:task_id,:name,:media_type,:storage_path,:sha256,:version,:created_at)"), record)
            self.ctx.repo._event(conn, self.ctx.task_id, "artifact", {key: value for key, value in record.items() if key != "storage_path"})
        return record

    def list(self, task_id: str | None = None) -> list[dict]:
        return self.ctx.repo.db.rows("SELECT * FROM artifacts WHERE task_id=:task ORDER BY created_at", {"task": task_id or self.ctx.task_id})

    def read(self, identifier: str) -> tuple[dict, bytes]:
        rows = self.ctx.repo.db.rows("SELECT * FROM artifacts WHERE id=:id", {"id": identifier})
        if not rows:
            raise ValueError("Unknown artifact")
        record = rows[0]
        path = Path(record["storage_path"])
        if path.is_symlink() or not path.resolve().is_relative_to(self.directory.resolve()):
            raise ValueError("Artifact integrity check failed")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Artifact integrity check failed")
        return record, data

    def source(self, url: str, title: str, content: str) -> dict:
        url, title, content = self.ctx.safe(url), self.ctx.safe(title), self.ctx.safe(content)
        record = {"id": uuid.uuid4().hex, "task_id": self.ctx.task_id, "url": url, "title": title,
                  "text": self.ctx.safe(content), "sha256": hashlib.sha256(content.encode()).hexdigest(), "retrieved_at": time.time()}
        with self.ctx.repo.db.transaction() as conn:
            conn.execute(text("""INSERT INTO sources(id,task_id,url,title,text,sha256,retrieved_at)
                VALUES(:id,:task_id,:url,:title,:text,:sha256,:retrieved_at)
                ON CONFLICT(task_id,url) DO UPDATE SET title=excluded.title,text=excluded.text,sha256=excluded.sha256,retrieved_at=excluded.retrieved_at"""), record)
            result = dict(conn.execute(text("SELECT * FROM sources WHERE task_id=:task_id AND url=:url"), record).mappings().one())
            self.ctx.repo._event(conn, self.ctx.task_id, "source", {k: v for k, v in result.items() if k != "text"})
        return result

    def sources(self) -> list[dict]:
        return self.ctx.repo.db.rows("SELECT * FROM sources WHERE task_id=:task ORDER BY retrieved_at", {"task": self.ctx.task_id})
