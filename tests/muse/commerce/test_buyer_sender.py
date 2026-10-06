import base64
import hashlib
import hmac
import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from muse.commerce.buyer_probe import BuyerProbeRepository
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ProductDraft
from muse.commerce.repository import digest
from muse.commerce.staging_source import StagingSourceRepository
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_reference_runner import inputs


def setup(workflow, tmp_path, monkeypatch, *, attack=None):
    from muse.commerce.buyer_sender import SyntheticBuyer
    jobs, job, _, lock = inputs(workflow, tmp_path)
    started = jobs.begin(job.id, expected_revision=job.revision)
    safety = {'job_id': job.id, 'environment': 'staging', 'wordpress_version': lock['wordpress'],
        'woocommerce_version': lock['woocommerce'], **{name: True for name in ('email_disabled', 'external_requests_disabled',
            'indexing_disabled', 'cron_disabled', 'offline_gateway_only')}}
    job = jobs.ready(job.id, started.revision, {'job_id': job.id, 'asset_digest': job.asset_digest,
        'containers': {role: str(index) * 64 for index, role in enumerate(('database', 'wordpress', 'cli'), 1)},
        'volumes': [job.resource_names['database_volume'], job.resource_names['site_volume']],
        'network': job.resource_names['network'], 'safety': safety})
    probes = BuyerProbeRepository(jobs.repo)
    plan = workflow[2]
    connection = WordPressConnection('ref-' + job.id, job.project_id, 'staging', 'http://127.0.0.1:63660',
        'unit-service', 'unit-private-password', approved_development_http=True)
    runner = SimpleNamespace(lock=lock, _connection=lambda value: connection,
        _read_private=lambda *args: {'execution_secret': 'unit-private-probe-signing-secret-0000'})
    sources = StagingSourceRepository(jobs.repo, clock=lambda: 1000.)
    intent = SimpleNamespace(project_id=job.project_id, plan_id=plan.id, source_digest='b' * 64, digest='c' * 64,
        target=SimpleNamespace(connector_ref=connection.connection_id),
        products=[ProductDraft(sku='CUP', title='Cup', price=Decimal('12.50'), currency='USD', stock=3)])
    authorizations = []
    def source(conn, grant, value, *, fresh=False):
        authorizations.append(fresh)
        if attack == 'stale' and len(authorizations) == 2: raise CommerceFailure('REVIEW_STALE')
        return intent, [SimpleNamespace(snapshot=SimpleNamespace(products=[{'id': 12, 'sku': 'CUP'}]))]
    # Explicit fake completed deployment; these tests measure HTTP/fences only.
    monkeypatch.setattr(sources, '_verification_source', source)
    calls, payloads = [], []
    cart = {'items': [{'id': 12, 'sku': 'CUP', 'quantity': 1, 'prices': {'price': '1250',
        'currency_code': 'USD', 'currency_minor_unit': 2}}],
        'shipping_rates': [{'package_id': 0, 'shipping_rates': [{'rate_id': 'flat_rate:1', 'method_id': 'flat_rate'}]}]}
    if attack == 'price': cart['items'][0]['prices']['price'] = '1200'
    if attack == 'sku': cart['items'][0]['sku'] = 'OTHER'
    if attack == 'quantity': cart['items'][0]['quantity'] = True
    if attack == 'shipping': cart['shipping_rates'] = [None]
    if attack == 'unsafe': safety['offline_gateway_only'] = False
    def remote(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith('/safety'):
            assert request.headers.get('Authorization', '').startswith('Basic ')
            return httpx.Response(200, json=safety)
        if path.endswith('/probe-order'):
            proof = {'state': 'found', **payloads[0], 'order_id': 25, 'status': 'on-hold', 'payment_method': 'cod', 'quantity': 1, 'currency': 'USD', 'item_subtotal': '12.50',
                'shipping_total': '5.00', 'tax_total': '0.00', 'order_total': '17.50'}
            if attack == 'readback': proof['source_digest'] = 'd' * 64
            return httpx.Response(200, json=proof)
        assert 'Authorization' not in request.headers
        if request.method == 'GET' and path.endswith('/cart'):
            return httpx.Response(200, json={'items': []}, headers={'Cart-Token': 'unit-cart-token-0123456789'})
        assert request.headers['Cart-Token'] == 'unit-cart-token-0123456789'
        if path.endswith('/checkout'):
            payload = request.headers['X-Muse-Probe']
            signature = hmac.new(b'unit-private-probe-signing-secret-0000', payload.encode(), hashlib.sha256).hexdigest()
            assert request.headers['X-Muse-Probe-Signature'] == signature
            payloads.append(json.loads(base64.b64decode(payload)))
            identity = digest([job.project_id, plan.id, 'buyer_probe', job.id])
            assert probes.read(job.project_id, plan.id, identity).state == 'UNKNOWN'
            assert json.loads(request.content)['payment_method'] == 'cod'
            if attack == 'lost': raise httpx.ReadTimeout('simulated lost checkout reply')
            return httpx.Response(201 if attack == 'created' else 200, json={'order_id': 25, 'status': 'on-hold', 'order_key': 'unit-private-order-key',
                'billing_address': {'email': 'private-synthetic@example.invalid'}, 'payment_result': {'payment_status': 'success'}})
        if attack == 'redirect': return httpx.Response(302, headers={'Location': 'https://evil.invalid'})
        return httpx.Response(201 if attack == 'created' and path.endswith('/add-item') else 200, json=cart)
    sender = SyntheticBuyer(probes, jobs, runner, sources, transport=httpx.MockTransport(remote))
    return sender, probes, plan, job, calls, payloads


@pytest.mark.parametrize('status', [None, 'created'])
async def test_store_api_buyer_checks_cart_sends_once_and_independently_reads_order(workflow, tmp_path, monkeypatch, status):
    sender, probes, plan, job, calls, _ = setup(workflow, tmp_path, monkeypatch, attack=status)
    saved = await sender.send(job.project_id, plan.id, job.id, 'unit-grant', 'CUP')
    assert saved.receipt.order_id == 25 and saved.source.product_id == 12
    assert len([call for call in calls if call[1].endswith('/checkout')]) == 1
    assert calls[-1] == ('GET', '/wp-json/muse-staging/v1/probe-order')
    current = probes.read(job.project_id, plan.id, saved.probe_id)
    assert current.buyer_flow_verified is False
    assert 'order_key' not in saved.model_dump_json() and 'email' not in saved.model_dump_json()
    before = len(calls)
    with pytest.raises(CommerceFailure): await sender.send(job.project_id, plan.id, job.id, 'unit-grant', 'CUP')
    assert len(calls) == before


@pytest.mark.parametrize('attack', ['price', 'sku', 'quantity', 'unsafe', 'redirect', 'stale', 'shipping'])
async def test_bad_cart_safety_or_source_never_sends_checkout(workflow, tmp_path, monkeypatch, attack):
    sender, _, plan, job, calls, payloads = setup(workflow, tmp_path, monkeypatch, attack=attack)
    with pytest.raises(CommerceFailure): await sender.send(job.project_id, plan.id, job.id, 'unit-grant', 'CUP')
    assert payloads == [] and not any(path.endswith('/checkout') for _, path in calls)


async def test_lost_checkout_reply_is_fenced_and_explicit_reconcile_only_reads(workflow, tmp_path, monkeypatch):
    sender, probes, plan, job, calls, _ = setup(workflow, tmp_path, monkeypatch, attack='lost')
    with pytest.raises(CommerceFailure): await sender.send(job.project_id, plan.id, job.id, 'unit-grant', 'CUP')
    identity = digest([job.project_id, plan.id, 'buyer_probe', job.id])
    assert probes.read(job.project_id, plan.id, identity).state == 'UNKNOWN'
    before = len(calls)
    with pytest.raises(CommerceFailure): await sender.send(job.project_id, plan.id, job.id, 'unit-grant', 'CUP')
    assert len(calls) == before
    saved = await sender.reconcile(job.project_id, plan.id, identity)
    assert saved.receipt.order_id == 25
    assert all(method == 'GET' for method, _ in calls[before:])


async def test_mismatched_independent_readback_does_not_persist_verification(workflow, tmp_path, monkeypatch):
    sender, probes, plan, job, _, _ = setup(workflow, tmp_path, monkeypatch, attack='readback')
    with pytest.raises(CommerceFailure): await sender.send(job.project_id, plan.id, job.id, 'unit-grant', 'CUP')
    assert probes.db.rows("SELECT id FROM commerce_artifacts WHERE kind='buyer_order_readback'") == []


async def test_disposable_product_reader_is_authenticated_get_only(workflow, tmp_path, monkeypatch):
    sender, _probes, plan, job, _calls, _payloads = setup(workflow, tmp_path, monkeypatch)
    from tests.muse.commerce.test_buyer_fixture import proof
    calls = []
    def remote(request):
        calls.append(request)
        assert request.method == 'GET' and request.headers.get('authorization', '').startswith('Basic ')
        if request.url.path.endswith('/safety'):
            return httpx.Response(200, json={'job_id': job.id, 'environment': 'staging',
                'wordpress_version': sender.runner.lock['wordpress'], 'woocommerce_version': sender.runner.lock['woocommerce'],
                **{key: True for key in ('email_disabled', 'external_requests_disabled', 'indexing_disabled',
                                       'cron_disabled', 'offline_gateway_only')}})
        return httpx.Response(200, json={**proof(), 'job_id': job.id, 'project_id': plan.project_id,
            'connection_id': 'ref-' + job.id, 'sku': 'MUSE-PROBE-' + job.id})
    sender.transport = httpx.MockTransport(remote)
    value = await sender.disposable_product(plan.project_id, job.id, currency='USD')
    assert value.job_id == job.id and len(calls) == 2
    assert not sender.probes.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='buyer_probe'")
