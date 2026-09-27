import json

from sqlalchemy import text
from test_api_contract import api


def test_json_prompt_drains_terminal_events_across_pages(api, monkeypatch, capsys):
    from muse.compat_cli import execute_prompt
    from muse.terminal import TerminalClient
    client, app = api
    repo = app.state.repository
    terminal = TerminalClient(client, client.get('/api/workspaces').json()[0]['id'])
    submit = terminal.submit
    def finish_before_poll(*args, **kwargs):
        result = submit(*args, **kwargs)
        task = repo.claim_next('fixture')
        with repo.db.transaction() as conn:
            for index in range(1005):
                repo._event(conn, task.id, 'text_delta', {'text': str(index)})
        repo.finish(task.id, 'fixture', task.lease_epoch, 'SUCCEEDED', 'Done')
        return result
    monkeypatch.setattr(terminal, 'submit', finish_before_poll)
    assert execute_prompt(terminal, 'Long task', output_format='stream-json') == 0
    emitted = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    events = [row['event'] for row in emitted if row['type'] == 'event']
    with repo.db.engine.connect() as conn:
        expected = conn.execute(text('SELECT COUNT(*) FROM events WHERE task_id=:id'), {'id': terminal.task_id}).scalar_one()
    assert len(events) == expected
    assert events[-1]['type'] == 'status'
    assert events[-1]['payload']['status'] == 'SUCCEEDED'
    assert len({event['sequence'] for event in events}) == expected
