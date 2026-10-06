"""Host-owned loopback preview relay for a fixed isolated CMS address.

No URL, proxy target, credentials or network settings are accepted from agents.
The runner must validate the container and its private network before calling.
"""
import asyncio
import ipaddress


class LoopbackPreviewProxy:
    def __init__(self, address, port):
        ip = ipaddress.IPv4Address(address)
        if not ip.is_private or ip.is_loopback or ip.is_link_local or not 1024 <= port <= 65535:
            raise ValueError('Private CMS address and loopback listener port required')
        self.address, self.port = str(ip), port
        self.server = None
        self.clients = set()

    async def start(self):
        if self.server is not None:
            raise ValueError('Preview listener already started')
        self.server = await asyncio.start_server(self._relay, '127.0.0.1', self.port)
        if any(sock.getsockname()[:2] != ('127.0.0.1', self.port) for sock in self.server.sockets):
            await self.close()
            raise ValueError('Loopback binding failed')

    async def _relay(self, reader, writer):
        task = asyncio.current_task()
        if len(self.clients) >= 32:
            writer.close()
            return
        self.clients.add(task)
        upstream = None
        async def copy(source, target):
            while data := await source.read(65536):
                target.write(data)
                await target.drain()
            if target.can_write_eof():
                target.write_eof()
        try:
            async with asyncio.timeout(30):
                remote, upstream = await asyncio.open_connection(self.address, 80)
                await asyncio.gather(copy(reader, upstream), copy(remote, writer))
        except (OSError, TimeoutError):
            pass
        finally:
            writer.close()
            if upstream is not None:
                upstream.close()
            self.clients.discard(task)

    async def close(self):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        tasks = list(self.clients)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
