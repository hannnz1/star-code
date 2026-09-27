"""Approved isolated checkouts, retained for review after child completion."""
import hashlib
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from mewcode.worktree.models import Worktree
from muse.contracts import TERMINAL, ToolDefinition, ToolResult
from muse.tools.shell import run_command


class DurableWorktrees:
    def __init__(self, registry):
        self.registry = registry
        self.ctx = registry.context
        registry.register(ToolDefinition(name='spawn_worktree', risk='execute',
            description='Create a retained isolated Git checkout at an exact commit and delegate a child. Omit role for the default general worker; role is a registered capability profile, not a worker display name. Use list_roles to discover project roles. Shares budgets, requires approval, preserves parent changes. No automatic merge or deletion.',
            parameters={'type': 'object', 'properties': {
                'base_commit': {'type': 'string', 'pattern': '^[a-fA-F0-9]{40}([a-fA-F0-9]{24})?$'},
                'prompt': {'type': 'string', 'minLength': 1, 'maxLength': 50000},
                'role': {'type': 'string', 'maxLength': 64, 'description': 'Registered role name only; not a display name. Omit for general, or use general/explore/plan/verification or a role returned by list_roles.'}, '_role_sha256': {'type': 'string'},
                'worktree_path': {'type': 'string'}}, 'required': ['base_commit', 'prompt'],
                'additionalProperties': False}), self.spawn)
        commit = {'type': 'string', 'pattern': '^[a-fA-F0-9]{40}([a-fA-F0-9]{24})?$'}
        registry.register(ToolDefinition(name='worktree_manage', risk='execute',
            description='Review, fast-forward merge, integrate divergent commits with a merge commit, or remove a managed child checkout with approval. Changes require exact source and parent commits, clean checkouts, and finished child tasks. Conflicts are retained for review; no automatic reset. Removal requires the child commit already merged; branches are retained.',
            parameters={'type': 'object', 'properties': {'child_id': {'type': 'string'},
                'action': {'type': 'string', 'enum': ['review', 'merge', 'integrate', 'remove']},
                'source_commit': commit, 'parent_commit': commit}, 'required': ['child_id', 'action'],
                'additionalProperties': False}), self.manage)

    def path(self, call_id):
        identity = self.ctx.task_id + ':' + call_id
        return self.managed_root() / hashlib.sha256(identity.encode()).hexdigest()[:24]

    def managed_root(self):
        # Task files must be outside the protected application-state directory.
        data = self.ctx.settings.data_dir
        return data.parent / (data.name + '-worktrees')

    def bind(self, call):
        if call.name == 'spawn_worktree':
            return call.model_copy(update={'arguments': {**call.arguments, 'worktree_path': str(self.path(call.id))}})
        return call

    async def git(self, call_id, *arguments):
        executable = shutil.which('git')
        if not executable:
            raise ValueError('Git is required for isolated worktrees')
        argv = [executable, '-c', f'core.hooksPath={os.devnull}', '-c', 'core.fsmonitor=false', '-c', 'core.longpaths=true', *arguments]
        result = await run_command(self.ctx, {'command': 'git ' + ' '.join(arguments), 'timeout_seconds': 60}, call_id, argv=argv)
        if result.status != 'success':
            raise ValueError('Git operation failed: ' + result.content[:2000])
        return result.content.split('\n[stderr]\n', 1)[0].strip()

    async def manage(self, args, call_id):
        child = next((c for c in self.ctx.repo.children(self.ctx.task_id) if c.id == args['child_id']), None)
        if child is None:
            raise ValueError('Checkout is not a child of this task')
        link = self.ctx.repo.db.rows('SELECT call_id FROM task_delegations WHERE child_id=:id', {'id': child.id})[0]
        target = Path(self.ctx.repo.workspace(child.workspace_id)['path']).absolute()
        managed = self.managed_root().absolute()
        if managed.resolve() != managed or target != self.path(link['call_id']) or target.resolve() != target or not target.is_relative_to(managed):
            raise PermissionError('Checkout is not an unchanged managed path')
        root = await self.git(call_id + ':root', 'rev-parse', '--show-toplevel')
        if Path(root).resolve() != self.ctx.workspace.resolve():
            raise ValueError('Parent workspace must be the repository root')
        parent_commit = await self.git(call_id + ':parent', 'rev-parse', 'HEAD')
        source_commit = await self.git(call_id + ':source', '-C', str(target), 'rev-parse', 'HEAD')
        parent_status = await self.git(call_id + ':parent-status', 'status', '--porcelain')
        child_status = await self.git(call_id + ':child-status', '-C', str(target), 'status', '--porcelain')
        if args['action'] == 'review':
            diff = await self.git(call_id + ':diff', 'diff', '--no-ext-diff', '--no-textconv', '--stat', parent_commit, source_commit)
            return ToolResult(call_id=call_id, content=json.dumps({'child_id': child.id, 'path': str(target),
                'parent_commit': parent_commit, 'source_commit': source_commit, 'parent_status': parent_status,
                'child_status': child_status, 'diff_stat': diff}))
        active = self.ctx.repo.db.rows("SELECT id FROM tasks WHERE workspace_id=:id AND status NOT IN ('SUCCEEDED','FAILED','CANCELLED')", {'id': child.workspace_id})
        if child.status not in TERMINAL or active:
            raise ValueError('Finish all tasks using this checkout before changing it')
        if parent_status or child_status:
            raise ValueError('Both checkouts must be clean; existing changes are preserved')
        if args.get('source_commit', '').lower() != source_commit.lower():
            raise ValueError('Child checkout commit changed; review this child again before retrying')
        if args.get('parent_commit', '').lower() != parent_commit.lower():
            raise ValueError('Parent checkout commit changed after another integration; review this child again before retrying')
        if args['action'] == 'merge':
            await self.git(call_id + ':merge', 'merge', '--ff-only', '--no-overwrite-ignore', source_commit)
        elif args['action'] == 'integrate':
            await self.git(call_id + ':integrate', 'merge', '--no-ff', '--no-edit', '--no-overwrite-ignore', source_commit)
        elif args['action'] == 'remove':
            ignored = await self.git(call_id + ':ignored', '-C', str(target), 'status', '--porcelain', '--ignored')
            if ignored:
                raise ValueError('Checkout must be clean including ignored files; retained for review')
            await self.git(call_id + ':merged', 'merge-base', '--is-ancestor', source_commit, parent_commit)
            # Git refuses dirty or locked checkouts; no --force and no branch deletion.
            await self.git(call_id + ':remove', 'worktree', 'remove', str(target))
        else:
            raise ValueError('Unknown worktree action')
        return ToolResult(call_id=call_id, content=json.dumps({'action': args['action'], 'child_id': child.id,
                         'source_commit': source_commit, 'path': str(target)}))

    async def spawn(self, args, call_id):
        prompt, capabilities = self.registry.roles.prompt(args.get('role', 'general'), args['prompt'], isolated=True)
        destination = self.path(call_id)
        managed = self.managed_root().absolute()
        if managed.resolve() != managed:
            raise PermissionError('Managed worktree root was replaced by a link')
        if not destination.resolve().is_relative_to(managed):
            raise PermissionError('Managed worktree path was replaced by a link')
        root = await self.git(call_id + ':root', 'rev-parse', '--show-toplevel')
        if Path(root).resolve() != self.ctx.workspace.resolve():
            raise ValueError('Register the Git repository root as the workspace')
        commit = await self.git(call_id + ':commit', 'rev-parse', '--verify', args['base_commit'] + '^{commit}')
        if commit.lower() != args['base_commit'].lower():
            raise ValueError('Worktree base must identify an exact commit')
        if destination.exists():
            raise ValueError('Worktree destination already exists; inspect retained work before retrying')
        destination.parent.mkdir(parents=True, exist_ok=True)
        branch = 'muse-' + self.ctx.task_id[:12] + '-' + destination.name
        await self.git(call_id + ':create', 'worktree', 'add', '-b', branch, str(destination), commit)
        self.ctx.check()
        workspace = self.ctx.repo.register_workspace(str(destination), branch)
        child = self.ctx.repo.spawn_child(self.ctx.task_id, self.ctx.owner, self.ctx.epoch, call_id,
                                         prompt, workspace_id=workspace['id'], capabilities=capabilities)
        worktree = asdict(Worktree(name=branch, path=str(destination), branch=branch, based_on=commit, head_commit=commit))
        worktree['created'] = worktree['created'].isoformat()
        return ToolResult(call_id=call_id, content=json.dumps({'child_id': child.id, 'worktree': worktree}),
                          metadata={'worktree': worktree, 'child_id': child.id})
