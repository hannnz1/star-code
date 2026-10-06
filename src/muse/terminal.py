"""Terminal frontend for the same HTTP service and Worker used by the web UI."""
import hashlib
import json
import re
import shlex
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import httpx

from mewcode.commands.parser import parse_command
from muse.contracts import TERMINAL

HELP = '''Crew commands:
/help /status /tasks /use ID /clear /events /watch
/plan PROMPT /do PROMPT /review PROMPT
/mode default|acceptEdits|plan
/thinking
/trace [TASK_ID] /run-skill NAME [ARGS] /coordinator on|off
/sandbox
/pause /resume /cancel /input REPLY
/approvals /approve ID /deny ID /renew ID
/memory /artifacts /sources /rewind CALL_ID /exit
/memory-jobs /memory-candidates /confirm-memory ID /withdraw-memory ID /memory-history ID
/children /child ID /back
/team /board
/compact /reload /skills /agents /mcp /model /cost /context
/uncertain /resolve CALL_ID success|failed EXPLANATION
/checkpoints /rewind SEQUENCE conversation PROMPT
/hooks /permission /skill NAME /active-skills /reload-skills /worktree
Ordinary text creates a durable coding task. /plan and /review are read-only.
'''


def complete_command(prefix):
    if not prefix.startswith('/') or any(ch.isspace() for ch in prefix):
        return []
    return sorted(name for name in set(re.findall(r'/[a-z][a-z-]*', HELP)) if name.startswith(prefix.lower()))


class TerminalClient:
    def __init__(self, client, workspace_id):
        self.client = client
        self.workspace_id = workspace_id
        self.task_id = None
        self.reviewed = {}
        self.reviewed_external = {}
        self.parents = []

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def task(self):
        if self.task_id is None:
            raise ValueError('Select a task with /use ID or submit a prompt first')
        task = self.request('GET', f'/api/tasks/{self.task_id}')
        if task['workspace_id'] != self.workspace_id:
            raise ValueError('Task belongs to a different workspace')
        return task

    def submit(self, prompt, read_only=False, permission_mode=None, plan=None):
        parent = self.task() if self.task_id else None
        if parent and parent['status'] not in TERMINAL:
            raise ValueError('Current task is active; use /input to answer it or /clear to start another task')
        result = self.request('POST', '/api/tasks', json={'prompt': prompt, 'workspace_id': self.workspace_id,
            'scenario': 'coding', 'read_only': read_only, 'client_request_id': uuid.uuid4().hex,
            'coordinator_mode': getattr(self, 'coordinator_mode', False),
            'plan_task_id': plan['id'] if plan else None,
            'plan_sha256': hashlib.sha256(plan['result'].encode()).hexdigest() if plan else None,
            'permission_mode': 'plan' if read_only else permission_mode or getattr(self, 'permission_mode', 'default'),
            'parent_task_id': parent['id'] if parent else None})
        self.task_id = result['id']
        return result

    def handle(self, line):
        name, args, is_command = parse_command(line)
        name = {'permission': 'approvals', 'reload-skills': 'skills'}.get(name, name)
        if not is_command:
            result = self.submit(line)
        elif name == 'sandbox':
            if args:
                raise ValueError('Set sandbox.policy in your explicit configuration, then restart for new tasks')
            result = self.request('GET', '/api/sandbox')
        elif name == 'memory-jobs':
            result = self.request('GET', '/api/memory/jobs')
        elif name == 'memory-candidates':
            result = self.request('GET', '/api/memory/candidates')
        elif name in {'confirm-memory', 'withdraw-memory', 'memory-history'}:
            if not re.fullmatch(r'[a-f0-9]{32}', args):
                raise ValueError('A memory ID is required')
            action = {'confirm-memory': 'confirm', 'withdraw-memory': 'withdraw', 'memory-history': 'history'}[name]
            result = self.request('GET' if action == 'history' else 'POST', f'/api/memory/{args}/{action}')
        elif name == 'help':
            return HELP
        elif name in {'exit', 'quit'}:
            raise EOFError()
        elif name == 'clear':
            self.task_id = None
            return 'Ready for a new task. Existing tasks continue in the Worker.'
        elif name == 'mode':
            if args not in {'default', 'acceptEdits', 'plan'}:
                raise ValueError('Use /mode default|acceptEdits|plan')
            if self.task_id:
                task = self.task()
                if task['status'] not in TERMINAL:
                    result = self.request('POST', f"/api/tasks/{task['id']}/policy", json={
                        'permission_mode': args, 'expected_revision': task['revision']})
                    self.permission_mode = args
                else:
                    self.permission_mode = args
                    result = {'permission_mode': args, 'applies_to': 'new tasks'}
            else:
                self.permission_mode = args
                result = {'permission_mode': args, 'applies_to': 'new tasks'}
        elif name == 'coordinator':
            if args not in {'on', 'off'}:
                raise ValueError('Use /coordinator on|off for new tasks')
            self.coordinator_mode = args == 'on'
            result = {'coordinator_mode': self.coordinator_mode, 'applies_to': 'new tasks'}
        elif name == 'trace':
            identifier = args or self.task()['id']
            if not re.fullmatch(r'[a-f0-9]{32}', identifier):
                raise ValueError('A task ID is required')
            result = self.request('GET', f'/api/tasks/{identifier}/trace')
        elif name == 'run-skill':
            result = self.run_skill(args)
        elif name in {'plan', 'review', 'do'}:
            prompt = args or ('Execute the previous plan and verify the changes.' if name == 'do' else 'Review the current project and report findings.')
            source = self.task() if name == 'do' and self.task_id else None
            result = self.submit(prompt, read_only=name != 'do', plan=source if source and source['read_only'] and source['status'] == 'SUCCEEDED' else None)
        elif name == 'use':
            task = self.request('GET', '/api/tasks/' + args)
            if task['workspace_id'] != self.workspace_id:
                raise ValueError('Task belongs to a different workspace')
            self.task_id = task['id']
            result = task
        elif name == 'tasks':
            result = [t for t in self.request('GET', '/api/tasks') if t['workspace_id'] == self.workspace_id]
        elif name in {'children', 'child'}:
            task = self.task()
            children = self.request('GET', f"/api/tasks/{task['id']}/children")
            result = children
            if name == 'child':
                child = next((item for item in children if item['id'] == args), None)
                if child is None:
                    raise ValueError('Not a child of the selected task; use /children')
                self.parents.append((self.workspace_id, self.task_id))
                self.workspace_id, self.task_id = child['workspace_id'], child['id']
                result = child
        elif name == 'back':
            if not self.parents:
                raise ValueError('No parent task to return to')
            self.workspace_id, self.task_id = self.parents.pop()
            result = self.task()
        elif name in {'team', 'board'}:
            task = self.task()
            result = self.request('GET', f"/api/tasks/{task['id']}/team")
            if name == 'board':
                result = result['work_items']
        elif name == 'worktree':
            if args:
                raise ValueError('Use /worktree to list retained child checkouts; request spawn_worktree or worktree_manage in a task for approved changes')
            task = self.task()
            result = [child for child in self.request('GET', f"/api/tasks/{task['id']}/children") if child['workspace_id'] != task['workspace_id']]
        elif name in {'skills', 'agents', 'mcp', 'hooks', 'active-skills', 'skill'}:
            task = self.task()
            catalog = self.request('GET', f"/api/tasks/{task['id']}/catalog")
            result = catalog['skills'] if name == 'skill' else catalog[name]
            if name == 'skill' and args:
                result = [item for item in result['skills'] if item['name'] == args]
                if not result:
                    raise ValueError('Unknown skill; use /skills. Request its execution in a task.')
        elif name == 'model':
            result = self.request('GET', '/api/settings').get('provider')
        elif name in {'cost', 'context'}:
            result = self.task()['metrics']
        elif name in {'status', 'session'}:
            result = self.task() if self.task_id else self.request('GET', '/api/settings')
        elif name in {'pause', 'resume', 'cancel', 'input', 'compact', 'reload'}:
            task = self.task()
            result = self.request('POST', f"/api/tasks/{task['id']}/{name}", json={'expected_revision': task['revision'], 'content': args})
        elif name == 'uncertain':
            task = self.task()
            result = self.request('GET', f"/api/tasks/{task['id']}/uncertain-actions")
            self.reviewed_external = {(task['id'], item['id']): item['digest'] for item in result}
        elif name == 'resolve':
            task = self.task()
            parts = shlex.split(args)
            if len(parts) < 3 or parts[1] not in {'success', 'failed'}:
                raise ValueError('Use /resolve CALL_ID success|failed EXPLANATION after reviewing /uncertain')
            digest = self.reviewed_external.get((task['id'], parts[0]))
            if not digest:
                raise ValueError('Read /uncertain before resolving this action')
            result = self.request('POST', f"/api/external-actions/{task['id']}/reconcile", json={
                'call_id': parts[0], 'action_digest': digest, 'successful': parts[1] == 'success',
                'expected_revision': task['revision'], 'explanation': ' '.join(parts[2:])})
            self.reviewed_external.pop((task['id'], parts[0]))
        elif name == 'approvals':
            task = self.task()
            result = self.request('GET', '/api/approvals', params={'task_id': task['id']})
            self.reviewed = {a['id']: a['action_digest'] for a in result if a['status'] == 'PENDING'}
        elif name in {'approve', 'deny', 'renew'}:
            if args not in self.reviewed:
                raise ValueError('Read /approvals before deciding an action')
            body = {'action_digest': self.reviewed[args]}
            if name != 'renew':
                body['allow'] = name == 'approve'
            endpoint = 'renew' if name == 'renew' else 'decision'
            result = self.request('POST', f'/api/approvals/{args}/{endpoint}', json=body)
            self.reviewed.pop(args)
        elif name == 'memory':
            result = [m for m in self.request('GET', '/api/memories') if m['scope'] == 'user' or m['workspace_id'] == self.workspace_id]
        elif name == 'thinking':
            task = self.task()
            summaries, cursor, pending = [], 0, []
            while True:
                response = self.client.get(f"/api/tasks/{task['id']}/events", params={'follow': 'false', 'after': cursor})
                response.raise_for_status()
                batch = [json.loads(frame[6:]) for frame in response.text.splitlines() if frame.startswith('data: ')]
                for event in batch:
                    cursor = event['sequence']
                    if event['type'] == 'thinking_summary_delta':
                        pending.append(event['payload']['text'])
                    elif event['type'] == 'thinking_summary':
                        summaries.append(f"#{event['payload']['model_request']}: " + event['payload']['text'])
                        pending = []
                if len(batch) < 1000:
                    break
            if pending:
                summaries.append('进行中：' + ''.join(pending))
            return '\n'.join(summaries) or '本任务尚无思考摘要。'
        elif name in {'artifacts', 'sources', 'events'}:
            task = self.task()
            if name == 'events':
                response = self.client.get(f"/api/tasks/{task['id']}/events", params={'follow': 'false'})
                response.raise_for_status()
                return response.text
            result = self.request('GET', f"/api/tasks/{task['id']}/{name}")
        elif name == 'checkpoints':
            task = self.task()
            result = self.request('GET', f"/api/tasks/{task['id']}/conversation-checkpoints")
        elif name == 'rewind':
            if 'both' in args.split():
                raise ValueError('both recovery is unsupported; file and conversation recovery are separate actions')
            task = self.task()
            parts = args.split(maxsplit=2)
            if len(parts) >= 2 and parts[1] == 'conversation':
                if len(parts) != 3 or not parts[0].isdigit():
                    raise ValueError('Use /rewind SEQUENCE conversation PROMPT after /checkpoints')
                result = self.request('POST', f"/api/conversations/{task['id']}/fork", json={
                    'sequence': int(parts[0]), 'expected_revision': task['revision'],
                    'prompt': parts[2], 'client_request_id': uuid.uuid4().hex})
                self.task_id = result['id']
            else:
                if len(parts) > 1 and (len(parts) != 2 or parts[1] != 'files'):
                    raise ValueError('Use /rewind CALL_ID files, or /rewind SEQUENCE conversation PROMPT. File and conversation recovery are separate actions.')
                result = self.request('POST', f"/api/file-actions/{task['id']}/rewind", json={'call_id': parts[0], 'expected_revision': task['revision']}) if parts else self.request('GET', f"/api/tasks/{task['id']}/file-history")
        elif name == 'watch':
            previous = None
            while True:
                task = self.task()
                if task['revision'] != previous:
                    print(json.dumps(task, ensure_ascii=False, indent=2), flush=True)
                    previous = task['revision']
                if task['status'] not in {'QUEUED', 'RUNNING'}:
                    return 'Use /approvals or /input when the task needs your response.'
                time.sleep(.5)
        else:
            catalog = self.request('GET', f'/api/workspaces/{self.workspace_id}/skills')
            if name in {alias['name'] for alias in catalog['aliases'] if alias['enabled']}:
                result = self.run_skill(name + (' ' + args if args else ''))
            else:
                raise ValueError('Unknown command. Use /help or /run-skill NAME ARGS.')
        return json.dumps(result, ensure_ascii=False, indent=2)

    def run_skill(self, arguments):
        parts = arguments.split(maxsplit=1)
        if not parts:
            raise ValueError('Use /run-skill NAME [ARGS]')
        if self.task_id and self.task()['status'] not in TERMINAL:
            raise ValueError('Current task is active; finish it or /clear before running a skill')
        result = self.request('POST', '/api/skills/run', json={'name': parts[0], 'arguments': parts[1] if len(parts) > 1 else '',
            'prompt': 'Execute skill ' + parts[0], 'workspace_id': self.workspace_id,
            'client_request_id': uuid.uuid4().hex, 'scenario': 'coding',
            'permission_mode': getattr(self, 'permission_mode', 'default'),
            'coordinator_mode': getattr(self, 'coordinator_mode', False)})
        self.task_id = result['id']
        return result


def validate_server(settings, public):
    if Path(public['data_dir']).resolve() != settings.data_dir.resolve():
        raise ValueError('Server data directory differs from this client')
    if settings.provider:
        expected = settings.public()
        fields = ('provider', 'max_turns', 'max_tool_calls', 'max_active_seconds')
        if any(public.get(field) != expected[field] for field in fields):
            raise ValueError('Server model configuration differs from the selected configuration; restart API and Worker together')


@contextmanager
def connect_terminal(settings, workspace: Path):
    with httpx.Client(base_url=f'http://127.0.0.1:{settings.port}',
                      headers={'Authorization': 'Bearer ' + settings.access_token.get_secret_value()},
                      trust_env=False, timeout=15) as client:
        server = client.get('/api/settings')
        server.raise_for_status()
        validate_server(settings, server.json())
        response = client.post('/api/workspaces', json={'path': str(workspace.resolve()), 'name': workspace.name})
        response.raise_for_status()
        yield TerminalClient(client, response.json()['id'])


def run_terminal(settings, workspace: Path):
    with connect_terminal(settings, workspace) as terminal:
        print(HELP)
        while True:
            try:
                line = input('Crew> ').strip()
                if line:
                    print(terminal.handle(line))
            except EOFError:
                break
            except KeyboardInterrupt:
                print('\nUse /cancel to stop the selected task; /exit leaves it running.')
            except (ValueError, httpx.HTTPError) as error:
                print(str(error))
