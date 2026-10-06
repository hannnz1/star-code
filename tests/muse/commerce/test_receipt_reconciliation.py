import gzip
import json

import httpx
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.commerce_connector.receipts import ReceiptReconciler
from muse.commerce_connector.wordpress import WordPressConnection


@pytest.mark.asyncio
@pytest.mark.parametrize('response_kind', ['success', 'failed', '404', 'timeout', 'wrong-digest', 'wrong-project', 'oversize', 'compressed'])
async def test_reconciliation_never_resends_and_only_verified_terminal_receipt_unlocks(tmp_path, response_kind):
    connection = WordPressConnection('connection', 'project', 'staging', 'https://store.example/shop', 'service', 'private-password')
    ledger = OperationLedger(tmp_path / 'operations.sqlite')
    ledger.bind_target('project', 'connection', 'staging', connection.base_url)
    operation = ChangeOperation(operation_id='op-1', kind='publish_owned_page', resource_key='page:12',
                                expected_fingerprint='a' * 64, payload={'page_id': 12})
    record = ledger.prepare('project', 'connection', 'staging', operation)
    ledger.begin('project', 'connection', 'staging', 'op-1')
    calls = []
    def remote(request):
        calls.append((request.method, str(request.url)))
        if response_kind == 'timeout':
            raise httpx.ReadTimeout('private-password', request=request)
        if response_kind == '404':
            return httpx.Response(404, text='private-password')
        if response_kind == 'oversize':
            return httpx.Response(200, content=b'x' * 16385)
        body = {
            'project_id': 'other' if response_kind == 'wrong-project' else 'project',
            'connection_id': 'connection', 'environment': 'staging', 'operation_id': 'op-1',
            'operation_digest': 'c' * 64 if response_kind == 'wrong-digest' else record.operation_digest,
            'resource_key': 'page:12', 'state': 'FAILED' if response_kind == 'failed' else 'SUCCEEDED',
            'fingerprint': None if response_kind == 'failed' else 'b' * 64,
        }
        if response_kind == 'compressed':
            return httpx.Response(200, content=gzip.compress(json.dumps(body).encode()),
                                  headers={'Content-Encoding': 'gzip'})
        return httpx.Response(200, json=body)
    reconciler = ReceiptReconciler(connection, ledger, transport=httpx.MockTransport(remote))
    if response_kind in ('success', 'failed'):
        result = await reconciler.reconcile('op-1')
        assert result.state == ('FAILED' if response_kind == 'failed' else 'SUCCEEDED')
        assert await reconciler.reconcile('op-1') == result
        ledger.prepare('project', 'connection', 'staging', operation.model_copy(update={'operation_id': 'op-2'}))
    else:
        with pytest.raises(CommerceFailure) as error:
            await reconciler.reconcile('op-1')
        assert 'private-password' not in str(error.value)
        assert ledger.get('project', 'connection', 'staging', 'op-1').state == 'NEEDS_RECONCILIATION'
        with pytest.raises(CommerceFailure):
            ledger.prepare('project', 'connection', 'staging', operation.model_copy(update={'operation_id': 'op-2'}))
    assert calls == [('GET', 'https://store.example/shop/wp-json/muse/v1/receipts/op-1')]

@pytest.mark.asyncio
async def test_direct_reconciler_rejects_rebound_target_without_http(tmp_path):
    connection = WordPressConnection('connection', 'project', 'staging', 'https://store.example', 'service', 'password')
    ledger = OperationLedger(tmp_path / 'ledger.sqlite')
    ledger.bind_target('project', 'connection', 'staging', connection.base_url)
    op = ChangeOperation(operation_id='op-1', kind='publish_owned_page', resource_key='page:12',
                         expected_fingerprint='a'*64, payload={'page_id': 12})
    ledger.prepare('project', 'connection', 'staging', op)
    ledger.begin('project', 'connection', 'staging', 'op-1')
    calls = []
    def remote(request):
        calls.append(request)
        return httpx.Response(404)
    rebound = WordPressConnection('connection', 'project', 'staging', 'https://another.example', 'service', 'password')
    with pytest.raises(CommerceFailure) as error:
        await ReceiptReconciler(rebound, OperationLedger(tmp_path / 'ledger.sqlite'), transport=httpx.MockTransport(remote)).reconcile('op-1')
    assert error.value.public.code == 'RESOURCE_CONFLICT'
    assert calls == []
    assert ledger.get('project', 'connection', 'staging', 'op-1').state == 'NEEDS_RECONCILIATION'
