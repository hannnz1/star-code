import io
import zipfile

import pytest

from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry
from test_agent_loop import ScriptedProvider, runtime


def test_pinned_skill_archive_install_rejects_escape_and_preserves_existing(tmp_path):
    from muse.extensions.skill_install import install_archive
    commit = 'a' * 40
    def archive(name='SKILL.md'):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr(f'repo-{commit}/skills/audit/{name}', '---\nname: audit\ndescription: Inspect files\n---\nRead carefully.')
        return data.getvalue()
    args = {'repository': 'owner/repo', 'commit': commit, 'path': 'skills/audit', 'name': 'audit'}
    target = tmp_path / 'project'
    target.mkdir()
    installed = install_archive(target, args, archive())
    assert (target / '.muse/skills/audit/SKILL.md').is_file()
    assert installed['commit'] == commit
    with pytest.raises(ValueError, match='exists'):
        install_archive(target, args, archive())
    with pytest.raises(ValueError):
        install_archive(target, {**args, 'name': 'second'}, archive('../../../outside.txt'))
    assert not (target / 'outside.txt').exists()


async def test_explicit_global_skill_root_is_visible_without_implicit_home_scan(tmp_path):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    task = repo.claim_next('worker')
    directory = tmp_path / 'selected-global/inspect'
    directory.mkdir(parents=True)
    (directory / 'SKILL.md').write_text('---\nname: inspect\ndescription: Inspect files\n---\nRead only.')
    settings = worker.settings.model_copy(update={'skill_roots': [directory.parent]})
    registry = ToolRegistry(ExecutionContext(settings, repo, task, 'worker'))
    assert 'inspect' in await registry.skills.list({}, 'list')


def test_invalid_yaml_skill_never_installs(tmp_path):
    from muse.extensions.skill_install import install_archive
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('repo/skill.yaml', '[]')
        z.writestr('repo/prompt.md', 'Inspect')
    args = {'repository': 'owner/repo', 'commit': 'a' * 40, 'path': '.', 'name': 'audit'}
    with pytest.raises(ValueError, match='Skill'):
        install_archive(tmp_path, args, data.getvalue())
    assert not (tmp_path / '.muse/skills/audit').exists()
