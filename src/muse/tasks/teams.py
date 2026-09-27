"""Transactional coordination restricted to one root task's descendants."""
import json
import time
import uuid

from sqlalchemy import text

from muse.contracts import TERMINAL


class TeamMixin:
    def team_board(self, task_id):
        with self.db.engine.connect() as conn:
            root = self._root_id(conn, task_id)
            return [{**dict(row), 'dependencies': json.loads(row['dependencies'])} for row in conn.execute(
                text('SELECT * FROM team_work_items WHERE root_id=:root ORDER BY created_at,id'), {'root': root}).mappings()]

    def team_work(self, task_id, owner, epoch, call_id, args):
        now = time.time()
        encoded = json.dumps(args, sort_keys=True, ensure_ascii=False)
        with self.db.transaction() as conn:
            task = self._lease(conn, task_id, owner, epoch, now)
            if task['cancel_requested'] or task['pause_requested']:
                raise ValueError('Task control prevents team work changes')
            root = self._root_id(conn, task_id)
            receipt = conn.execute(text('SELECT * FROM team_work_actions WHERE task_id=:task AND call_id=:call'),
                                   {'task': task_id, 'call': call_id}).mappings().first()
            if receipt:
                if receipt['arguments'] != encoded:
                    raise ValueError('Team work call reused with different arguments')
                return json.loads(receipt['result'])
            action = args['action']
            if action == 'create':
                title = args.get('title', '')
                if not isinstance(title, str) or not title.strip() or len(title) > 500:
                    raise ValueError('Work title must contain 1–500 characters')
                if conn.execute(text('SELECT COUNT(*) FROM team_work_items WHERE root_id=:root'), {'root': root}).scalar_one() >= 100:
                    raise ValueError('Task group work limit reached')
                dependencies = args.get('dependencies', [])
                if not isinstance(dependencies, list) or any(not isinstance(d, str) for d in dependencies):
                    raise ValueError('Invalid work dependencies')
                for dependency in dependencies:
                    if not conn.execute(text('SELECT id FROM team_work_items WHERE id=:id AND root_id=:root'),
                                        {'id': dependency, 'root': root}).first():
                        raise ValueError('Work dependency is outside this group')
                item_id = uuid.uuid4().hex
                conn.execute(text('''INSERT INTO team_work_items(id,root_id,title,dependencies,status,created_at,updated_at)
                    VALUES(:id,:root,:title,:deps,'pending',:now,:now)'''),
                    {'id': item_id, 'root': root, 'title': title, 'deps': json.dumps(sorted(set(dependencies))), 'now': now})
            else:
                item_id = args.get('item_id')
                row = conn.execute(text('SELECT * FROM team_work_items WHERE id=:id AND root_id=:root'),
                                   {'id': item_id, 'root': root}).mappings().first()
                if not row:
                    raise ValueError('Work item is outside this group')
                if row['revision'] != args.get('expected_revision'):
                    raise ValueError('Work item revision conflict')
                if row['status'] in {'completed', 'cancelled'}:
                    raise ValueError('Work item is already terminal')
                new_owner = row['owner_id']
                if action == 'claim':
                    if row['owner_id'] not in (None, task_id):
                        raise ValueError('Work item has another owner')
                    for dependency in json.loads(row['dependencies']):
                        if conn.execute(text('SELECT status FROM team_work_items WHERE id=:id'), {'id': dependency}).scalar_one() != 'completed':
                            raise ValueError('Work dependencies are not completed')
                    status, new_owner = 'in_progress', task_id
                elif action in {'complete', 'release'}:
                    if row['owner_id'] != task_id:
                        raise ValueError('Only the work owner can complete or release it')
                    status = 'completed' if action == 'complete' else 'pending'
                    if action == 'release':
                        new_owner = None
                elif action == 'cancel':
                    if task_id != root and row['owner_id'] != task_id:
                        raise ValueError('Only the lead or owner can cancel work')
                    status = 'cancelled'
                else:
                    raise ValueError('Unknown work action')
                conn.execute(text('UPDATE team_work_items SET status=:status,owner_id=:owner,revision=revision+1,updated_at=:now WHERE id=:id'),
                             {'id': item_id, 'status': status, 'owner': new_owner, 'now': now})
            row = dict(conn.execute(text('SELECT * FROM team_work_items WHERE id=:id'), {'id': item_id}).mappings().one())
            result = {**row, 'dependencies': json.loads(row['dependencies'])}
            conn.execute(text('INSERT INTO team_work_actions(task_id,call_id,arguments,result) VALUES(:task,:call,:args,:result)'),
                         {'task': task_id, 'call': call_id, 'args': encoded, 'result': json.dumps(result)})
            self._event(conn, root, 'team_work_updated', {'actor_id': task_id, 'item': result}, now)
            return result

    def team_members(self, task_id):
        with self.db.engine.connect() as conn:
            return [self._task(conn, identifier) for identifier in self._group_ids(conn, task_id)]

    def send_team_message(self, task_id, owner, epoch, call_id, recipient, message):
        if not message.strip() or len(message) > 8000:
            raise ValueError('Team message must contain 1–8000 characters')
        now = time.time()
        with self.db.transaction() as conn:
            sender = self._lease(conn, task_id, owner, epoch, now)
            if sender['cancel_requested'] or sender['pause_requested']:
                raise ValueError('Task control prevents team messages')
            root = self._root_id(conn, task_id)
            if recipient not in self._group_ids(conn, task_id):
                raise ValueError('Recipient is outside this task group')
            existing = conn.execute(text('SELECT * FROM team_messages WHERE sender_id=:sender AND call_id=:call'),
                                    {'sender': task_id, 'call': call_id}).mappings().first()
            if existing:
                if existing['recipient_id'] != recipient or existing['message'] != message:
                    raise ValueError('Message call reused with different content')
                return dict(existing)
            if self._task(conn, recipient)['status'] in TERMINAL:
                raise ValueError('Recipient task has already finished')
            count = conn.execute(text('SELECT COUNT(*) FROM team_messages WHERE root_id=:root'), {'root': root}).scalar_one()
            if count >= 200:
                raise ValueError('Task group message limit reached')
            data = {'id': uuid.uuid4().hex, 'root_id': root, 'sender_id': task_id, 'recipient_id': recipient,
                    'call_id': call_id, 'message': message, 'created_at': now}
            conn.execute(text('''INSERT INTO team_messages(id,root_id,sender_id,recipient_id,call_id,message,created_at)
                VALUES(:id,:root_id,:sender_id,:recipient_id,:call_id,:message,:created_at)'''), data)
            self._event(conn, recipient, 'team_message', {'id': data['id'], 'sender_id': task_id, 'message': message}, now)
            return data

    def team_inbox(self, task_id):
        return self.db.rows('SELECT * FROM team_messages WHERE recipient_id=:id ORDER BY created_at,id', {'id': task_id})
