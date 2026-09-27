import json

import pytest
from sqlalchemy import text
from test_api_contract import api


def test_compact_requires_inactive_turn_and_preserves_goal_and_tool_pair(api):
    from muse.terminal import TerminalClient
    client, app = api
    repo = app.state.repository
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    terminal.handle('Original goal')
    terminal.handle('/pause')
    messages = [{'role': 'user', 'content': 'Original goal'}]
    messages += [{'role': 'assistant', 'content': str(i) * 3000} for i in range(20)]
    messages += [{'role': 'assistant', 'tool_calls': [{'id': 'last', 'name': 'read_file', 'arguments': {'path': 'file'}}]},
                 {'role': 'tool', 'tool_call_id': 'last', 'content': 'Evidence'}, {'role': 'user', 'content': 'Latest request'}]
    with repo.db.transaction() as conn:
        conn.execute(text('UPDATE tasks SET checkpoint=:cp WHERE id=:id'), {'id': terminal.task_id, 'cp': json.dumps({'messages': messages})})
    terminal.handle('/compact')
    saved = repo.get(terminal.task_id)
    assert repo.conversation_checkpoints(terminal.task_id), 'Manual compaction must archive the original messages for recall'
    assert saved.status == 'PAUSED'
    assert len(saved.checkpoint['messages']) < len(messages)
    assert saved.checkpoint['messages'][0]['content'] == 'Original goal'
    assert saved.checkpoint['messages'][-1]['content'] == 'Latest request'
    assert any(m.get('tool_call_id') == 'last' for m in saved.checkpoint['messages'])
    terminal.handle('/resume')
    repo.claim_next('worker')
    with pytest.raises(Exception):
        terminal.handle('/compact')


def test_command_completion_matches_public_commands():
    from muse.terminal import complete_command
    assert '/compact' in complete_command('/com')
    assert '/cancel' in complete_command('/can')
    assert complete_command('ordinary text') == []


def test_manual_compaction_preserves_new_evidence_at_existing_sequence(api):
    from muse.agent.context import recall_history
    from types import SimpleNamespace
    client, app = api
    repo = app.state.repository
    from muse.terminal import TerminalClient
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    terminal.handle('Goal')
    terminal.handle('/pause')
    original = [{'role': 'user', 'content': 'Original checkpoint'}]
    messages = [{'role': 'user', 'content': 'Goal'},
                {'role': 'user', 'content': 'New needle ' + 'x' * 15000}]
    with repo.db.transaction() as conn:
        conn.execute(text('INSERT INTO conversation_checkpoints VALUES(:id,0,:messages,0)'),
                     {'id': terminal.task_id, 'messages': json.dumps(original)})
        conn.execute(text('UPDATE tasks SET checkpoint=:cp WHERE id=:id'),
                     {'id': terminal.task_id, 'cp': json.dumps({'messages': messages, 'model_requests': 0})})
    terminal.handle('/compact')
    ctx = SimpleNamespace(repo=repo, task_id=terminal.task_id, safe=lambda value: value)
    assert 'New needle' in recall_history(ctx, 'New needle')
    old = repo.db.rows('SELECT messages FROM conversation_checkpoints WHERE task_id=:id AND sequence=0', {'id': terminal.task_id})
    assert json.loads(old[0]['messages']) == original


def test_terminal_conversation_rewind_uses_durable_fork(api):
    from muse.terminal import TerminalClient
    client, app = api
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    terminal.handle('Original goal')
    source = terminal.task_id
    task = app.state.repository.claim_next('worker')
    app.state.repository.save_conversation_checkpoint(source, 'worker', task.lease_epoch, 0,
        [{'role': 'user', 'content': 'Original goal'}])
    terminal.handle('/pause')
    assert json.loads(terminal.handle('/checkpoints'))[0]['sequence'] == 0
    app.state.repository.abandon(source, 'worker', task.lease_epoch)
    fork = json.loads(terminal.handle('/rewind 0 conversation Continue here'))
    assert fork['id'] != source
    assert terminal.task_id == fork['id']


def test_extension_inspection_commands_do_not_dispatch_tools(api):
    from muse.terminal import TerminalClient
    client, app = api
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    terminal.handle('Inspect')
    for command in ('/hooks', '/permission', '/active-skills', '/reload-skills', '/worktree'):
        json.loads(terminal.handle(command))
    assert app.state.repository.calls(terminal.task_id) == []
