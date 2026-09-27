from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from sqlalchemy import text

from muse.contracts import TERMINAL, TaskRecord, TaskRequest
from muse.storage.database import Database
from muse.tasks.conversation import ConversationMixin
from muse.tasks.delegation import DelegationMixin
from muse.tasks.teams import TeamMixin


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def timestamp(value: float | None) -> float:
    return time.time() if value is None else value


_NO_CHANGES = re.compile(
    r'\bwithout (?:changing|modifying|editing|writing|altering) (?:any |the )?(?:files?|code|project)\b'
    r'|\bdo not (?:change|modify|edit|write|alter) (?:any |the )?(?:files?|code|project)\b'
    r'|^\s*(?:please )?(?:read[- ]only|analyze only)\b'
    r'|^\s*(?:请)?只读(?:分析|查看|检查)'
    r'|(?:不要|不|请勿)(?:修改|改动|编辑|写入)(?:任何)?(?:文件|代码|项目)',
    re.IGNORECASE,
)


def explicit_read_only(prompt: str) -> bool:
    """Honor unambiguous no-write instructions even when the client omits the flag."""
    match = _NO_CHANGES.search(prompt)
    if not match:
        return False
    # A no-write instruction for an inspection phase must not disable later
    # requested repairs. Ambiguous task-wide intent remains writable.
    later = prompt[match.end():]
    return not bool(re.search(r'(?:\b(?:then|afterwards|next|subsequently)\b|然后|随后|接着).{0,120}'
                              r'(?:\b(?:fix|edit|modify|change|implement|write|update|repair)\b|修复|修改|改动|编辑|写入|实现)',
                              later, re.IGNORECASE | re.DOTALL))


def row_task(row) -> TaskRecord:
    value = dict(row)
    value["checkpoint"] = json.loads(value["checkpoint"])
    return TaskRecord(**value)


class TaskRepository(DelegationMixin, TeamMixin, ConversationMixin):
    def __init__(self, path: Path):
        self.db = Database(path)

    def register_workspace(self, path: str, name: str = "Workspace") -> dict:
        try:
            resolved = Path(path).resolve(strict=True)
        except OSError:
            raise ValueError("Workspace must be an existing accessible directory") from None
        if not resolved.is_dir():
            raise ValueError("workspace must be an existing directory")
        with self.db.transaction() as conn:
            existing = conn.execute(text("SELECT * FROM workspaces WHERE path=:path"), {"path": str(resolved)}).mappings().first()
            if existing:
                return dict(existing)
            data = {"id": uuid.uuid4().hex, "name": name, "path": str(resolved), "created_at": time.time()}
            conn.execute(text("INSERT INTO workspaces(id,name,path,created_at) VALUES(:id,:name,:path,:created_at)"), data)
            return data

    def workspaces(self) -> list[dict]:
        return self.db.rows("SELECT * FROM workspaces ORDER BY created_at")

    def workspace(self, workspace_id: str) -> dict:
        rows = self.db.rows("SELECT * FROM workspaces WHERE id=:id", {"id": workspace_id})
        if not rows:
            raise ValueError("Unknown workspace")
        return rows[0]

    @staticmethod
    def _task(conn, task_id: str) -> dict:
        row = conn.execute(text("SELECT * FROM tasks WHERE id=:id"), {"id": task_id}).mappings().first()
        if row is None:
            raise ValueError("Unknown task")
        return dict(row)

    @staticmethod
    def _event(conn, task_id: str, kind: str, payload: dict, now: float | None = None):
        conn.execute(text("UPDATE tasks SET event_sequence=event_sequence+1 WHERE id=:id"), {"id": task_id})
        sequence = conn.execute(text("SELECT event_sequence FROM tasks WHERE id=:id"), {"id": task_id}).scalar_one()
        conn.execute(text("INSERT INTO events(task_id,sequence,type,payload,created_at) VALUES(:id,:sequence,:type,:payload,:now)"),
                     {"id": task_id, "sequence": sequence, "type": kind, "payload": encode(payload), "now": timestamp(now)})

    @staticmethod
    def _state(conn, task_id: str, status: str, now: float, **fields):
        allowed = {"lease_owner", "lease_until", "cancel_requested", "pause_requested", "error", "result"}
        if fields.keys() - allowed:
            raise ValueError("Invalid task field")
        values = {"id": task_id, "status": status, "now": now, **fields}
        extras = "".join(f", {key}=:{key}" for key in fields)
        conn.execute(text(f"UPDATE tasks SET status=:status,revision=revision+1,updated_at=:now{extras} WHERE id=:id"), values)
        if status in TERMINAL:
            items = conn.execute(text("SELECT id,root_id FROM team_work_items WHERE owner_id=:id AND status='in_progress'"), {'id': task_id}).mappings().all()
            for item in items:
                conn.execute(text("UPDATE team_work_items SET owner_id=NULL,status='pending',revision=revision+1,updated_at=:now WHERE id=:id"), {'id': item['id'], 'now': now})
                TaskRepository._event(conn, item['root_id'], 'team_work_released', {'item_id': item['id'], 'previous_owner': task_id, 'reason': status}, now)
        TaskRepository._event(conn, task_id, "status", {"status": status}, now)

    @staticmethod
    def _lease(conn, task_id: str, owner: str, epoch: int, now: float) -> dict:
        task = TaskRepository._task(conn, task_id)
        if task["status"] != "RUNNING" or task["lease_owner"] != owner or task["lease_epoch"] != epoch or (task["lease_until"] or 0) <= now:
            raise ValueError("Worker lease is no longer valid")
        return task

    def create(self, request: TaskRequest) -> TaskRecord:
        if not request.read_only and explicit_read_only(request.prompt):
            request = request.model_copy(update={'read_only': True})
        now = time.time()
        with self.db.transaction() as conn:
            old = conn.execute(text("SELECT * FROM tasks WHERE client_request_id=:key"), {"key": request.client_request_id}).mappings().first()
            if old:
                previous = row_task(old)
                if any(getattr(previous, key) != value for key, value in request.model_dump().items()):
                    raise ValueError("client_request_id already belongs to another request")
                return previous
            if not conn.execute(text("SELECT id FROM workspaces WHERE id=:id"), {"id": request.workspace_id}).first():
                raise ValueError("Unknown workspace")
            if request.parent_task_id:
                parent = self._task(conn, request.parent_task_id)
                if parent["workspace_id"] != request.workspace_id or parent["status"] not in TERMINAL:
                    raise ValueError("Follow-up requires a terminal parent in the same workspace")
            data = {**request.model_dump(), "id": uuid.uuid4().hex, "now": now}
            conn.execute(text("""INSERT INTO tasks(id,prompt,workspace_id,scenario,client_request_id,parent_task_id,status,created_at,updated_at,read_only)
                VALUES(:id,:prompt,:workspace_id,:scenario,:client_request_id,:parent_task_id,'QUEUED',:now,:now,:read_only)"""), data)
            self._event(conn, data["id"], "status", {"status": "QUEUED"}, now)
            return row_task(self._task(conn, data["id"]))

    def get(self, task_id: str) -> TaskRecord:
        rows = self.db.rows("SELECT * FROM tasks WHERE id=:id", {"id": task_id})
        if not rows:
            raise ValueError("Unknown task")
        return row_task(rows[0])

    def list(self) -> list[TaskRecord]:
        return [row_task(row) for row in self.db.rows("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 500")]

    def claim_next(self, worker_id: str, *, now: float | None = None, ttl: float = 30) -> TaskRecord | None:
        now = timestamp(now)
        with self.db.transaction() as conn:
            row = conn.execute(text("SELECT id FROM tasks WHERE status='QUEUED' AND cancel_requested=0 ORDER BY created_at LIMIT 1")).first()
            if not row:
                return None
            task_id = row[0]
            conn.execute(text("UPDATE tasks SET lease_epoch=lease_epoch+1 WHERE id=:id"), {"id": task_id})
            self._state(conn, task_id, "RUNNING", now, lease_owner=worker_id, lease_until=now + ttl)
            return row_task(self._task(conn, task_id))

    def heartbeat(self, task_id: str, owner: str, epoch: int, *, ttl: float = 30, now: float | None = None):
        now = timestamp(now)
        with self.db.transaction() as conn:
            self._lease(conn, task_id, owner, epoch, now)
            conn.execute(text("UPDATE tasks SET lease_until=:until WHERE id=:id"), {"until": now + ttl, "id": task_id})

    def checkpoint(self, task_id: str, owner: str, epoch: int, checkpoint: dict, *, now: float | None = None):
        now = timestamp(now)
        with self.db.transaction() as conn:
            self._lease(conn, task_id, owner, epoch, now)
            conn.execute(text("UPDATE tasks SET checkpoint=:checkpoint,updated_at=:now WHERE id=:id"),
                         {"checkpoint": encode(checkpoint), "now": now, "id": task_id})

    def finish(self, task_id: str, owner: str, epoch: int, status: str, result: str = "", error: str = ""):
        if status not in TERMINAL | {"WAITING_INPUT", "PAUSED", "INTERRUPTED"}:
            raise ValueError("Invalid finish status")
        now = time.time()
        with self.db.transaction() as conn:
            task = self._lease(conn, task_id, owner, epoch, now)
            if task["cancel_requested"]:
                status = "CANCELLED"
            if status in {'CANCELLED', 'FAILED'}:
                self._cancel_descendants(conn, task_id, now)
            self._state(conn, task_id, status, now, result=result, error=error, lease_owner=None, lease_until=None)

    def control(self, task_id: str, action: str, *, expected_revision: int, content: str = "") -> TaskRecord:
        now = time.time()
        with self.db.transaction() as conn:
            task = self._task(conn, task_id)
            if task["revision"] != expected_revision:
                raise ValueError("Task revision conflict")
            status = task["status"]
            if action in {'compact', 'reload'}:
                if status not in {'QUEUED', 'PAUSED'}:
                    raise ValueError('Context changes require a queued or paused task')
                cp = json.loads(task['checkpoint'])
                if cp.get('pending_calls') or cp.get('usage_pending'):
                    raise ValueError('Finish pending tool/model calls before changing context')
                if action == 'reload':
                    cp.pop('project_guidance', None)
                elif cp.get('messages'):
                    from muse.agent.context import compact_messages
                    if len(encode(cp['messages'])) > 8 * 1024 * 1024:
                        raise ValueError('Conversation checkpoint exceeds limit')
                    conn.execute(text('INSERT INTO conversation_archives(task_id,revision,sequence,messages,created_at) VALUES(:task,:revision,:sequence,:messages,:now)'),
                                 {'task': task_id, 'revision': task['revision'], 'sequence': cp.get('model_requests', 0), 'messages': encode(cp['messages']), 'now': now})
                    conn.execute(text('INSERT OR IGNORE INTO conversation_checkpoints(task_id,sequence,messages,created_at) VALUES(:task,:sequence,:messages,:now)'),
                                 {'task': task_id, 'sequence': cp.get('model_requests', 0), 'messages': encode(cp['messages']), 'now': now})
                    cp['messages'] = compact_messages(cp['messages'], max_chars=12000)
                    cp.setdefault('pending_hook_events', []).append(['compact', 'manual:' + str(task['revision'])])
                conn.execute(text('UPDATE tasks SET checkpoint=:cp WHERE id=:id'), {'id': task_id, 'cp': encode(cp)})
                self._state(conn, task_id, status, now)
                self._event(conn, task_id, 'context_updated', {'action': action}, now)
                return row_task(self._task(conn, task_id))
            if status in TERMINAL:
                raise ValueError("Terminal tasks cannot be resumed; create a follow-up")
            if action == "cancel":
                self._cancel_descendants(conn, task_id, now)
                self._state(conn, task_id, "RUNNING" if status == "RUNNING" else "CANCELLED", now, cancel_requested=1)
            elif action == "pause" and status in {"QUEUED", "RUNNING"}:
                self._state(conn, task_id, "RUNNING" if status == "RUNNING" else "PAUSED", now, pause_requested=1)
            elif action == "resume" and status in {"PAUSED", "INTERRUPTED"}:
                unknown = conn.execute(text("SELECT id FROM tool_calls WHERE task_id=:id AND status='UNKNOWN'"), {"id": task_id}).first()
                if unknown:
                    raise ValueError("Uncertain side effects require reconciliation before resume")
                self._state(conn, task_id, "QUEUED", now, pause_requested=0, lease_owner=None, lease_until=None)
            elif action == "input" and status == "WAITING_INPUT" and content.strip():
                cp = json.loads(task["checkpoint"])
                cp.pop("input_question", None)
                cp.setdefault("messages", []).append({"role": "user", "content": content})
                conn.execute(text("UPDATE tasks SET checkpoint=:cp WHERE id=:id"), {"cp": encode(cp), "id": task_id})
                self._state(conn, task_id, "QUEUED", now)
            else:
                raise ValueError("Action is not valid in the current task state")
            return row_task(self._task(conn, task_id))

    def add_event(self, task_id: str, kind: str, payload: dict):
        with self.db.transaction() as conn:
            self._task(conn, task_id)
            self._event(conn, task_id, kind, payload)

    def events(self, task_id: str, after: int = 0) -> list[dict]:
        rows = self.db.rows("SELECT * FROM events WHERE task_id=:id AND sequence>:after ORDER BY sequence LIMIT 1000", {"id": task_id, "after": after})
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows

    def prepare_call(self, task_id: str, owner: str, epoch: int, call_id: str, name: str, arguments: dict, risk: str, *, now: float | None = None) -> dict:
        now = timestamp(now)
        with self.db.transaction() as conn:
            task = self._lease(conn, task_id, owner, epoch, now)
            if task["cancel_requested"]:
                raise ValueError("Task has been cancelled")
            digest = hashlib.sha256(encode([task_id, task["workspace_id"], name, arguments]).encode()).hexdigest()
            params = {"task_id": task_id, "id": call_id, "name": name, "arguments": encode(arguments), "risk": risk, "digest": digest, "now": now}
            old = conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task_id AND id=:id"), params).mappings().first()
            if old:
                if old["digest"] != digest:
                    raise ValueError("Tool call ID reused with different arguments")
                return dict(old)
            conn.execute(text("""INSERT INTO tool_calls(task_id,id,name,arguments,risk,status,digest,created_at,updated_at)
                VALUES(:task_id,:id,:name,:arguments,:risk,'PREPARED',:digest,:now,:now)"""), params)
            self._event(conn, task_id, "tool_prepared", {"call_id": call_id, "name": name, "arguments": arguments}, now)
            return dict(conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task_id AND id=:id"), params).mappings().one())

    def begin_call(self, task_id: str, owner: str, epoch: int, call_id: str, *, now: float | None = None, max_calls: int = 10000) -> bool:
        now = timestamp(now)
        with self.db.transaction() as conn:
            task = self._lease(conn, task_id, owner, epoch, now)
            if task["cancel_requested"] or task["pause_requested"]:
                raise ValueError("Task control request prevents new tool dispatch")
            params = {"task_id": task_id, "id": call_id}
            call = conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task_id AND id=:id"), params).mappings().one()
            if call["status"] in {"DONE", "FAILED"}:
                return False
            if call["status"] != "PREPARED":
                raise ValueError("Tool call is already executing or has uncertain side effects")
            attempts = sum(conn.execute(text("SELECT COALESCE(SUM(attempts),0) FROM tool_calls WHERE task_id=:id"), {"id": identifier}).scalar_one()
                           for identifier in self._group_ids(conn, task_id))
            frozen = conn.execute(text('SELECT max_tool_calls FROM execution_budgets WHERE root_id=:root'),
                                  {'root': self._root_id(conn, task_id)}).scalar()
            if frozen is not None:
                max_calls = min(max_calls, frozen)
            if attempts >= max_calls:
                raise ValueError("Tool call budget exhausted")
            if call["risk"] == "execute":
                approved = conn.execute(text("SELECT id FROM approvals WHERE task_id=:task_id AND tool_call_id=:id AND action_digest=:digest AND status='APPROVED' AND expires_at>:now"),
                                        {**params, "digest": call["digest"], "now": now}).first()
                if not approved:
                    raise ValueError("Tool execution requires current approval")
            conn.execute(text("UPDATE tool_calls SET status='EXECUTING',attempts=attempts+1,updated_at=:now WHERE task_id=:task_id AND id=:id"), {**params, "now": now})
            self._event(conn, task_id, "tool_started", {"call_id": call_id, "name": call["name"]}, now)
            return True

    def complete_call(self, task_id: str, owner: str, epoch: int, call_id: str, result: dict):
        now = time.time()
        with self.db.transaction() as conn:
            self._lease(conn, task_id, owner, epoch, now)
            params = {"task_id": task_id, "id": call_id, "result": encode(result), "now": now,
                      "status": "DONE" if result.get("status") == "success" else "FAILED"}
            updated = conn.execute(text("UPDATE tool_calls SET status=:status,result=:result,updated_at=:now WHERE task_id=:task_id AND id=:id AND status='EXECUTING'"), params)
            if updated.rowcount != 1:
                raise ValueError("Only an executing call can be completed")
            self._event(conn, task_id, "tool_result", {"call_id": call_id, **result}, now)

    def calls(self, task_id: str) -> list[dict]:
        rows = self.db.rows("SELECT * FROM tool_calls WHERE task_id=:id ORDER BY created_at", {"id": task_id})
        for row in rows:
            row["arguments"] = json.loads(row["arguments"])
            row["result"] = json.loads(row["result"]) if row["result"] else None
        return rows

    def request_approval(self, task_id: str, owner: str, epoch: int, call_id: str) -> dict:
        now = time.time()
        with self.db.transaction() as conn:
            self._lease(conn, task_id, owner, epoch, now)
            call = conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task AND id=:call"), {"task": task_id, "call": call_id}).mappings().one()
            data = {"id": uuid.uuid4().hex, "task_id": task_id, "call": call_id, "digest": call["digest"], "expires": now + 3600, "now": now}
            conn.execute(text("""INSERT INTO approvals(id,task_id,tool_call_id,action_digest,status,expires_at,created_at)
                VALUES(:id,:task_id,:call,:digest,'PENDING',:expires,:now)
                ON CONFLICT(task_id,tool_call_id,action_digest) DO UPDATE SET status='PENDING',expires_at=excluded.expires_at"""), data)
            self._state(conn, task_id, "WAITING_APPROVAL", now, lease_owner=None, lease_until=None)
            self._event(conn, task_id, "approval_required", {"call_id": call_id, "name": call["name"], "arguments": json.loads(call["arguments"])}, now)
            return dict(conn.execute(text("SELECT * FROM approvals WHERE task_id=:task_id AND tool_call_id=:call"), data).mappings().one())

    def approvals(self, task_id: str | None = None) -> list[dict]:
        clause = "WHERE a.task_id=:task" if task_id else ""
        rows = self.db.rows(f"""SELECT a.*,c.name,c.arguments FROM approvals a JOIN tool_calls c
            ON a.task_id=c.task_id AND a.tool_call_id=c.id {clause} ORDER BY a.created_at""", {"task": task_id})
        for row in rows:
            row["arguments"] = json.loads(row["arguments"])
        return rows

    def tool_attempts(self, task_id: str) -> int:
        return self.db.rows("SELECT COALESCE(SUM(attempts),0) AS total FROM tool_calls WHERE task_id=:id", {"id": task_id})[0]["total"]

    def renew_approval(self, approval_id: str, action_digest: str):
        """Extend an expired review window; never approve or queue the action."""
        now = time.time()
        with self.db.transaction() as conn:
            row = conn.execute(text('SELECT * FROM approvals WHERE id=:id'), {'id': approval_id}).mappings().first()
            if not row:
                raise ValueError('Unknown approval')
            if row['action_digest'] != action_digest:
                raise ValueError('Approval digest mismatch')
            if row['status'] != 'PENDING' or row['expires_at'] > now:
                raise ValueError('Only an expired pending approval can be renewed')
            task = self._task(conn, row['task_id'])
            if task['status'] != 'WAITING_APPROVAL' or task['cancel_requested']:
                raise ValueError('Task is not waiting for approval')
            call = conn.execute(text('SELECT digest,status FROM tool_calls WHERE task_id=:task AND id=:call'),
                                {'task': row['task_id'], 'call': row['tool_call_id']}).mappings().one()
            if call['digest'] != action_digest or call['status'] != 'PREPARED':
                raise ValueError('Approval no longer matches a prepared action')
            expires = now + 3600
            conn.execute(text('UPDATE approvals SET expires_at=:expires WHERE id=:id'), {'expires': expires, 'id': approval_id})
            self._event(conn, row['task_id'], 'approval_renewed', {'approval_id': approval_id,
                        'action_digest': action_digest, 'previous_expires_at': row['expires_at'], 'expires_at': expires}, now)
            return {**dict(row), 'expires_at': expires}

    def reconcile_external(self, task_id, call_id, digest, revision, successful, explanation):
        from muse.contracts import ToolResult
        if not explanation.strip() or len(explanation) > 4000:
            raise ValueError('A reconciliation explanation is required')
        with self.db.transaction() as conn:
            task = self._task(conn, task_id)
            if task['revision'] != revision or task['status'] != 'INTERRUPTED':
                raise ValueError('Reconciliation requires an interrupted task and current revision')
            call = conn.execute(text('SELECT * FROM tool_calls WHERE task_id=:task AND id=:call'),
                                {'task': task_id, 'call': call_id}).mappings().first()
            if not call or call['digest'] != digest:
                raise ValueError('Action digest mismatch')
            if call['status'] != 'UNKNOWN' or call['risk'] != 'execute':
                raise ValueError('Only uncertain external actions can be reconciled here')
            result = ToolResult(call_id=call_id, status='success' if successful else 'error',
                content='User reconciled external action: ' + explanation,
                metadata={'reconciled': True, 'verified': False}).model_dump()
            conn.execute(text('UPDATE tool_calls SET status=:status,result=:result,updated_at=:now WHERE task_id=:task AND id=:call'),
                         {'task': task_id, 'call': call_id, 'status': 'DONE' if successful else 'FAILED',
                          'result': encode(result), 'now': time.time()})
            self._state(conn, task_id, 'INTERRUPTED', time.time())
            self._event(conn, task_id, 'external_action_reconciled', {'call_id': call_id, 'result': result})
            return result

    def decide_approval(self, approval_id: str, allow: bool, action_digest: str):
        now = time.time()
        with self.db.transaction() as conn:
            row = conn.execute(text("SELECT * FROM approvals WHERE id=:id"), {"id": approval_id}).mappings().first()
            if not row:
                raise ValueError("Unknown approval")
            if row["action_digest"] != action_digest:
                raise ValueError("Approval digest mismatch")
            status = "APPROVED" if allow else "DENIED"
            if row["status"] == status:
                return dict(row)
            if row["status"] != "PENDING" or row["expires_at"] <= now:
                raise ValueError("Approval is expired or already decided")
            task = self._task(conn, row["task_id"])
            if task["status"] != "WAITING_APPROVAL":
                raise ValueError("Task is not waiting for approval")
            call = conn.execute(text("SELECT digest FROM tool_calls WHERE task_id=:task AND id=:call"), {"task": row["task_id"], "call": row["tool_call_id"]}).scalar_one()
            if call != action_digest:
                raise ValueError("Approval digest no longer matches the action")
            conn.execute(text("UPDATE approvals SET status=:status WHERE id=:id"), {"status": status, "id": approval_id})
            self._event(conn, row["task_id"], "approval_decided", {"approval_id": approval_id, "status": status})
            self._state(conn, row["task_id"], "QUEUED", now)
            return {**dict(row), "status": status}

    def recover_expired_tasks(self, *, now: float | None = None) -> list[str]:
        now = timestamp(now)
        recovered = []
        with self.db.transaction() as conn:
            tasks = conn.execute(text("SELECT * FROM tasks WHERE status='RUNNING' AND lease_until<=:now"), {"now": now}).mappings().all()
            for task in tasks:
                task_id = task["id"]
                checkpoint = json.loads(task['checkpoint'])
                checkpoint['active_seconds'] = float(checkpoint.get('active_seconds', 0)) + max(0, min(now, task['lease_until'] or now) - task['updated_at'])
                conn.execute(text('UPDATE tasks SET checkpoint=:cp WHERE id=:id'), {'id': task_id, 'cp': encode(checkpoint)})
                self._reconcile_spawn_calls(conn, task_id, now)
                unknown = conn.execute(text("SELECT id FROM tool_calls WHERE task_id=:id AND status='EXECUTING' AND risk!='read'"), {"id": task_id}).first()
                conn.execute(text("UPDATE tool_calls SET status=CASE WHEN risk='read' THEN 'PREPARED' ELSE 'UNKNOWN' END WHERE task_id=:id AND status='EXECUTING'"), {"id": task_id})
                self._state(conn, task_id, "INTERRUPTED", now, lease_owner=None, lease_until=None,
                            error="Side effect needs reconciliation" if unknown else "Worker interrupted")
                if task["cancel_requested"] and not unknown:
                    self._state(conn, task_id, "CANCELLED", now)
                elif not unknown:
                    self._state(conn, task_id, "PAUSED" if task["pause_requested"] else "QUEUED", now)
                recovered.append(task_id)
        return recovered

    def abandon(self, task_id: str, owner: str, epoch: int):
        with self.db.transaction() as conn:
            conn.execute(text("UPDATE tasks SET lease_until=0 WHERE id=:id AND lease_owner=:owner AND lease_epoch=:epoch AND status='RUNNING'"),
                         {"id": task_id, "owner": owner, "epoch": epoch})
        self.recover_expired_tasks()
