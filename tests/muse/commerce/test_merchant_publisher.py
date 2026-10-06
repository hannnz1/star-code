import copy
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation
from tests.muse.commerce.test_merchant_journal import (  # noqa: F401
    merchant_journal,
    merchant_review,
)
from tests.muse.commerce.test_site_release_steps import outcome


@pytest.fixture
def merchant_publisher(merchant_review, tmp_path):  # noqa: F811
    from muse.commerce_connector.merchant_authorization import MerchantReleaseAuthority
    from muse.commerce_connector.merchant_publisher import MerchantReleasePublisher
    journal, grant = merchant_journal(merchant_review, tmp_path)
    intent, connection = merchant_review[3], merchant_review[5]
    code = journal.approvals.frozen_code(intent)
    remote = {'snapshot': intent.initial_snapshot.model_dump(mode='json'), 'proofs': copy.deepcopy(merchant_review[-1]),
        'calls': [], 'receipts': {}, 'lose_reply': False}

    def transport(request):
        remote['calls'].append((request.method, request.url.path))
        if request.url.path.endswith('/capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2', 'theme_id': 'muse-storefront',
                'supported_operations': sorted({step.kind for step in intent.steps})})
        if request.url.path.endswith('/snapshot'): return httpx.Response(200, json=remote['snapshot'])
        if request.url.path.endswith('/resources'):
            params = request.url.params
            if 'media_sha256' in params: ref = 'media-sha256:' + params['media_sha256']
            elif 'page_slug' in params: ref = 'page-slug:' + hashlib.sha256(params['page_slug'].encode()).hexdigest()
            else: ref = 'sku:' + hashlib.sha256(params['sku'].strip().casefold().encode()).hexdigest()
            return httpx.Response(200, json=remote['proofs'][ref])
        if '/receipts/' in request.url.path:
            receipt = remote['receipts'].get(request.url.path.rsplit('/', 1)[1])
            return httpx.Response(200 if receipt else 404, json=receipt or {})
        assert request.method == 'POST' and request.url.path.endswith('/operations')
        operation = ChangeOperation.model_validate(json.loads(request.content)['operation'])
        before = normalize_snapshot(remote['snapshot'], intent.project_id, connection.environment)
        done, after = outcome(intent, connection, code, SimpleNamespace(operation=operation), before, remote['proofs'])
        remote['snapshot'] = after.model_dump(mode='json')
        remote['receipts'][operation.operation_id] = done.receipt.model_dump(mode='json')
        if remote['lose_reply']: raise httpx.ReadTimeout('Explicit fixture lost reply', request=request)
        return httpx.Response(200, json=done.receipt.model_dump(mode='json'))

    lock = {'verified': True, 'wordpress': '7.1.2', 'woocommerce': '11.1.2', 'theme': 'muse-storefront', 'php': '8.4.26',
        'database': '11.4.12', 'images': {name: name + '@sha256:' + 'a' * 64 for name in ('wordpress', 'database', 'cli')}}
    publisher = MerchantReleasePublisher(connection, journal,
        MerchantReleaseAuthority(b'x' * 32, clock=lambda: merchant_review[6][0]), versions_lock=lock,
        execution_enabled=True, transport=httpx.MockTransport(transport))
    return publisher, remote, grant


@pytest.mark.asyncio
async def test_merchant_broker_completes_18_steps_and_never_replays_consumed_release(merchant_publisher):
    publisher, remote, grant = merchant_publisher
    for index in range(18):
        result = await publisher.publish_next(grant.id)
        assert result.index == index and result.state == 'SUCCEEDED' and result.effect_verified
    assert len(remote['receipts']) == 18
    before = list(remote['calls'])
    assert await publisher.publish_next(grant.id) == result
    assert remote['calls'] == before


@pytest.mark.asyncio
async def test_merchant_broker_lost_image_reply_accounts_after_expiry_with_get_only(merchant_publisher, merchant_review):  # noqa: F811
    publisher, remote, grant = merchant_publisher
    remote['lose_reply'] = True
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    merchant_review[6][0] = grant.expires_at
    remote['calls'].clear()
    result = await publisher.publish_next(grant.id)
    assert result.state == 'SUCCEEDED' and result.effect_verified
    assert all(method == 'GET' for method, _ in remote['calls'])
    assert len(remote['receipts']) == 1
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['disabled', 'unverified', 'revoked'])
async def test_merchant_broker_rejects_unavailable_authority_before_any_post(merchant_publisher, condition):
    publisher, remote, grant = merchant_publisher
    if condition == 'disabled': publisher.execution_enabled = False
    elif condition == 'unverified': publisher.lock['verified'] = False
    else: publisher.approvals.revoke(grant.id, project_id=publisher.connection.project_id)
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    assert not any(method == 'POST' for method, _ in remote['calls'])
