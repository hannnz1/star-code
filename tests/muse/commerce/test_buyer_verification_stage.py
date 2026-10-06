"""Owned source/deployment/buyer integration; all remote CMS calls are simulated."""
# ruff: noqa: F811
import base64
import json

import httpx
import pytest

from muse.commerce.buyer_probe import BuyerProbeRepository
from muse.commerce.buyer_sender import SyntheticBuyer
from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401
from tests.muse.commerce.test_staging_verification_stage import setup as staging_setup


async def setup(inputs, tmp_path, lost=False):
    from muse.commerce.buyer_verification_stage import BuyerVerificationStage
    jobs, job, staging, worker, remote, _intent = await staging_setup(inputs, tmp_path)
    await worker.run_step(job.project_id, job.id)
    source = staging.source
    runner = source.service.runner
    publisher = staging._publisher(jobs.read(job.project_id, job.id))
    runner.lock = publisher.lock
    runner._read_private = lambda *args: {'execution_secret': 'explicit-test-private-probe-secret-0000'}
    product = next(product for product in remote['snapshot']['products'] if product['stock_quantity'] >= 1)
    cart = {'items': [{'id': product['id'], 'sku': product['sku'], 'quantity': 1,
        'prices': {'price': str(int(float(product['price']) * 100)), 'currency_code': 'USD', 'currency_minor_unit': 2}}],
        'shipping_rates': [{'package_id': 0, 'shipping_rates': [{'rate_id': 'flat_rate:1', 'method_id': 'flat_rate'}]}]}
    calls, payloads = [], []

    def transport(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith('/safety'):
            target = source.targets.target(job.project_id, job.plan_id)
            return httpx.Response(200, json={'job_id': target.connector_ref[4:], 'environment': 'staging',
                'wordpress_version': runner.lock['wordpress'], 'woocommerce_version': runner.lock['woocommerce'],
                **dict.fromkeys(['email_disabled', 'external_requests_disabled', 'indexing_disabled',
                    'cron_disabled', 'offline_gateway_only'], True)})
        if request.url.path.endswith('/disposable-product'):
            target = source.targets.target(job.project_id, job.plan_id)
            from tests.muse.commerce.test_buyer_fixture import proof
            return httpx.Response(200, json={**proof(), 'job_id': target.connector_ref[4:], 'project_id': job.project_id,
                'connection_id': target.connector_ref, 'sku': product['sku'], 'product_id': product['id']})
        if request.url.path.endswith('/probe-order'):
            return httpx.Response(200, json={'state': 'found', **payloads[0], 'order_id': 42,
                'status': 'on-hold', 'payment_method': 'cod', 'quantity': 1, 'currency': 'USD',
                'item_subtotal': product['price'], 'shipping_total': '5.00', 'tax_total': '0.00', 'order_total': str(float(product['price']) + 5)})
        assert 'Authorization' not in request.headers
        if request.method == 'GET':
            return httpx.Response(200, json={'items': []}, headers={'Cart-Token': 'explicit-fixture-cart-token-0000'})
        if request.url.path.endswith('/checkout'):
            payloads.append(json.loads(base64.b64decode(request.headers['X-Muse-Probe'])))
            if lost: raise httpx.ReadTimeout('explicit lost checkout reply', request=request)
            return httpx.Response(201, json={'order_id': 42, 'status': 'on-hold'})
        return httpx.Response(201 if request.url.path.endswith('/add-item') else 200, json=cart)

    sender = SyntheticBuyer(BuyerProbeRepository(jobs.repo), source.service.jobs, runner, source.sources,
        transport=httpx.MockTransport(transport))
    stage = BuyerVerificationStage(jobs, source, sender)
    worker.handlers['buyer'] = stage
    return jobs, job, stage, worker, calls


@pytest.mark.asyncio
async def test_buyer_stage_binds_real_sender_readback_to_verification_job(staging_source_inputs, tmp_path):
    jobs, job, stage, worker, calls = await setup(staging_source_inputs, tmp_path)
    saved = await worker.run_step(job.project_id, job.id)
    assert [item.phase for item in saved.completed] == ['reference', 'source_capture', 'staging', 'buyer']
    assert len([path for method, path in calls if method == 'POST' and path.endswith('/checkout')]) == 1
    assert stage.sender.probes.db.rows("SELECT id FROM commerce_artifacts WHERE kind='buyer_order_readback'")
    assert jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'") == []


@pytest.mark.asyncio
async def test_buyer_stage_lost_checkout_reply_recovers_without_second_order(staging_source_inputs, tmp_path):
    _jobs, job, stage, worker, calls = await setup(staging_source_inputs, tmp_path, lost=True)
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    before = len(calls)
    saved = await stage.reconcile(job.project_id, job.id)
    assert len(saved.completed) == 4
    assert all(method == 'GET' for method, _path in calls[before:])
    assert len([path for method, path in calls if method == 'POST' and path.endswith('/checkout')]) == 1


@pytest.mark.asyncio
async def test_buyer_stage_missing_probe_cannot_recover_by_sending(staging_source_inputs, tmp_path):
    jobs, job, stage, worker, calls = await setup(staging_source_inputs, tmp_path)
    async def missing(claim): raise TimeoutError('stopped before buyer')
    worker.handlers['buyer'] = missing
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    with pytest.raises(CommerceFailure): await stage.reconcile(job.project_id, job.id)
    assert calls == [] and jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'
