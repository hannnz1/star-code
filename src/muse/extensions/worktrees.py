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
        # Pin this task's location before approval. A config reload cannot move
        # approved or retained checkouts; legacy receipts also carry the location.
        if 'worktree_managed_root' not in self.ctx.cp:
            previous = next((call['arguments'].get('worktree_path')
                             for call in self.ctx.repo.calls(self.ctx.task_id)
                             if call['name'] == 'spawn_worktree' and call['arguments'].get('worktree_path')), None)
            data = self.ctx.settings.data_dir
            root = (Path(previous).parent if previous else self.ctx.settings.worktree_managed_root
                    or self.default_root(data))
            self.ctx.cp['worktree_managed_root'] = str(root.absolute())
        return Path(self.ctx.cp['worktree_managed_root'])

    @staticmethod
    def default_root(data):
        root = data.parent / (data.name + '-worktrees')
        if os.name == 'nt':
            namespace = 'muse-worktrees-' + hashlib.sha256(str(data.absolute()).encode()).hexdigest()[:16]
            parent = data.parent
            while len(str(root / ('x' * 24) / '.git').encode('utf-8')) > 220 and parent != parent.parent:
                parent = parent.parent
                root = parent / namespace
        return root

    def creation_path(self, destination):
        # Git 2.43 passes <input>/.git through GIT_DIR to its child. Its
        # PATH_MAX-40 check precedes longpath handling and gitfile resolution.
        # A relative input is equivalent, while the approval stays absolute.
        try:
            value = os.path.relpath(destination, self.ctx.workspace)
        except ValueError:  # Different Windows drives.
            value = str(destination)
        if os.name == 'nt' and (len((value + '/.git').encode('utf-8')) > 220
                              or len(str(destination / '.git').encode('utf-8')) > 220):
            raise ValueError('WORKTREE_PATH_UNSUPPORTED: configure worktrees.managed_root to a shorter path on the workspace drive')
        return value

    async def path_preflight(self, call_id, commit, destination):
        for option in ('--absolute-git-dir', '--git-common-dir'):
            value = await self.git(call_id + ':' + option, 'rev-parse', option)
            directory = (self.ctx.workspace / value).resolve(strict=True)
            if not directory.is_dir():
                raise ValueError('Source Git metadata is not an accessible directory')
            if os.name == 'nt' and len(str(directory / 'worktrees' / destination.name).encode('utf-16-le')) // 2 >= 32760:
                raise ValueError('Source Git metadata exceeds the Windows extended path limit')
        listing = await self.git(call_id + ':paths', 'ls-tree', '-r', '-z', '--name-only', commit, raw=True)
        if '[output truncated]' in listing:
            raise ValueError('The tracked-path listing exceeds the bounded preflight limit')
        reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{name}{i}' for name in ('COM', 'LPT') for i in range(1, 10)}
        for value in listing.split('\0'):
            if not value:
                continue
            parts = value.split('/')
            if any(part in {'', '.', '..'} or part.casefold() == '.git' for part in parts):
                raise ValueError('Commit contains an unsafe checkout path')
            if os.name == 'nt':
                if any(len(part.encode('utf-16-le')) // 2 > 255 or part.endswith((' ', '.'))
                       or any(ord(char) < 32 or char in '\\:*?"<>|' for char in part)
                       or part.split('.')[0].upper() in reserved for part in parts):
                    raise ValueError('Commit contains a filename unsupported on Windows')
                if len(str(destination.joinpath(*parts)).encode('utf-16-le')) // 2 >= 32760:
                    raise ValueError('Tracked checkout path exceeds the Windows extended path limit')
            elif any(len(part.encode('utf-8')) > 255 for part in parts):
                raise ValueError('Commit contains a filename exceeding filesystem component limits')

    def bind(self, call):
        if call.name == 'spawn_worktree':
            return call.model_copy(update={'arguments': {**call.arguments, 'worktree_path': str(self.path(call.id))}})
        return call

    async def git(self, call_id, *arguments, raw=False):
        executable = shutil.which('git')
        if not executable:
            raise ValueError('Git is required for isolated worktrees')
        argv = [executable, '-c', f'core.hooksPath={os.devnull}', '-c', 'core.fsmonitor=false', '-c', 'core.longpaths=true', *arguments]
        result = await run_command(self.ctx, {'command': 'git ' + ' '.join(arguments), 'timeout_seconds': 60}, call_id,
                                   argv=argv, machine_output=True)
        if result.status != 'success':
            raise ValueError('Git operation failed: ' + result.content[:2000])
        return result.content if raw else result.content.strip()

    async def manage(self, args, call_id):
        child = next((c for c in self.ctx.repo.children(self.ctx.task_id) if c.id == args['child_id']), None)
        if child is None:
            raise ValueError('Checkout is not a child of this task')
        link = self.ctx.repo.db.rows('SELECT call_id FROM task_delegations WHERE child_id=:id', {'id': child.id})[0]
        target = Path(self.ctx.repo.workspace(child.workspace_id)['path']).absolute()
        managed = self.managed_root().absolute()
        if managed.resolve().is_relative_to(self.ctx.settings.data_dir.resolve()):
            raise PermissionError('Managed worktrees must be outside private application state')
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
            await self.git(call_id + ':remove', 'worktree', 'remove', self.creation_path(target))
        else:
            raise ValueError('Unknown worktree action')
        return ToolResult(call_id=call_id, content=json.dumps({'action': args['action'], 'child_id': child.id,
                         'source_commit': source_commit, 'path': str(target)}))

    async def spawn(self, args, call_id):
        prompt, capabilities = self.registry.roles.prompt(args.get('role', 'general'), args['prompt'], isolated=True)
        destination = self.path(call_id)
        managed = self.managed_root().absolute()
        if managed.resolve().is_relative_to(self.ctx.settings.data_dir.resolve()):
            raise PermissionError('Managed worktrees must be outside private application state')
        if managed.resolve() != managed:
            raise PermissionError('Managed worktree root was replaced by a link')
        if not destination.resolve().is_relative_to(managed):
            raise PermissionError('Managed worktree path was replaced by a link')
        try:
            creation_path = self.creation_path(destination)
        except ValueError as error:
            return ToolResult(call_id=call_id, status='error', error_code='WORKTREE_PATH_UNSUPPORTED', content=str(error))
        root = await self.git(call_id + ':root', 'rev-parse', '--show-toplevel')
        if Path(root).resolve() != self.ctx.workspace.resolve():
            raise ValueError('Register the Git repository root as the workspace')
        commit = await self.git(call_id + ':commit', 'rev-parse', '--verify', args['base_commit'] + '^{commit}')
        if commit.lower() != args['base_commit'].lower():
            raise ValueError('Worktree base must identify an exact commit')
        try:
            await self.path_preflight(call_id, commit, destination)
        except (ValueError, OSError) as error:
            return ToolResult(call_id=call_id, status='error', error_code='WORKTREE_PATH_UNSUPPORTED',
                              content='Checkout preflight rejected the path: ' + str(error) + '. Inspect the source repository and worktrees.managed_root.')
        if destination.exists():
            raise ValueError('Worktree destination already exists; inspect retained work before retrying')
        destination.parent.mkdir(parents=True, exist_ok=True)
        branch = 'muse-' + self.ctx.task_id[:12] + '-' + destination.name
        await self.git(call_id + ':create', 'worktree', 'add', '-b', branch, creation_path, commit)
        self.ctx.check()
        workspace = self.ctx.repo.register_workspace(str(destination), branch)
        child = self.ctx.repo.spawn_child(self.ctx.task_id, self.ctx.owner, self.ctx.epoch, call_id,
                                         prompt, workspace_id=workspace['id'], capabilities=capabilities)
        worktree = asdict(Worktree(name=branch, path=str(destination), branch=branch, based_on=commit, head_commit=commit))
        worktree['created'] = worktree['created'].isoformat()
        return ToolResult(call_id=call_id, content=json.dumps({'child_id': child.id, 'worktree': worktree}),
                          metadata={'worktree': worktree, 'child_id': child.id})
