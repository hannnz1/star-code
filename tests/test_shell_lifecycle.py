import asyncio
import json
import os
import shlex
import subprocess
import sys

import psutil
import pytest
from mewcode.tools.bash import Bash, Params


def command(script):
    args = [sys.executable, str(script)]
    return subprocess.list2cmdline(args) if os.name == 'nt' else shlex.join(args)


async def test_agent_shell_uses_selected_workspace(tmp_path):
    from test_agent import MockLLMClient
    from mewcode.agent import Agent, ToolResultEvent
    from mewcode.conversation import ConversationManager
    from mewcode.tools import create_default_registry
    from mewcode.tools.base import ToolCallComplete, StreamEnd
    script = tmp_path / 'location.py'
    script.write_text('import os\nprint(os.getcwd())')
    client = MockLLMClient([[ToolCallComplete('c', 'Bash', {'command': command(script)}),
                            StreamEnd('tool_use')], [StreamEnd('end_turn')]])
    agent = Agent(client, create_default_registry(), 'openai', work_dir=str(tmp_path))
    conversation = ConversationManager()
    conversation.add_user_message('Check working directory')
    events = [e async for e in agent.run(conversation)]
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.output.strip() == str(tmp_path)


async def test_failed_command_has_structured_exit_code(tmp_path):
    script = tmp_path / 'failure.py'
    script.write_text('print("failure evidence")\nraise SystemExit(3)')
    tool = Bash()
    tool.work_dir = str(tmp_path)
    result = await tool.execute(Params(command=command(script)))
    assert result.is_error
    assert result.exit_code == 3
    assert 'failure evidence' in result.output


@pytest.mark.parametrize('mode', ['timeout', 'cancel', 'parent_exit'])
async def test_command_owns_descendants(tmp_path, mode):
    parent = tmp_path / 'parent.py'
    child = tmp_path / 'child.py'
    child.write_text('import time\ntime.sleep(120)')
    parent.write_text('import subprocess,sys,pathlib,json,time,os\n'
        'p=subprocess.Popen([sys.executable,"child.py"])\n'
        'pathlib.Path("pids.json").write_text(json.dumps([os.getpid(),p.pid]))\n'
        + ('time.sleep(120)\n' if mode != 'parent_exit' else ''))
    tool = Bash()
    tool.work_dir = str(tmp_path)
    task = asyncio.create_task(tool.execute(Params(command=command(parent), timeout=2)))
    pids = []
    try:
        for _ in range(100):
            if (tmp_path / 'pids.json').exists():
                pids = json.loads((tmp_path / 'pids.json').read_text())
                break
            await asyncio.sleep(.02)
        assert pids, 'parent did not start'
        if mode == 'cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await asyncio.wait_for(task, 5)
            assert result.is_error == (mode == 'timeout')
        for _ in range(100):
            if not any(psutil.pid_exists(pid) for pid in pids):
                break
            await asyncio.sleep(.02)
        assert not any(psutil.pid_exists(pid) for pid in pids)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for pid in pids:
            try:
                psutil.Process(pid).kill()
            except psutil.NoSuchProcess:
                pass
