import hashlib

import httpx
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce_connector.wordpress import WordPressConnection, WordPressReader


@pytest.mark.asyncio
async def test_sku_absence_uses_explicit_bounded_resource_query():
    seen = []
    sku = 'Straße / cup'
    state = {'sku': sku.casefold(), 'exists': False}
    key = 'sku:' + hashlib.sha256(sku.casefold().encode()).hexdigest()

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={'resource_key': key, 'fingerprint': digest(state), 'state': state})

    connection = WordPressConnection('conn', 'project', 'staging', 'https://shop.example', 'user', 'private')
    result = await WordPressReader(connection, transport=httpx.MockTransport(handle)).read_sku(sku, remaining_seconds=10)
    assert result['resource_key'] == key and result['fingerprint'] == digest(state)
    assert len(seen) == 1 and seen[0].method == 'GET'
    assert seen[0].url.path == '/wp-json/muse/v1/resources' and seen[0].url.params['sku'] == sku


@pytest.mark.asyncio
@pytest.mark.parametrize('corruption', ['resource', 'digest', 'sku', 'exists', 'unknown', 'product_id'])
async def test_sku_absence_rejects_malformed_or_unbound_remote_proof(corruption):
    state = {'sku': 'cup', 'exists': False}
    result = {'resource_key': 'sku:' + hashlib.sha256(b'cup').hexdigest(), 'fingerprint': digest(state), 'state': state}
    if corruption == 'resource': result['resource_key'] = 'sku:' + 'e' * 64
    elif corruption == 'digest': result['fingerprint'] = 'd' * 64
    elif corruption == 'sku': state['sku'] = 'other'
    elif corruption == 'exists': state['exists'] = 0
    elif corruption == 'unknown': state['extra'] = True
    else: state['product_id'] = 1
    connection = WordPressConnection('conn', 'project', 'staging', 'https://shop.example', 'user', 'private')
    reader = WordPressReader(connection, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=result)))
    with pytest.raises(CommerceFailure):
        await reader.read_sku('cup', remaining_seconds=10)
