from muse.config import load_settings
from muse.contracts import TaskRequest, ToolCall
from muse.tasks.repository import TaskRepository
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry


async def test_explicit_no_changes_request_enforces_read_only_tools(tmp_path):
    settings = load_settings(data_dir=tmp_path / 'data', require_provider=False)
    repo = TaskRepository(settings.data_dir / 'state.sqlite3')
    workspace = tmp_path / 'project'
    workspace.mkdir()
    source = workspace / 'calculator.py'
    source.write_text('value = 1\n', encoding='utf-8')
    ws = repo.register_workspace(str(workspace))
    request = TaskRequest(prompt='Explain this project without changing any files: entry point and imports.',
                          workspace_id=ws['id'], scenario='coding', client_request_id='read-only')
    task = repo.create(request)
    assert task.read_only is True
    assert repo.create(request).id == task.id

    claimed = repo.claim_next('worker')
    context = ExecutionContext(settings, repo, claimed, 'worker')
    registry = ToolRegistry(context)
    assert 'edit_file' not in {definition.name for definition in registry.definitions()}
    result = await registry.execute(ToolCall(id='edit', name='edit_file', arguments={
        'path': 'calculator.py', 'old_text': 'value = 1', 'new_text': 'value = 2'}))
    assert result.status == 'error'
    assert source.read_text(encoding='utf-8') == 'value = 1\n'


def test_editing_a_read_only_feature_remains_writable(tmp_path):
    settings = load_settings(data_dir=tmp_path / 'data', require_provider=False)
    repo = TaskRepository(settings.data_dir / 'state.sqlite3')
    workspace = tmp_path / 'project'
    workspace.mkdir()
    ws = repo.register_workspace(str(workspace))
    task = repo.create(TaskRequest(prompt='Implement a read-only mode in calculator.py and run tests.', workspace_id=ws['id'],
                                   scenario='coding', client_request_id='edit'))
    assert task.read_only is False


def test_read_only_inspection_followed_by_repair_remains_writable(tmp_path):
    settings = load_settings(data_dir=tmp_path / 'data', require_provider=False)
    repo = TaskRepository(settings.data_dir / 'state.sqlite3')
    workspace = tmp_path / 'project'
    workspace.mkdir()
    ws = repo.register_workspace(str(workspace))
    for prompt in ('Inspect tests without changing code, then fix the bug',
                   '先只读检查代码，然后修改文件修复问题'):
        task = repo.create(TaskRequest(prompt=prompt, workspace_id=ws['id'],
                                       scenario='coding', client_request_id=prompt))
        assert task.read_only is False
