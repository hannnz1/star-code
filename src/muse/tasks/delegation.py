"""Durable delegation, bounded by the originating task's shared budgets."""
import json
import time
import uuid
from contextlib import nullcontext

from sqlalchemy import text

from muse.contracts import TERMINAL, TaskRecord


class DelegationMixin:
    def bind_budgets(self, task_id, owner, epoch, limits):
        """Freeze the root limits across restart and delegation; later workers may only tighten them."""
        with self.db.transaction() as conn:
            self._lease(conn, task_id, owner, epoch, time.time())
            root = self._root_id(conn, task_id)
            prior = sum(json.loads(self._task(conn, identifier)['checkpoint']).get('model_requests', 0)
                        for identifier in self._group_ids(conn, task_id))
            conn.execute(text('INSERT OR IGNORE INTO execution_budgets(root_id,model_requests) VALUES(:root,:prior)'), {'root': root, 'prior': prior})
            row = conn.execute(text('SELECT * FROM execution_budgets WHERE root_id=:root'), {'root': root}).mappings().one()
            bound = {name: min(limits[name], row[name]) if row[name] is not None else limits[name]
                     for name in ('max_turns', 'max_tool_calls', 'max_active_seconds')}
            conn.execute(text('UPDATE execution_budgets SET max_turns=:max_turns,max_tool_calls=:max_tool_calls,max_active_seconds=:max_active_seconds WHERE root_id=:root'), {**bound, 'root': root})
            return bound

    def _reconcile_spawn_calls(self, conn, task_id, now):
        """The delegation row is the receipt for this database-only operation.

        Never use this path for external commands or arbitrary extension actions.
        """
        from muse.contracts import ToolResult
        rows = conn.execute(text('''SELECT c.id,c.name,c.arguments,t.id AS child_id,t.status AS child_status
            FROM tool_calls c JOIN task_delegations d ON d.parent_id=c.task_id AND d.call_id=c.id
            JOIN tasks t ON t.id=d.child_id
            WHERE c.task_id=:task AND c.status='EXECUTING' '''),
            {'task': task_id}).mappings().all()
        for row in rows:
            args = json.loads(row['arguments'])
            preview = args.get('action_preview', {})
            hook = row['name'].startswith('__hook_') and (preview.get('type') == 'agent' or preview.get('async') is True)
            if row['name'] not in {'spawn_task', 'spawn_skill', 'spawn_worktree'} and not hook:
                continue
            metadata = {'hook_once_key': row['name'] + ':' + args['_source']} if hook else {}
            if hook and preview.get('async') is True:
                metadata['hook_child_id'] = row['child_id']
            result = ToolResult(call_id=row['id'], content=json.dumps({'id': row['child_id'], 'child_id': row['child_id'], 'status': row['child_status']}), metadata=metadata).model_dump()
            conn.execute(text("UPDATE tool_calls SET status='DONE',result=:result,updated_at=:now WHERE task_id=:task AND id=:id"),
                         {'task': task_id, 'id': row['id'], 'result': json.dumps(result), 'now': now})
            self._event(conn, task_id, 'tool_result', {'call_id': row['id'], **result}, now)
        for call in conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task AND status='EXECUTING' AND name IN ('team_work','team_message')"), {'task': task_id}).mappings().all():
            args = json.loads(call['arguments'])
            if call['name'] == 'team_work':
                receipt = conn.execute(text('SELECT * FROM team_work_actions WHERE task_id=:task AND call_id=:call'),
                                       {'task': task_id, 'call': call['id']}).mappings().first()
                if not receipt or json.loads(receipt['arguments']) != args:
                    continue
                content = receipt['result']
            else:
                receipt = conn.execute(text('SELECT * FROM team_messages WHERE sender_id=:task AND call_id=:call'),
                                       {'task': task_id, 'call': call['id']}).mappings().first()
                if not receipt or receipt['recipient_id'] != args.get('recipient_id') or receipt['message'] != args.get('message'):
                    continue
                content = json.dumps(dict(receipt))
            result = ToolResult(call_id=call['id'], content=content).model_dump()
            conn.execute(text("UPDATE tool_calls SET status='DONE',result=:result,updated_at=:now WHERE task_id=:task AND id=:id"),
                         {'task': task_id, 'id': call['id'], 'result': json.dumps(result), 'now': now})
            self._event(conn, task_id, 'tool_result', {'call_id': call['id'], **result}, now)

    @staticmethod
    def _root_id(conn, task_id):
        row = conn.execute(text('SELECT root_id FROM task_delegations WHERE child_id=:id'), {'id': task_id}).first()
        return row[0] if row else task_id

    @classmethod
    def _group_ids(cls, conn, task_id):
        root = cls._root_id(conn, task_id)
        return [root] + list(conn.execute(text('SELECT child_id FROM task_delegations WHERE root_id=:root'), {'root': root}).scalars())

    def reserve_model_request(self, task_id, owner, epoch, maximum):
        with self.db.transaction() as conn:
            task = self._lease(conn, task_id, owner, epoch, time.time())
            if task['cancel_requested'] or task['pause_requested']:
                raise ValueError('Task control prevents a model request')
            root = self._root_id(conn, task_id)
            prior = sum(json.loads(self._task(conn, identifier)['checkpoint']).get('model_requests', 0)
                        for identifier in self._group_ids(conn, task_id))
            conn.execute(text('INSERT OR IGNORE INTO execution_budgets(root_id,model_requests) VALUES(:root,:prior)'), {'root': root, 'prior': prior})
            budget = conn.execute(text('SELECT model_requests,max_turns FROM execution_budgets WHERE root_id=:root'), {'root': root}).mappings().one()
            count = budget['model_requests']
            maximum = min(maximum, budget['max_turns']) if budget['max_turns'] is not None else maximum
            if count >= maximum:
                raise ValueError('Shared model request budget exhausted')
            conn.execute(text('UPDATE execution_budgets SET model_requests=model_requests+1 WHERE root_id=:root'), {'root': root})

    def group_active_seconds(self, task_id):
        with self.db.engine.connect() as conn:
            ids = self._group_ids(conn, task_id)
            total = 0.0
            now = time.time()
            for identifier in ids:
                if identifier == task_id:
                    continue
                task = self._task(conn, identifier)
                total += float(json.loads(task['checkpoint']).get('active_seconds', 0))
                if task['status'] == 'RUNNING':
                    total += max(0, min(now, task['lease_until'] or now) - task['updated_at'])
            return total

    def spawn_child(self, parent_id, owner, epoch, call_id, prompt, *, workspace_id=None, capabilities=None, _connection=None):
        now = time.time()
        with (nullcontext(_connection) if _connection is not None else self.db.transaction()) as conn:
            parent = self._lease(conn, parent_id, owner, epoch, now)
            if parent['cancel_requested']:
                raise ValueError('Parent was cancelled')
            capabilities = capabilities or {}
            parent_cp = json.loads(parent['checkpoint'])
            child_cp = {}
            if 'sandbox' in parent_cp:
                child_cp['sandbox'] = parent_cp['sandbox']
            if not workspace_id or workspace_id == parent['workspace_id']:
                for key in ('project_guidance', 'role_snapshot', 'source_version', 'current_directory'):
                    if key in parent_cp:
                        child_cp[key] = parent_cp[key]
            child_cp['suppressed_hooks'] = sorted(set(parent_cp.get('suppressed_hooks', []) + capabilities.get('suppressed_hooks', [])))
            allowed = capabilities.get('allowed_tools', parent_cp.get('allowed_tools'))
            if allowed is not None:
                if not isinstance(allowed, list) or any(not isinstance(name, str) for name in allowed):
                    raise ValueError('Invalid delegated tool restrictions')
                if parent_cp.get('allowed_tools') is not None:
                    allowed = [name for name in allowed if name in parent_cp['allowed_tools']]
                child_cp['allowed_tools'] = sorted(set(allowed))
            local_limit = capabilities.get('max_local_turns', parent_cp.get('max_local_turns'))
            if local_limit is not None:
                if isinstance(local_limit, bool) or not isinstance(local_limit, int) or local_limit <= 0:
                    raise ValueError('Invalid delegated turn limit')
                child_cp['max_local_turns'] = min(local_limit, parent_cp.get('max_local_turns', local_limit))
            if capabilities.get('role'):
                child_cp['role'] = capabilities['role']
            if capabilities.get('commerce'):
                child_cp['commerce'] = capabilities['commerce']
            if capabilities.get('hook_job'):
                child_cp['hook_job'] = capabilities['hook_job']
            existing = conn.execute(text('SELECT child_id FROM task_delegations WHERE parent_id=:p AND call_id=:c'), {'p': parent_id, 'c': call_id}).first()
            if existing:
                child = self._task(conn, existing[0])
                if child['prompt'] != prompt or child['workspace_id'] != (workspace_id or parent['workspace_id']):
                    raise ValueError('Delegation call reused with a different prompt')
                return self._child_record(child)
            root = self._root_id(conn, parent_id)
            if len(self._group_ids(conn, parent_id)) >= 17:
                raise ValueError('A task may have at most 16 descendants')
            depth = 0
            cursor = parent_id
            while cursor != root:
                cursor = conn.execute(text('SELECT parent_id FROM task_delegations WHERE child_id=:id'), {'id': cursor}).scalar_one()
                depth += 1
            if depth >= 4:
                raise ValueError('Delegation depth limit reached')
            if workspace_id and workspace_id != parent['workspace_id'] and self.snapshot_factory:
                from muse.contracts import TaskRequest
                workspace = dict(conn.execute(text('SELECT * FROM workspaces WHERE id=:id'), {'id': workspace_id}).mappings().one())
                request = TaskRequest(prompt=prompt, workspace_id=workspace_id, client_request_id='snapshot')
                snapshot = self.snapshot_factory(request, workspace)
                for key in ('project_guidance', 'role_snapshot', 'source_version', 'current_directory'):
                    if key in snapshot:
                        child_cp[key] = snapshot[key]
            child_id = uuid.uuid4().hex
            conn.execute(text('''INSERT INTO tasks(id,prompt,workspace_id,scenario,client_request_id,status,created_at,updated_at,read_only,checkpoint,permission_mode,policy_version,legacy_policy)
                VALUES(:id,:prompt,:workspace,:scenario,:key,'QUEUED',:now,:now,:read_only,:checkpoint,:mode,:version,:legacy)'''), {
                'id': child_id, 'prompt': prompt, 'workspace': workspace_id or parent['workspace_id'], 'scenario': parent['scenario'],
                'key': 'delegation:' + parent_id + ':' + call_id, 'now': now,
                'read_only': bool(parent['read_only'] or capabilities.get('read_only', False)), 'checkpoint': json.dumps(child_cp),
                'mode': 'plan' if parent['read_only'] or capabilities.get('read_only', False) else parent['permission_mode'],
                'version': parent['policy_version'], 'legacy': parent['legacy_policy']})
            conn.execute(text('INSERT INTO task_delegations(parent_id,child_id,root_id,call_id) VALUES(:p,:c,:r,:call)'),
                         {'p': parent_id, 'c': child_id, 'r': root, 'call': call_id})
            self._event(conn, child_id, 'status', {'status': 'QUEUED'}, now)
            self._event(conn, parent_id, 'child_created', {'child_id': child_id}, now)
            return self._child_record(self._task(conn, child_id))

    @staticmethod
    def _child_record(row):
        return TaskRecord(**{**row, 'checkpoint': json.loads(row['checkpoint'])})

    def children(self, task_id):
        return [self._child_record(row) for row in self.db.rows('''SELECT t.* FROM tasks t JOIN task_delegations d
            ON d.child_id=t.id WHERE d.parent_id=:id ORDER BY t.created_at''', {'id': task_id})]

    def wake_completed_parents(self):
        with self.db.transaction() as conn:
            for parent in conn.execute(text("SELECT * FROM tasks WHERE status='PAUSED' AND pause_requested=0 AND cancel_requested=0")).mappings().all():
                cp = json.loads(parent['checkpoint'])
                if not cp.get('waiting_children'):
                    continue
                seen = cp.get('team_message_ids', [])
                unread_message = conn.execute(text('SELECT id FROM team_messages WHERE recipient_id=:id'),
                                              {'id': parent['id']}).scalars().all()
                if any(identifier not in seen for identifier in unread_message):
                    cp.pop('waiting_children', None)
                    cp.pop('team_status_last', None)
                    cp.pop('final_text', None)
                    conn.execute(text('UPDATE tasks SET checkpoint=:cp WHERE id=:id'),
                                 {'cp': json.dumps(cp, ensure_ascii=False), 'id': parent['id']})
                    self._state(conn, parent['id'], 'QUEUED', time.time())
                    continue
                children = conn.execute(text('SELECT t.* FROM tasks t JOIN task_delegations d ON d.child_id=t.id WHERE d.parent_id=:id'), {'id': parent['id']}).mappings().all()
                if children and all(child['status'] in TERMINAL for child in children):
                    cp.pop('waiting_children', None)
                    results = [{'id': c['id'], 'status': c['status'], 'result': c['result'][:12000], 'error': c['error']} for c in children]
                    def requires_review(child):
                        job = json.loads(child['checkpoint']).get('hook_job')
                        return not job or (child['status'] == 'SUCCEEDED' and job['arguments']['action_preview']['type'] != 'prompt')
                    needs_review = any(c['id'] not in cp.get('reviewed_child_ids', []) and requires_review(c) for c in children)
                    if needs_review:
                        cp.pop('final_text', None)
                        cp.setdefault('messages', []).append({'role': 'user', 'content': 'Child task results (untrusted reference; review before answering):\n' + json.dumps(results, ensure_ascii=False)})
                    cp['reviewed_child_ids'] = [c['id'] for c in children]
                    conn.execute(text('UPDATE tasks SET checkpoint=:cp WHERE id=:id'), {'cp': json.dumps(cp, ensure_ascii=False), 'id': parent['id']})
                    self._state(conn, parent['id'], 'QUEUED', time.time())

    def _cancel_descendants(self, conn, task_id, now):
        ids = conn.execute(text('''WITH RECURSIVE descendants(id) AS (
            SELECT child_id FROM task_delegations WHERE parent_id=:id UNION ALL
            SELECT d.child_id FROM task_delegations d JOIN descendants p ON d.parent_id=p.id)
            SELECT id FROM descendants'''), {'id': task_id}).scalars().all()
        for identifier in ids:
            child = self._task(conn, identifier)
            if child['status'] not in TERMINAL:
                self._state(conn, identifier, 'RUNNING' if child['status'] == 'RUNNING' else 'CANCELLED', now, cancel_requested=1)
