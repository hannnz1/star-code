import pytest

from muse.commerce.errors import CommerceFailure


def test_checkout_send_fence_survives_restart_and_never_permits_second_order(workflow):
    from muse.commerce.buyer_probe import BuyerProbeRepository
    service, _, plan, _ = workflow
    probes = BuyerProbeRepository(service.repo)
    source = {'job_id': 'a' * 32, 'source_digest': 'b' * 64, 'staging_intent_digest': 'c' * 64,
              'product_id': 12, 'sku': 'CUP', 'connection_id': 'stage'}
    first = probes.begin(plan.project_id, plan.id, source)
    assert first.state == 'UNKNOWN'
    restarted = BuyerProbeRepository(service.repo)
    with pytest.raises(CommerceFailure): restarted.begin(plan.project_id, plan.id, source)
    assert restarted.read(plan.project_id, plan.id, first.id).state == 'UNKNOWN'
    assert 'email' not in first.model_dump_json() and 'cookie' not in first.model_dump_json()
    with pytest.raises(CommerceFailure): restarted.complete(first.id, {'order_id': True, 'status': 'on-hold'})
    completed = restarted.complete(first.id, {'order_id': 25, 'status': 'on-hold'})
    assert completed.state == 'SUCCEEDED'
    assert restarted.complete(first.id, {'order_id': 25, 'status': 'on-hold'}) == completed
    with pytest.raises(CommerceFailure): restarted.complete(first.id, {'order_id': 26, 'status': 'on-hold'})
    with pytest.raises(CommerceFailure): restarted.begin(plan.project_id, plan.id, source)


def test_buyer_journal_cannot_store_pii_live_target_or_mark_response_as_readback(workflow):
    from muse.commerce.buyer_probe import BuyerProbeRepository
    service, _, plan, _ = workflow
    probes = BuyerProbeRepository(service.repo)
    source = {'job_id': 'a' * 32, 'source_digest': 'b' * 64, 'staging_intent_digest': 'c' * 64,
              'product_id': 12, 'sku': 'CUP', 'connection_id': 'stage'}
    for extras in [{'email': 'customer@example.com'}, {'environment': 'live'}, {'product_id': True}]:
        with pytest.raises(CommerceFailure): probes.begin(plan.project_id, plan.id, {**source, **extras})
    record = probes.begin(plan.project_id, plan.id, source)
    for payload in [{'passed': True}, {'order_id': 25, 'status': 'on-hold', 'email': 'customer@example.com'},
                    {'order_id': 25, 'status': 'processing'}, {'order_id': 0, 'status': 'on-hold'}]:
        with pytest.raises(CommerceFailure): probes.complete(record.id, payload)
    assert probes.read(plan.project_id, plan.id, record.id).state == 'UNKNOWN'
    with pytest.raises(CommerceFailure): probes.read('other', plan.id, record.id)
