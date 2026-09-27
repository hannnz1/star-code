import asyncio
import os
import sys
from pathlib import Path

import pytest


async def test_controlled_mcp_transport_reaps_orphan_on_normal_parent_exit(tmp_path):
    import psutil
    from mcp.client.stdio import StdioServerParameters
    from muse.extensions.stdio import controlled_stdio
    pidfile = tmp_path / 'child.pid'
    fixture = tmp_path / 'server.py'
    fixture.write_text('import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\nPath(sys.argv[1]).write_text(str(p.pid))\ntime.sleep(.2)\n')
    child = None
    try:
        async with controlled_stdio(StdioServerParameters(command=sys.executable, args=[str(fixture), str(pidfile)])):
            for _ in range(100):
                if pidfile.exists():
                    child = int(pidfile.read_text())
                    break
                await asyncio.sleep(.02)
            assert child is not None
            await asyncio.sleep(.3)
        for _ in range(100):
            if not psutil.pid_exists(child):
                break
            await asyncio.sleep(.02)
        assert not psutil.pid_exists(child)
    finally:
        if child and psutil.pid_exists(child):
            process = psutil.Process(child)
            if process.exe().lower() == str(Path(sys.executable).resolve()).lower():
                process.kill()


async def test_http_client_does_not_inherit_proxy_or_follow_redirects(monkeypatch):
    from contextlib import AsyncExitStack, asynccontextmanager
    from mewcode.config import MCPServerConfig
    from mewcode.mcp.client import MCPClient
    observed = {}
    @asynccontextmanager
    async def transport(url, http_client):
        observed['redirects'] = http_client.follow_redirects
        observed['trust_env'] = http_client._trust_env
        yield ('read', 'write', None)
    monkeypatch.setattr('mewcode.mcp.client.streamable_http_client', transport)
    client = MCPClient(MCPServerConfig(name='fixture', url='http://127.0.0.1:12345/mcp'))
    async with AsyncExitStack() as stack:
        client._stack = stack
        await client._connect_http()
    assert observed == {'redirects': False, 'trust_env': False}
