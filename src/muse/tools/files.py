from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from sqlalchemy import text

from muse.contracts import ToolResult
from muse.permissions.policy import WorkspacePolicy
from muse.tools.regex_search import FILE_TIMEOUT, SEARCH_TIMEOUT, RegexSession

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
        if 'offset' not in args and 'limit' not in args:
            return self.context.safe(content)
        offset, limit = args.get('offset', 0), args.get('limit', 2000)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 10000:
            return ToolResult(call_id=call_id, status='error', error_code='INVALID_ARGUMENTS',
                              content='offset must be a nonnegative integer; limit must be an integer from 1 to 10000')
        lines = self.context.safe_lines(content)
        end = min(offset + limit, len(lines))
        return json.dumps({'lines': [{'line': i + 1, 'text': self.context.safe(lines[i])}
                                     for i in range(offset, end)], 'offset': offset,
                           'next_offset': end if end < len(lines) else None,
                           'truncated': end < len(lines), 'total_lines': len(lines)}, ensure_ascii=False)

    async def list_files(self, args, call_id, *, deadline=None):
        stop = threading.Event()

        def collect():
            root = self.policy.resolve(args.get('path', '.'), must_exist=True)
            return self._list_paths(root, args.get('pattern', '*'), stop, deadline)

        pending = asyncio.create_task(asyncio.to_thread(collect))
        try:
            if deadline is None:
                return await self.context.controlled(pending)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Search time limit exceeded during candidate enumeration')
            return await self.context.controlled(asyncio.wait_for(pending, remaining))
        finally:
            stop.set()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    def _list_paths(self, root, pattern, stop, deadline):
        def check():
            if stop.is_set() or (deadline is not None and time.monotonic() >= deadline):
                raise TimeoutError('Search time limit exceeded during candidate enumeration')

        found = []
        for directory, dirs, files in os.walk(root, followlinks=False):
            check()
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not (Path(directory) / d).is_symlink()
                             and not (hasattr(Path(directory) / d, "is_junction") and (Path(directory) / d).is_junction()))
            for name in sorted(files):
                check()
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
        deadline = time.monotonic() + SEARCH_TIMEOUT
        paths = []
        hits = []
        needle = args["pattern"]
        session = RegexSession(self.context, deadline) if args.get('regex', False) else None
        limits = {'candidate_files': 500, 'matches': 100, 'file_timeout_ms': int(FILE_TIMEOUT * 1000),
                  'search_timeout_ms': int(SEARCH_TIMEOUT * 1000)}
        processed, skipped = 0, 0

        def result(reason=None):
            return json.dumps({'matches': hits, 'truncated': reason is not None,
                               'truncation_reason': reason, 'limits': limits,
                               'processed_files': processed, 'skipped_files': skipped}, ensure_ascii=False)

        try:
            listing = json.loads(await self.list_files(
                {'path': args.get('path', '.'), 'pattern': args.get('glob', '*')}, call_id, deadline=deadline))
            paths = listing['paths']
            if session:
                try:
                    await session.start(needle, args.get('case_sensitive', False))
                except ValueError as error:
                    return ToolResult(call_id=call_id, status='error', error_code='INVALID_ARGUMENTS',
                                      content=self.context.safe(str(error)))
            for path in paths[:500]:
                await asyncio.sleep(0)
                self.context.check()
                if time.monotonic() >= deadline:
                    raise TimeoutError('Search time limit exceeded')
                try:
                    content = self.read_bytes(path).decode('utf-8-sig')
                except (ValueError, OSError, UnicodeError):
                    skipped += 1
                    continue
                if session:
                    matches = await session.matches(content, 100 - len(hits))
                else:
                    sensitive = args.get('case_sensitive', False)
                    query = needle if sensitive else needle.casefold()
                    matches = []
                    for number, line in enumerate(content.splitlines(), 1):
                        if query in (line if sensitive else line.casefold()):
                            matches.append({'line': number, 'text': line[:1000]})
                        if len(matches) >= 100 - len(hits):
                            break
                        if number % 1000 == 0:
                            self.context.check()
                            if time.monotonic() >= deadline:
                                raise TimeoutError('Search time limit exceeded')
                safe_lines = self.context.safe_lines(content) if matches else []
                hits.extend({'path': path, 'line': match['line'], 'text': safe_lines[match['line'] - 1][:1000]}
                            for match in matches)
                processed += 1
                if len(hits) >= 100:
                    return result('match_limit')
            return result('candidate_limit' if len(paths) > 500 or listing['truncated'] else None)
        except TimeoutError:
            return ToolResult(call_id=call_id, status='error', error_code='SEARCH_TIMEOUT',
                              content=result('timeout'), metadata={'limits': limits})
        finally:
            if session:
                await session.close()

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
