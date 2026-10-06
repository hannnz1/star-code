import asyncio
import socket

import pytest

from muse.commerce.preview_proxy import LoopbackPreviewProxy


@pytest.mark.parametrize('address', ['127.0.0.1', '169.254.169.254', '8.8.8.8', 'example.com', '::1'])
def test_preview_rejects_public_metadata_loopback_and_hostname_targets(address):
    with pytest.raises(ValueError):
        LoopbackPreviewProxy(address, 18081)


async def test_preview_relays_fixed_target_and_closes_listener(monkeypatch):
    async def echo(reader, writer):
        writer.write(await reader.read(4))
        await writer.drain()
        writer.close()
    upstream = await asyncio.start_server(echo, '127.0.0.1', 0)
    open_connection = asyncio.open_connection
    targets = []
    async def connect(address, port):
        targets.append((address, port))
        return await open_connection('127.0.0.1', upstream.sockets[0].getsockname()[1])
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    proxy = LoopbackPreviewProxy('172.20.0.3', port)
    monkeypatch.setattr(asyncio, 'open_connection', connect)
    await proxy.start()
    try:
        assert proxy.server.sockets[0].getsockname()[:2] == ('127.0.0.1', port)
        reader, writer = await open_connection('127.0.0.1', port)
        writer.write(b'muse')
        await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(4), timeout=3) == b'muse'
        writer.close()
        await writer.wait_closed()
        assert targets == [('172.20.0.3', 80)]
    finally:
        await proxy.close()
        upstream.close()
        await upstream.wait_closed()
    with pytest.raises(OSError):
        await open_connection('127.0.0.1', port)
