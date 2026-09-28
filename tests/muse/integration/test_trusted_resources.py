import json

from test_permission_modes import setup

from muse.agent.instructions import project_guidance
from muse.contracts import ToolCall
from muse.extensions.roles import DurableRoles


def write_role(path, name, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\nname: {name}\ndescription: Custom role\n---\n{text}', encoding='utf-8')


def test_user_project_nested_local_order_and_frozen_reload(tmp_path):
    _, _, ctx, _ = setup(tmp_path)
    user = tmp_path / 'trusted'
    user.mkdir()
    (user / 'MUSE.md').write_text('user preference', encoding='utf-8')
    (ctx.workspace / 'MUSE.md').write_text('project preference', encoding='utf-8')
    nested = ctx.workspace / 'app'
    nested.mkdir()
    (nested / 'MUSE.md').write_text('nested preference', encoding='utf-8')
    (nested / 'MUSE.local.md').write_text('local preference', encoding='utf-8')
    ctx.settings.instruction_roots = [user]
    ctx.cp['current_directory'] = 'app'
    ctx.cp.pop('project_guidance', None)
    result = project_guidance(ctx)
    assert result.index('user preference') < result.index('project preference') < result.index('nested preference') < result.index('local preference')
    (user / 'MUSE.md').write_text('changed preference', encoding='utf-8')
    assert project_guidance(ctx) == result
    ctx.cp.pop('project_guidance')
    assert 'changed preference' in project_guidance(ctx)


async def test_project_role_overrides_user_and_worker_snapshot_is_stable(tmp_path):
    _, _, ctx, tools = setup(tmp_path)
    user = tmp_path / 'roles'
    write_role(user / 'helper.md', 'helper', 'User behavior')
    write_role(ctx.workspace / '.muse/agents/helper.md', 'helper', 'Project behavior')
    ctx.settings.agent_roots = [user]
    ctx.cp.pop('role_snapshot', None)
    roles = DurableRoles(type('Registry', (), {'context': ctx, 'register': lambda *args: None})())
    catalog = json.loads(await roles.list({}, 'catalog'))
    assert roles.custom['helper']['body'].strip() == 'Project behavior'
    assert len(catalog['sources']) == 2
    write_role(ctx.workspace / '.muse/agents/helper.md', 'helper', 'New behavior')
    restarted = DurableRoles(type('Registry', (), {'context': ctx, 'register': lambda *args: None})())
    assert restarted.custom['helper']['body'].strip() == 'Project behavior'
    assert (await tools.execute(ToolCall(id='root-edit', name='register_instruction_root', arguments={'path': str(user)}))).status == 'error'


def test_unregistered_home_and_outside_include_are_denied(tmp_path):
    _, _, ctx, _ = setup(tmp_path)
    outside = tmp_path / 'outside.md'
    outside.write_text('outside confidential data', encoding='utf-8')
    (ctx.workspace / 'MUSE.md').write_text('@' + outside.as_posix(), encoding='utf-8')
    result = project_guidance(ctx)
    assert 'outside confidential data' not in result
