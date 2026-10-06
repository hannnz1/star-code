from decimal import Decimal
from types import SimpleNamespace
import pytest
from muse.commerce.buyer_sender import SyntheticBuyer
from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_store_configuration_facts import state


@pytest.mark.parametrize('price,kind,amount', [('49.99','flat_rate','6.00'),('50.00','free_shipping','0.00'),('50.01','free_shipping','0.00')])
def test_buyer_uses_frozen_rules_and_actual_owned_method(price,kind,amount):
    actual=state()
    intent=SimpleNamespace(project_id='project',blueprint=SimpleNamespace(required_settings={'shipping_rules':actual['rules']}))
    product=SimpleNamespace(price=Decimal(price))
    expectation,address = SyntheticBuyer._delivery(intent,SimpleNamespace(settings={'shipping_configuration':actual}),product)
    assert expectation['amount']==Decimal(amount)
    assert expectation['method_id']==kind
    assert expectation['rate_id']==kind+(':'+str(1 if kind=='flat_rate' else 2))
    assert address['country']=='AU' and address['postcode']=='2000'


def test_buyer_rejects_shipping_readback_not_matching_rules():
    actual=state(); actual['zones'][0]['methods'][0]['settings']['cost']='99.00'
    intent=SimpleNamespace(project_id='project',blueprint=SimpleNamespace(required_settings={'shipping_rules':actual['rules']}))
    with pytest.raises(CommerceFailure):
        SyntheticBuyer._delivery(intent,SimpleNamespace(settings={'shipping_configuration':actual}),SimpleNamespace(price=Decimal('20')))


@pytest.mark.parametrize('amount',['0.00','6.00'])
def test_order_readback_uses_persisted_expected_shipping(workflow,amount):
    from muse.commerce.buyer_probe import BuyerProbeRepository
    from muse.commerce.models import ProductDraft
    service,_,plan,_=workflow; probes=BuyerProbeRepository(service.repo)
    source={'job_id':'a'*32,'source_digest':'b'*64,'staging_intent_digest':'c'*64,'product_id':12,'sku':'CUP','connection_id':'stage'}
    product=ProductDraft(sku='CUP',title='Cup',price='12.50',currency='USD',stock=3)
    probe=probes.begin(plan.project_id,plan.id,source,expected_product=product,expected_shipping=Decimal(amount))
    proof={'state':'found',**{k:v for k,v in source.items() if k!='connection_id'},'probe_id':probe.id,
        'order_id':25,'status':'on-hold','payment_method':'cod','quantity':1,'currency':'USD',
        'item_subtotal':'12.50','shipping_total':amount,'tax_total':'0.00','order_total':str(Decimal('12.50')+Decimal(amount))}
    wrong={**proof,'shipping_total':'5.00','order_total':'17.50'}
    with pytest.raises(CommerceFailure): probes.confirm_readback(probe.id,wrong,require_amounts=True)
    assert probes.confirm_readback(probe.id,proof,require_amounts=True).order_facts.shipping_total==Decimal(amount)
