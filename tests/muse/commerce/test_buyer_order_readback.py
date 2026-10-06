import pytest

from muse.commerce.buyer_probe import BuyerProbeRepository
from muse.commerce.errors import CommerceFailure


def probe(workflow):
    repo, _, plan, _ = workflow
    probes = BuyerProbeRepository(repo.repo)
    source = {'job_id': 'a' * 32, 'source_digest': 'b' * 64, 'staging_intent_digest': 'c' * 64,
        'product_id': 12, 'sku': 'CUP', 'connection_id': 'ref-' + 'a' * 32}
    record = probes.begin(plan.project_id, plan.id, source)
    proof = {'state': 'found', 'probe_id': record.id, 'job_id': source['job_id'], 'source_digest': source['source_digest'],
        'staging_intent_digest': source['staging_intent_digest'], 'product_id': 12, 'sku': 'CUP',
        'order_id': 25, 'status': 'on-hold', 'payment_method': 'cod', 'quantity': 1}
    return probes, record, proof


def test_independent_order_readback_can_account_unknown_without_verifying_browser(workflow):
    probes, record, proof = probe(workflow)
    saved = probes.confirm_readback(record.id, proof)
    assert saved.receipt.order_id == 25 and saved.source == record.source
    assert probes.confirm_readback(record.id, proof) == saved
    current = probes.read(record.project_id, record.plan_id, record.id)
    assert current.state == 'SUCCEEDED' and current.buyer_flow_verified is False
    assert 'email' not in saved.model_dump_json() and 'cookie' not in saved.model_dump_json()
    assert probes.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'") == []
    with pytest.raises(CommerceFailure): probes.begin(record.project_id, record.plan_id, record.source)


@pytest.mark.parametrize('changes', [
    {'job_id': 'd' * 32}, {'source_digest': 'd' * 64}, {'staging_intent_digest': 'd' * 64},
    {'product_id': True}, {'product_id': 13}, {'sku': 'OTHER'}, {'probe_id': 'd' * 64},
    {'quantity': 1.5}, {'quantity': 2}, {'status': 'processing'}, {'payment_method': 'stripe'},
    {'email': 'customer@example.com'}, {'state': 'absent'},
])
def test_readback_rejects_wrong_source_shape_or_pii_without_saving(workflow, changes):
    probes, record, proof = probe(workflow)
    with pytest.raises(CommerceFailure): probes.confirm_readback(record.id, {**proof, **changes})
    assert probes.read(record.project_id, record.plan_id, record.id).state == 'UNKNOWN'
    assert probes.db.rows("SELECT id FROM commerce_artifacts WHERE kind='buyer_order_readback'") == []


def test_independent_receipt_must_match_previous_checkout_receipt(workflow):
    probes, record, proof = probe(workflow)
    probes.complete(record.id, {'order_id': 26, 'status': 'on-hold'})
    with pytest.raises(CommerceFailure): probes.confirm_readback(record.id, proof)


def test_production_readback_requires_the_frozen_price_artifact(workflow):
    probes, record, proof = probe(workflow)
    proof.update(currency='USD', item_subtotal='12.50', shipping_total='5.00', tax_total='0.00', order_total='17.50')
    with pytest.raises(CommerceFailure): probes.confirm_readback(record.id, proof, require_amounts=True)
    assert probes.db.rows("SELECT id FROM commerce_artifacts WHERE kind='buyer_order_readback'") == []


@pytest.mark.parametrize('changes', [{}, {'item_subtotal': '13.00'}, {'currency': 'EUR'},
    {'shipping_total': '6.00'}, {'tax_total': '1.00'}, {'order_total': '18.00'}])
def test_production_price_fence_checks_actual_order_amounts(workflow, changes):
    from muse.commerce.buyer_probe import BuyerSource
    from muse.commerce.models import ProductDraft
    service, _, plan, _ = workflow
    probes = BuyerProbeRepository(service.repo)
    source = BuyerSource(job_id='a' * 32, source_digest='b' * 64, staging_intent_digest='c' * 64,
        product_id=12, sku='CUP', connection_id='ref-' + 'a' * 32)
    draft = ProductDraft(sku='CUP', title='Cup', price='12.50', currency='USD', stock=3)
    record = probes.begin(plan.project_id, plan.id, source, expected_product=draft)
    proof = {'state': 'found', 'probe_id': record.id, 'job_id': source.job_id, 'source_digest': source.source_digest,
        'staging_intent_digest': source.staging_intent_digest, 'product_id': 12, 'sku': 'CUP', 'order_id': 25,
        'status': 'on-hold', 'payment_method': 'cod', 'quantity': 1, 'currency': 'USD',
        'item_subtotal': '12.50', 'shipping_total': '5.00', 'tax_total': '0.00', 'order_total': '17.50'}
    if changes:
        with pytest.raises(CommerceFailure): probes.confirm_readback(record.id, {**proof, **changes})
        assert probes.read(record.project_id, record.plan_id, record.id).state == 'UNKNOWN'
    else:
        saved = probes.confirm_readback(record.id, proof)
        assert saved.order_facts.item_subtotal == draft.price
