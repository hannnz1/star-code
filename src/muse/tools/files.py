from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from sqlalchemy import text

from muse.contracts import ToolResult
from muse.permissions.policy import WorkspacePolicy

MAX_FILE_BYTES = 16 * 1024 * 1024
IGNORED_DIRS = {".git", ".muse", ".mewcode", ".venv", "node_modules", "__pycache__", ".pytest_cache"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FileTools:
    def __init__(self, context):
        self.context = context
        protected = [context.settings.data_dir]
        if context.settings.config_path:
            protected.append(context.settings.config_path)
        self.policy = WorkspacePolicy(context.workspace, protected)
        self.history_dir = context.settings.data_dir / "file-history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        with context.repo.db.transaction() as conn:
            conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS file_history(
                task_id TEXT NOT NULL, call_id TEXT NOT NULL, path TEXT NOT NULL, before_hash TEXT,
                after_hash TEXT NOT NULL, snapshot TEXT, restored INTEGER DEFAULT 0,
                PRIMARY KEY(task_id,call_id))""")

    def read_bytes(self, value: str) -> bytes:
        path = self.policy.resolve(value, must_exist=True)
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Not a regular file or file exceeds 16 MiB")
        with path.open("rb") as stream:
            self.policy.resolve(value, must_exist=True)
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("File exceeds 16 MiB")
        return data

    async def read_file(self, args, call_id):
        data = self.read_bytes(args["path"])
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("File is not UTF-8 text; use read_document for PDF files") from None
        return self.context.safe(content)

    async def list_files(self, args, call_id):
        root = self.policy.resolve(args.get("path", "."), must_exist=True)
        pattern = args.get("pattern", "*")
        found = []
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not (Path(directory) / d).is_symlink()
                             and not (hasattr(Path(directory) / d, "is_junction") and (Path(directory) / d).is_junction()))
            for name in sorted(files):
                path = Path(directory) / name
                try:
                    self.policy.resolve(str(path))
                except PermissionError:
                    continue
                relative = path.relative_to(self.context.workspace)
                if relative.match(pattern) or (pattern.startswith("**/") and relative.match(pattern[3:])):
                    found.append(relative.as_posix())
                if len(found) >= 1000:
                    return json.dumps({"paths": found, "truncated": True}, ensure_ascii=False)
        return json.dumps({"paths": found, "truncated": False}, ensure_ascii=False)

    async def search_text(self, args, call_id):
        paths = json.loads(await self.list_files({"path": args.get("path", "."), "pattern": args.get("glob", "*")}, call_id))["paths"]
        hits = []
        needle = args["pattern"]
        for path in paths[:500]:
            try:
                content = self.read_bytes(path).decode("utf-8-sig")
            except (ValueError, OSError, UnicodeError):
                continue
            for number, line in enumerate(content.splitlines(), 1):
                if needle.casefold() in line.casefold():
                    hits.append({"path": path, "line": number, "text": self.context.safe(line[:1000])})
                if len(hits) >= 100:
                    return json.dumps({"matches": hits, "truncated": True}, ensure_ascii=False)
        return json.dumps({"matches": hits, "truncated": False}, ensure_ascii=False)

    async def write_file(self, args, call_id):
        content = args["content"].encode("utf-8")
        return self._write(args["path"], content, call_id)

    async def edit_file(self, args, call_id):
        before = self.read_bytes(args["path"]).decode("utf-8")
        if not args["old_text"] or before.count(args["old_text"]) != 1:
            raise ValueError("old_text must match exactly once")
        return self._write(args["path"], before.replace(args["old_text"], args["new_text"], 1).encode("utf-8"), call_id)

    def _write(self, value: str, data: bytes, call_id: str):
        self.context.check()
        if self.context.task.scenario in {"research", "documents"}:
            raise PermissionError("This scenario preserves sources; use save_artifact or organize_document")
        path = self.policy.resolve(value)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("File exceeds 16 MiB")
        before = self.read_bytes(value) if path.exists() else None
        snapshot = None
        if before is not None:
            snapshot = self.history_dir / f"{self.context.task_id}-{hashlib.sha256(call_id.encode()).hexdigest()}.bin"
            snapshot.write_bytes(before)
        with self.context.repo.db.transaction() as conn:
            conn.execute(text("INSERT INTO file_history(task_id,call_id,path,before_hash,after_hash,snapshot) VALUES(:task,:call,:path,:before,:after,:snapshot)"),
                         {"task": self.context.task_id, "call": call_id, "path": str(path), "before": sha(before) if before is not None else None,
                          "after": sha(data), "snapshot": str(snapshot) if snapshot else None})
        path.parent.mkdir(parents=True, exist_ok=True)
        self.policy.resolve(value)
        handle, temporary = tempfile.mkstemp(prefix=".muse-write-", dir=path.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self.context.check()
            self.policy.resolve(value)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.context.cp["writes"] = self.context.cp.get("writes", 0) + 1
        self.context.cp["verification"] = None
        return json.dumps({"path": str(path.relative_to(self.context.workspace)), "sha256": sha(data), "bytes": len(data)})

    def rewind(self, task_id: str, call_id: str):
        rows = self.context.repo.db.rows("SELECT * FROM file_history WHERE task_id=:task AND call_id=:call", {"task": task_id, "call": call_id})
        if not rows:
            raise ValueError("Unknown file checkpoint")
        row = rows[0]
        path = self.policy.resolve(row["path"])
        if row["restored"] or not path.exists() or sha(self.read_bytes(str(path))) != row["after_hash"]:
            raise ValueError("File changed after the checkpoint; refusing to overwrite it")
        if row["snapshot"]:
            path.write_bytes(Path(row["snapshot"]).read_bytes())
        else:
            path.unlink()
        with self.context.repo.db.transaction() as conn:
            conn.execute(text("UPDATE file_history SET restored=1 WHERE task_id=:task AND call_id=:call"), {"task": task_id, "call": call_id})

    def reconcile(self, call_id: str, *, expected_revision: int):
        """Verify only our tracked file writes. Unknown commands never auto-replay."""
        repo, task_id = self.context.repo, self.context.task_id
        with repo.db.transaction() as conn:
            task = repo._task(conn, task_id)
            if task["status"] != "INTERRUPTED" or task["revision"] != expected_revision:
                raise ValueError("Task state or revision conflict")
            params = {"task": task_id, "call": call_id}
            call = conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task AND id=:call"), params).mappings().first()
            history = conn.execute(text("SELECT * FROM file_history WHERE task_id=:task AND call_id=:call"), params).mappings().first()
            if not call or call["status"] != "UNKNOWN" or call["name"] not in {"write_file", "edit_file"} or not history:
                raise ValueError("This side effect cannot be verified automatically; inspect it before creating a follow-up")
            if history["restored"] or sha(self.read_bytes(history["path"])) != history["after_hash"]:
                raise ValueError("File result cannot be verified; user changes were preserved")
            result = ToolResult(call_id=call_id, content=json.dumps({"path": str(Path(history["path"]).relative_to(self.context.workspace)), "sha256": history["after_hash"], "reconciled": True}))
            conn.execute(text("UPDATE tool_calls SET status='DONE',result=:result WHERE task_id=:task AND id=:call"), {**params, "result": result.model_dump_json()})
            checkpoint = json.loads(task["checkpoint"])
            checkpoint["writes"] = max(checkpoint.get("writes", 0), conn.execute(text("SELECT COUNT(*) FROM file_history WHERE task_id=:task"), params).scalar_one())
            checkpoint["verification"] = None
            conn.execute(text("UPDATE tasks SET checkpoint=:cp,revision=revision+1 WHERE id=:task"), {"cp": json.dumps(checkpoint), "task": task_id})
            repo._event(conn, task_id, "reconciled", {"call_id": call_id, "sha256": history["after_hash"]})
        return {"verified": True, "call_id": call_id}
