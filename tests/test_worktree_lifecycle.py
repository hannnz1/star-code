import json
from pathlib import Path

import pytest
from test_agent_loop import ScriptedProvider, runtime
from test_durable_worktrees import git

from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry


async def test_worktree_merge_and_retirement_preserve_unmerged_and_dirty_work(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent', ttl=600)
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


async def test_reviewed_divergent_child_can_be_integrated_without_discarding_parent(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent', ttl=600)
    root = tmp_path / 'project'
    git(root, 'init')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'add', 'hello.txt')
    git(root, 'commit', '-m', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    manager = ToolRegistry(ExecutionContext(worker.settings, repo, parent, 'parent')).worktrees
    created = await manager.spawn({'base_commit': base, 'prompt': 'Inspect'}, 'spawn')
    child_id = json.loads(created.content)['child_id']
    child = repo.claim_next('child')
    repo.finish(child.id, 'child', child.lease_epoch, 'SUCCEEDED', 'Done')
    child_root = Path(repo.workspace(child.workspace_id)['path'])
    (child_root / 'child.txt').write_text('child contribution')
    git(child_root, 'add', 'child.txt')
    git(child_root, 'commit', '-m', 'child')
    source = git(child_root, 'rev-parse', 'HEAD')
    (root / 'parent.txt').write_text('parent contribution')
    git(root, 'add', 'parent.txt')
    git(root, 'commit', '-m', 'parent')
    head = git(root, 'rev-parse', 'HEAD')
    await manager.manage({'child_id': child_id, 'action': 'integrate', 'source_commit': source, 'parent_commit': head}, 'integrate')
    assert (root / 'child.txt').read_text() == 'child contribution'
    assert (root / 'parent.txt').read_text() == 'parent contribution'
    assert child_root.is_dir()
    git(root, 'merge-base', '--is-ancestor', source, 'HEAD')
    git(root, 'merge-base', '--is-ancestor', head, 'HEAD')


async def test_second_child_stale_review_explains_refresh_without_merging(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent', ttl=600)
    root = tmp_path / 'project'
    git(root, 'init')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'add', 'hello.txt')
    git(root, 'commit', '-m', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    manager = ToolRegistry(ExecutionContext(worker.settings, repo, parent, 'parent')).worktrees
    children = []
    for index in (1, 2):
        created = await manager.spawn({'base_commit': base, 'prompt': f'Component {index}'}, f'spawn-{index}')
        child_id = json.loads(created.content)['child_id']
        child = repo.claim_next(f'child-{index}')
        repo.finish(child.id, f'child-{index}', child.lease_epoch, 'SUCCEEDED', 'Done')
        child_root = Path(repo.workspace(child.workspace_id)['path'])
        (child_root / f'component-{index}.txt').write_text(str(index))
        git(child_root, 'add', f'component-{index}.txt')
        git(child_root, 'commit', '-m', f'component {index}')
        children.append((child_id, git(child_root, 'rev-parse', 'HEAD')))

    first, second = children
    await manager.manage({'child_id': first[0], 'action': 'integrate',
                          'source_commit': first[1], 'parent_commit': base}, 'integrate-first')
    with pytest.raises(ValueError, match='review.*again'):
        await manager.manage({'child_id': second[0], 'action': 'integrate',
                              'source_commit': second[1], 'parent_commit': base}, 'stale-second')
    assert not (root / 'component-2.txt').exists()
