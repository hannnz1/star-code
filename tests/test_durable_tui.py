import pytest

from test_api_contract import api


@pytest.mark.asyncio
async def test_textual_input_uses_durable_task_service(api):
    from muse.terminal import TerminalClient
    from muse.tui import MuseApp
    from textual.widgets import Input
    client, application = api
    workspace = client.get('/api/workspaces').json()[0]
    terminal = TerminalClient(client, workspace['id'])
    app = MuseApp(terminal)
    async with app.run_test() as pilot:
        app.query_one(Input).value = 'Inspect through Textual'
        await pilot.press('enter')
        for _ in range(30):
            await pilot.pause(.05)
            if terminal.task_id:
                break
        assert application.state.repository.get(terminal.task_id).prompt == 'Inspect through Textual'
        await app.handle_line('/pause')
        assert application.state.repository.get(terminal.task_id).status == 'PAUSED'
        await app.handle_line('/cancel')
        assert application.state.repository.get(terminal.task_id).status == 'CANCELLED'
