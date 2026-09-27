import pytest


@pytest.mark.parametrize('name,risk,expected', [
    ('mcp_call', 'execute', True),
    ('__hook_0', 'execute', True),
    ('__hook_1', 'read', False),
    ('future_extension', 'write', True),
    ('verify_command', 'execute', False),
    ('mcp_discover', 'execute', True),
    ('spawn_task', 'execute', False),
    ('spawn_skill', 'execute', False),
    ('save_artifact', 'write', False),
])
def test_verification_tracks_extension_attempts(name, risk, expected):
    from muse.tools.verification import mutation_ids
    call = {'id': 'action', 'name': name, 'risk': risk, 'attempts': 1}
    assert mutation_ids([call]) == ({'action'} if expected else set())
    call['attempts'] = 0
    assert mutation_ids([call]) == set()


async def test_command_hook_cannot_report_unverified_success(tmp_path):
    from test_durable_hooks import test_command_hook_requires_approval_before_read
    await test_command_hook_requires_approval_before_read(tmp_path)
    from muse.tasks.repository import TaskRepository
    repo = TaskRepository(tmp_path / 'data/state.sqlite3')
    task = repo.db.rows('SELECT status,error FROM tasks')[0]
    assert task['status'] == 'FAILED'
    assert 'verification' in task['error'].lower()
