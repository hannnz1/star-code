from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mewcode.config import MCPServerConfig
from mewcode.mcp.client import MCPClient


async def test_mcp_collects_pages_and_rejects_repeated_cursor():
    client = MCPClient(MCPServerConfig(name='fixture', command='fixture'))
    client._session = SimpleNamespace(list_tools=AsyncMock(side_effect=[
        SimpleNamespace(tools=['first'], nextCursor='second'),
        SimpleNamespace(tools=['last'], nextCursor=None)]))
    assert await client.list_tools() == ['first', 'last']
    client._session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[], nextCursor='loop'))
    with pytest.raises(ValueError, match='cursor'):
        await client.list_tools()
