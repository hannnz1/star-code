"""Real-platform acceptance probes; never substitute simulated argv assertions."""
import asyncio
import platform
import sys
from pathlib import Path

import pytest
from test_permission_modes import setup

from muse.permissions.os_sandbox import capabilities
from muse.tools.context import TaskControl
from muse.tools.shell import run_command


@pytest.mark.skipif(platform.system() not in {'Linux', 'Darwin'}, reason='Real Linux/macOS sandbox host required')
async def test_real_platform_denies_external_files_network_and_preserves_workspace(tmp_path):
    if not capabilities()['available']:
        pytest.fail('required sandbox backend is missing on this acceptance host')
    _, _, ctx, _ = setup(tmp_path)
    ctx.settings.sandbox_policy = 'required'
    # Explicit interpreter runtime for this fixture, never the host home directory.
    ctx.settings.sandbox_runtime_roots = [Path(sys.base_prefix)]
    outside = tmp_path / 'sentinel-outside.txt'
    outside.write_text('outside sentinel', encoding='utf-8')
    program = ctx.workspace / 'sandbox_probe.py'
    program.write_text('''import pathlib, socket, subprocess, sys
outside=pathlib.Path(sys.argv[1])
for action in (lambda: outside.read_text(), lambda: outside.write_text('violated')):
    try: action()
    except (OSError, PermissionError): pass
    else: raise AssertionError('external access allowed')
try: socket.create_connection(('1.1.1.1',443),timeout=1)
except OSError: pass
else: raise AssertionError('network allowed')
pathlib.Path('normal.txt').write_text('normal compilation output')
subprocess.run([sys.executable,'-c','print("child alive")'],check=True)
''', encoding='utf-8')
    result = await run_command(ctx, {'command': 'fixture', 'timeout_seconds': 30}, 'platform-probe',
                               argv=[sys.executable, str(program), str(outside)], verify=True)
    assert result.status == 'success', result.content
    assert outside.read_text() == 'outside sentinel'
    assert (ctx.workspace / 'normal.txt').exists()
    # A sleeping managed descendant must terminate when the task is cancelled.
    operation = asyncio.create_task(run_command(ctx, {'command': 'fixture', 'timeout_seconds': 30}, 'cancel-probe',
        argv=[sys.executable, '-c', 'import time; time.sleep(20)']))
    await asyncio.sleep(0.2)
    current = ctx.repo.get(ctx.task_id)
    ctx.repo.control(ctx.task_id, 'cancel', expected_revision=current.revision)
    with pytest.raises(TaskControl) as stopped:
        await operation
    assert stopped.value.status == 'CANCELLED'
