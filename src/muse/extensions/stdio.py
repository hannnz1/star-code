"""MCP transport with the same descendant lifetime boundary as command tools."""
import asyncio
from contextlib import asynccontextmanager

import anyio
from mcp.client.stdio import get_default_environment
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage

from muse.tools.process_tree import ProcessTree


@asynccontextmanager
async def controlled_stdio(server, errlog=None):
    process = await asyncio.create_subprocess_exec(server.command, *server.args,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        env={**get_default_environment(), **(server.env or {})}, cwd=server.cwd,
        limit=1024 * 1024, **ProcessTree.launch_options())
    tree = None
    incoming, read = anyio.create_memory_object_stream(0)
    write, outgoing = anyio.create_memory_object_stream(0)
    try:
        tree = ProcessTree(process.pid)
        async def reader():
            async with incoming:
                while line := await process.stdout.readline():
                    try:
                        item = SessionMessage(JSONRPCMessage.model_validate_json(line))
                    except ValueError as error:
                        item = error
                    await incoming.send(item)
        async def writer():
            async with outgoing:
                async for item in outgoing:
                    process.stdin.write((item.message.model_dump_json(by_alias=True, exclude_none=True) + '\n').encode())
                    await process.stdin.drain()
        async with anyio.create_task_group() as group:
            group.start_soon(reader)
            group.start_soon(writer)
            try:
                yield read, write
            finally:
                tree.close()
                group.cancel_scope.cancel()
    finally:
        if tree:
            tree.close()
        elif process.returncode is None:
            process.kill()
        with anyio.CancelScope(shield=True):
            with anyio.move_on_after(3):
                await process.wait()
            await read.aclose()
            await write.aclose()
