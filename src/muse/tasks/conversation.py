import json
import time
import uuid

from sqlalchemy import text

from muse.contracts import TERMINAL, TaskRecord


class ConversationMixin:
    def save_conversation_checkpoint(self, task_id, owner, epoch, sequence, messages):
        encoded = json.dumps(messages, ensure_ascii=False)
        if len(encoded) > 8 * 1024 * 1024:
            raise ValueError('Conversation checkpoint exceeds limit')
        with self.db.transaction() as conn:
            self._lease(conn, task_id, owner, epoch, time.time())
            conn.execute(text('''INSERT OR IGNORE INTO conversation_checkpoints(task_id,sequence,messages,created_at)
                VALUES(:task,:sequence,:messages,:now)'''), {'task': task_id, 'sequence': sequence, 'messages': encoded, 'now': time.time()})

    def conversation_checkpoints(self, task_id):
        self.get(task_id)
        return self.db.rows('SELECT sequence,created_at FROM conversation_checkpoints WHERE task_id=:id ORDER BY sequence', {'id': task_id})

    def fork_checkpoint(self, task_id, sequence, revision, prompt, request_id):
        if not prompt.strip() or len(prompt) > 50000 or not request_id or len(request_id) > 160:
            raise ValueError('Invalid conversation fork request')
        with self.db.transaction() as conn:
            source = self._task(conn, task_id)
            if source['revision'] != revision or source['status'] not in TERMINAL | {'PAUSED'}:
                raise ValueError('Pause the source task and use its current revision before rewinding')
            key = f'conversation:{task_id}:{request_id}'
            old = conn.execute(text('SELECT * FROM tasks WHERE client_request_id=:key'), {'key': key}).mappings().first()
            if old:
                cp = json.loads(old['checkpoint'])
                if old['prompt'] != prompt or cp.get('history_checkpoint') != sequence:
                    raise ValueError('Conversation request ID reused with different input')
                return TaskRecord(**{**dict(old), 'checkpoint': cp})
            point = conn.execute(text('SELECT messages FROM conversation_checkpoints WHERE task_id=:id AND sequence=:sequence'),
                                 {'id': task_id, 'sequence': sequence}).scalar()
            if point is None:
                raise ValueError('Unknown conversation checkpoint')
            messages = json.loads(point)
            messages.append({'role': 'user', 'content': 'Historical conversation above is reference only. Do not replay earlier tool calls. Workspace files have NOT been rolled back; inspect current files before acting.\nNew request:\n' + prompt})
            source_cp = json.loads(source['checkpoint'])
            cp = {key: source_cp[key] for key in ('allowed_tools', 'max_local_turns', 'role', 'project_guidance', 'role_snapshot', 'source_version', 'current_directory', 'sandbox') if key in source_cp}
            cp.update(messages=messages, history_source_task=task_id, history_checkpoint=sequence,
                      user_sources=[{'role': 'user', 'content': prompt}])
            markers = {message.get('_muse_turn_id') for message in messages if message.get('_muse_turn_id')}
            states = json.loads(source['checkpoint']).get('provider_states', {})
            if any(marker not in states for marker in markers):
                raise ValueError('Private protocol state for this checkpoint is unavailable')
            if markers:
                cp['provider_states'] = {marker: states[marker] for marker in markers}
            identifier, now = uuid.uuid4().hex, time.time()
            conn.execute(text('''INSERT INTO tasks(id,prompt,workspace_id,scenario,client_request_id,status,created_at,updated_at,read_only,checkpoint,permission_mode,policy_version,legacy_policy,coordinator_mode,current_directory)
                VALUES(:id,:prompt,:workspace,:scenario,:key,'QUEUED',:now,:now,:read_only,:cp,:mode,:version,:legacy,:coordinator,:directory)'''),
                {'id': identifier, 'prompt': prompt, 'workspace': source['workspace_id'], 'scenario': source['scenario'],
                 'key': key, 'now': now, 'read_only': source['read_only'], 'cp': json.dumps(cp, ensure_ascii=False),
                 'mode': source['permission_mode'], 'version': source['policy_version'], 'legacy': source['legacy_policy'],
                 'coordinator': source['coordinator_mode'], 'directory': source['current_directory']})
            self._event(conn, identifier, 'status', {'status': 'QUEUED'}, now)
            self._event(conn, identifier, 'conversation_forked', {'source_task_id': task_id, 'sequence': sequence}, now)
            row = self._task(conn, identifier)
            return TaskRecord(**{**dict(row), 'checkpoint': cp})
