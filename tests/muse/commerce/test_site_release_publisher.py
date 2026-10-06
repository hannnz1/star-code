import copy
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation
from muse.commerce.repository import digest
from tests.muse.commerce.test_site_release_approval import site_review  # noqa: F401
from tests.muse.commerce.test_site_release_journal import journal, outcome, proofs_for


@pytest.fixture
def site_publisher(site_review, tmp_path):  # noqa: F811
    from muse.commerce_connector.site_authorization import SiteReleaseAuthority
    from muse.commerce_connector.site_publisher import SiteReleasePublisher
    execution, grant = journal(site_review, tmp_path)
    intent, connection = site_review[3], site_review[5]
    code = execution.approvals.frozen_code(intent)
    remote = {'snapshot': copy.deepcopy(intent.initial_snapshot.model_dump(mode='json')), 'calls': [], 'receipts': {}, 'lose_reply': False}

    def identity_proof(name, identity):
        snapshot = normalize_snapshot(remote['snapshot'], intent.project_id, connection.environment)
        kind = 'page' if name == 'slug' else 'product'
        canonical = identity if name == 'slug' else identity.strip().casefold()
        entity = next((item for item in getattr(snapshot, kind + 's') if
                       (item.get(name, '') if name == 'slug' else item.get(name, '').strip().casefold()) == canonical), None)
        state = {name: canonical, 'exists': entity is not None}
        if entity: state.update({kind + '_id': entity['id'], 'entity_fingerprint': digest(entity)})
        ref = ('page-slug:' if name == 'slug' else 'sku:') + hashlib.sha256(canonical.encode()).hexdigest()
        return {'resource_key': ref, 'state': state, 'fingerprint': digest(state)}

    def transport(request):
        remote['calls'].append((request.method, request.url.path))
        if request.url.path.endswith('/capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2', 'theme_id': 'muse-storefront',
                'supported_operations': sorted({step.kind for step in intent.steps})})
        if request.url.path.endswith('/snapshot'): return httpx.Response(200, json=remote['snapshot'])
        if request.url.path.endswith('/resources'):
            parameter = 'page_slug' if 'page_slug' in request.url.params else 'sku'
            return httpx.Response(200, json=identity_proof('slug' if parameter == 'page_slug' else 'sku', request.url.params[parameter]))
        if '/receipts/' in request.url.path:
            receipt = remote['receipts'].get(request.url.path.rsplit('/', 1)[1])
            return httpx.Response(200 if receipt else 404, json=receipt or {})
        assert request.method == 'POST' and request.url.path.endswith('/operations')
        operation = ChangeOperation.model_validate(json.loads(request.content)['operation'])
        snapshot = normalize_snapshot(remote['snapshot'], intent.project_id, connection.environment)
        done, after = outcome(intent, connection, code, SimpleNamespace(operation=operation), snapshot, proofs_for(intent))
        receipt = done.receipt.model_dump(mode='json')
        remote['snapshot'], remote['receipts'][operation.operation_id] = after.model_dump(mode='json'), receipt
        if remote['lose_reply']: raise httpx.ReadTimeout('private test lost reply', request=request)
        return httpx.Response(200, json=receipt)

    lock = {'verified': True, 'wordpress': '7.1.2', 'woocommerce': '11.1.2', 'theme': 'muse-storefront', 'php': '8.4.26',
            'database': '11.4.12', 'images': {name: name + '@sha256:' + 'a' * 64 for name in ('wordpress', 'database', 'cli')}}
    publisher = SiteReleasePublisher(connection, execution,
        SiteReleaseAuthority(b'x' * 32, clock=lambda: site_review[-1][0]), versions_lock=lock,
        execution_enabled=True, transport=httpx.MockTransport(transport))
    return publisher, remote, grant, connection


@pytest.mark.asyncio
async def test_site_broker_runs_full_build_and_duplicate_completion_never_posts(site_publisher):
    publisher, remote, grant, _ = site_publisher
    for index in range(17):
        result = await publisher.publish_next(grant.id)
        assert result.state == 'SUCCEEDED' and result.effect_verified and result.index == index
    before = list(remote['calls'])
    assert await publisher.publish_next(grant.id) == result
    assert remote['calls'] == before
    assert len(remote['receipts']) == 17


@pytest.mark.asyncio
async def test_site_broker_lost_reply_reconciles_after_expiry_with_get_only(site_publisher, site_review):  # noqa: F811
    publisher, remote, grant, _ = site_publisher
    remote['lose_reply'] = True
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    site_review[-1][0] = grant.expires_at
    remote['calls'].clear()
    result = await publisher.publish_next(grant.id)
    assert result.state == 'SUCCEEDED' and result.effect_verified
    assert all(method == 'GET' for method, _ in remote['calls'])
    assert len(remote['receipts']) == 1
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['disabled', 'lock', 'cancel', 'revocation_at_fence'])
async def test_site_broker_unavailable_or_revoked_approval_never_posts(site_publisher, site_review, monkeypatch, change):  # noqa: F811
    publisher, remote, grant, connection = site_publisher
    if change == 'disabled': publisher.execution_enabled = False
    elif change == 'lock': publisher.lock['verified'] = False
    elif change == 'cancel':
        repo = site_review[0]
        current = repo.get_plan(site_review[2].id, project_id=connection.project_id)
        repo.save_plan(current.model_copy(update={'state': 'CANCELLED'}), current.revision)
    else:
        original = publisher.journal.mark_sent
        def revoke(identity, configured):
            result = original(identity, configured)
            publisher.approvals.revoke(grant.id, project_id=connection.project_id)
            return result
        monkeypatch.setattr(publisher.journal, 'mark_sent', revoke)
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    assert not any(method == 'POST' for method, _ in remote['calls'])
