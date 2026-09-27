import asyncio

import pytest

from mewcode.hooks.engine import HookEngine
from mewcode.hooks.models import Action, Hook, HookContext


@pytest.mark.parametrize('iteration', range(10))
async def test_async_hook_shutdown_drains_owned_commands(iteration):
    engine = HookEngine([Hook(id='exit', event='post_tool_use',
        action=Action(type='command', command='echo completed'), async_exec=True)])
    assert callable(getattr(engine, 'close', None)), 'Background Hook owner needs an awaited shutdown'
    await engine.run_hooks('post_tool_use', HookContext(event_name='post_tool_use'))
    await engine.close()
    notifications = engine.drain_notifications()
    assert len(notifications) == 1
    assert notifications[0].success
    assert notifications[0].output == 'completed'
    assert not engine._background_tasks
    await engine.close()


@pytest.mark.parametrize('cancel', [False, True])
async def test_prompt_owner_drains_hooks_on_early_return_and_cancellation(monkeypatch, cancel):
    import mewcode.__main__ as cli
    engine = HookEngine([Hook(id='exit', event='post_tool_use',
        action=Action(type='command', command='echo completed'), async_exec=True)])
    async def implementation(*args):
        await engine.run_hooks('post_tool_use', HookContext(event_name='post_tool_use'))
        if cancel:
            raise asyncio.CancelledError
    monkeypatch.setattr(cli, '_run_prompt_impl', implementation, raising=False)
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await cli._run_prompt(None, None, engine, 'test')
    else:
        await cli._run_prompt(None, None, engine, 'test')
    assert engine.drain_notifications()[0].output == 'completed'
    assert not engine._background_tasks
