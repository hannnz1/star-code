import json
from pathlib import Path

import pytest

from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry
from test_agent_loop import ScriptedProvider, runtime
from test_durable_worktrees import git


async def test_worktree_merge_and_retirement_preserve_unmerged_and_dirty_work(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent')
    root = tmp_path / 'project'
    git(root, 'init')
    git(root, 'add', 'hello.txt')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    ctx = ExecutionContext(worker.settings, repo, parent, 'parent')
    manager = ToolRegistry(ctx).worktrees
    created = await manager.spawn({'base_commit': base, 'prompt': 'Inspect'}, 'spawn')
    child_id = json.loads(created.content)['child_id']
    child = repo.claim_next('child')
    repo.finish(child.id, 'child', child.lease_epoch, 'SUCCEEDED', 'Done')
    child_root = Path(repo.workspace(child.workspace_id)['path'])
    (child_root / 'hello.txt').write_text('child change')
    args = {'child_id': child_id, 'action': 'remove', 'source_commit': base, 'parent_commit': base}
    with pytest.raises(ValueError, match='clean'):
        await manager.manage(args, 'dirty-remove')
    git(child_root, 'add', 'hello.txt')
    git(child_root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'child')
    head = git(child_root, 'rev-parse', 'HEAD')
    with pytest.raises(ValueError, match='Git operation failed'):
        await manager.manage({**args, 'source_commit': head}, 'unmerged-remove')
    await manager.manage({**args, 'action': 'merge', 'source_commit': head}, 'merge')
    assert (root / 'hello.txt').read_text() == 'child change'
    await manager.manage({**args, 'source_commit': head, 'parent_commit': head}, 'remove')
    assert not child_root.exists()
    assert git(root, 'cat-file', '-t', head) == 'commit'
