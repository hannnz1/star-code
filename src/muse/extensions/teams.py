import json

from mewcode.teams.models import AgentTeam, TeammateInfo
from muse.contracts import TERMINAL, ToolDefinition, ToolResult


class DurableTeams:
    def __init__(self, registry):
        self.ctx = registry.context
        registry.register(ToolDefinition(name='team_board', description='Read the shared dependency and ownership board for this task group.',
            parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}), self.board)
        registry.register(ToolDefinition(name='team_work', risk='execute', description='Create, claim, release, complete or cancel shared work with approval. Updates require the current revision; dependencies must finish before claiming.',
            parameters={'type': 'object', 'properties': {
                'action': {'type': 'string', 'enum': ['create', 'claim', 'release', 'complete', 'cancel']},
                'title': {'type': 'string', 'minLength': 1, 'maxLength': 500},
                'dependencies': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 100},
                'item_id': {'type': 'string'}, 'expected_revision': {'type': 'integer', 'minimum': 1}},
                'required': ['action'], 'additionalProperties': False}), self.work)
        registry.register(ToolDefinition(name='team_status', description='List this root task and its durable child workers. Other task groups are invisible.',
            parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}), self.status)
        registry.register(ToolDefinition(name='team_message', risk='execute',
            description='Send a durable coordination message to a worker in this task group, with approval. Cannot message people or unrelated tasks.',
            parameters={'type': 'object', 'properties': {'recipient_id': {'type': 'string'},
                'message': {'type': 'string', 'minLength': 1, 'maxLength': 8000}},
                'required': ['recipient_id', 'message'], 'additionalProperties': False}), self.send)

    async def status(self, args, call_id):
        members = self.ctx.repo.team_members(self.ctx.task_id)
        team = AgentTeam(name='task-' + members[0]['id'][:12], lead_agent_id=members[0]['id'])
        for member in members:
            team.add_member(TeammateInfo(name=member['id'], agent_id=member['id'], agent_type='durable-task',
                model=self.ctx.settings.provider.model if self.ctx.settings.provider else '',
                worktree_path=self.ctx.repo.workspace(member['workspace_id'])['path'], backend_type='durable-worker',
                is_active=member['status'] not in TERMINAL))
        return json.dumps({'team': team.to_dict(), 'statuses': {member['id']: member['status'] for member in members}})

    async def send(self, args, call_id):
        record = self.ctx.repo.send_team_message(self.ctx.task_id, self.ctx.owner, self.ctx.epoch,
            call_id, args['recipient_id'], self.ctx.safe(args['message']))
        return ToolResult(call_id=call_id, content=json.dumps(record))

    async def board(self, args, call_id):
        return json.dumps(self.ctx.repo.team_board(self.ctx.task_id))

    async def work(self, args, call_id):
        record = self.ctx.repo.team_work(self.ctx.task_id, self.ctx.owner, self.ctx.epoch, call_id, self.ctx.safe_value(args))
        return ToolResult(call_id=call_id, content=json.dumps(record))

    def receive(self):
        seen = self.ctx.cp.setdefault('team_message_ids', [])
        for message in self.ctx.repo.team_inbox(self.ctx.task_id):
            if message['id'] in seen:
                continue
            self.ctx.cp['messages'].append({'role': 'user', 'content':
                'Untrusted coordination from task ' + message['sender_id'] + ':\n' + self.ctx.safe(message['message'])})
            seen.append(message['id'])
            self.ctx.cp.pop('final_text', None)
        self.ctx.save()
