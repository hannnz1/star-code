from test_api_contract import api


def test_terminal_submits_to_same_queue_and_controls_task(api):
    from muse.terminal import TerminalClient
    client, app = api
    workspace = client.get('/api/workspaces').json()[0]
    terminal = TerminalClient(client, workspace['id'])
    terminal.handle('Inspect the project')
    task = app.state.repository.get(terminal.task_id)
    assert task.status == 'QUEUED'
    assert task.prompt == 'Inspect the project'
    terminal.handle('/pause')
    assert app.state.repository.get(task.id).status == 'PAUSED'
    terminal.handle('/resume')
    terminal.handle('/cancel')
    assert app.state.repository.get(task.id).status == 'CANCELLED'


def test_terminal_plan_has_enforced_read_only_tools(api):
    from muse.terminal import TerminalClient
    from muse.tools.context import ExecutionContext
    from muse.tools.registry import ToolRegistry
    client, app = api
    workspace = client.get('/api/workspaces').json()[0]
    terminal = TerminalClient(client, workspace['id'])
    terminal.handle('/plan Explain the design')
    task = app.state.repository.get(terminal.task_id)
    assert task.read_only
    task = app.state.repository.claim_next('test')
    ctx = ExecutionContext(app.state.settings, app.state.repository, task, 'test')
    assert all(tool.risk == 'read' for tool in ToolRegistry(ctx).definitions())


def test_terminal_can_inspect_and_enter_child_workspace(api, tmp_path):
    import json
    from muse.terminal import TerminalClient
    client, app = api
    repo = app.state.repository
    workspace = client.get('/api/workspaces').json()[0]
    terminal = TerminalClient(client, workspace['id'])
    terminal.handle('Delegate inspection')
    parent = repo.claim_next('worker')
    isolated = tmp_path / 'isolated'
    isolated.mkdir()
    child_space = repo.register_workspace(str(isolated))
    child = repo.spawn_child(parent.id, 'worker', parent.lease_epoch, 'spawn', 'Inspect child', workspace_id=child_space['id'])
    assert json.loads(terminal.handle('/children'))[0]['id'] == child.id
    terminal.handle('/child ' + child.id)
    assert terminal.workspace_id == child_space['id']
    assert terminal.task_id == child.id
    terminal.handle('/back')
    assert terminal.task_id == parent.id
    assert terminal.workspace_id == workspace['id']


def test_terminal_never_approves_an_unreviewed_action(api):
    import pytest
    from muse.terminal import TerminalClient
    client, app = api
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    with pytest.raises(ValueError, match='approvals'):
        terminal.handle('/approve unknown-id')


def test_task_detail_reads_do_not_require_or_create_worker_lease(api):
    from muse.terminal import TerminalClient
    client, app = api
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    terminal.handle('Inspect project')
    response = client.get(f'/api/tasks/{terminal.task_id}/file-history')
    assert response.status_code == 200
    assert app.state.repository.db.rows('SELECT * FROM execution_budgets') == []


def test_terminal_rejects_different_server_configuration(api):
    import pytest
    from pydantic import SecretStr
    from muse.config import ProviderSettings
    from muse.terminal import validate_server
    _, app = api
    provider = ProviderSettings(name='Original', protocol='openai-responses', base_url='https://example.test/v1',
                                model='original-model', api_key=SecretStr('fixture'))
    settings = app.state.settings.model_copy(update={'provider': provider})
    public = settings.public()
    validate_server(settings, public)
    public['provider']['model'] = 'different-model'
    with pytest.raises(ValueError, match='configuration'):
        validate_server(settings, public)
