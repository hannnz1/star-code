from tests.muse.commerce.test_project_api import request
pytest_plugins=['tests.muse.commerce.test_project_api']


def test_configured_is_not_verified(client):
    project=client.post('/api/commerce/projects',json=request(client)).json()
    path='/api/commerce/projects/'+project['id']
    report=client.get(path+'/readiness')
    assert report.status_code==200
    items={i['key']:i for i in report.json()['items']}
    assert items['payment']['verification_status']=='NOT_VERIFIED'
    assert items['policy']['configuration_status']=='MISSING'
    assert report.json()['can_publish'] is False


def test_shipping_quote_boundary():
    from muse.commerce.store_readiness import ShippingQuote,quote_shipping
    from decimal import Decimal
    settings=ShippingQuote(country='AU',rate=Decimal('6.00'),free_from=Decimal('50.00'),subtotal=Decimal('49.99'))
    assert quote_shipping(settings)==Decimal('6.00')
    assert quote_shipping(settings.model_copy(update={'subtotal':Decimal('50.00')}))==Decimal('0.00')


def test_shipping_and_payment_have_separate_configuration_and_acknowledgement(workflow):
    from muse.commerce.repository import CommerceRepository
    from muse.commerce.store_readiness import StoreReadinessService
    _, runtime, plan, _ = workflow
    report = StoreReadinessService(CommerceRepository(runtime)).evaluate(plan.project_id)
    items = {item.key: item for item in report.items}
    for key, tab in [('shipping', 'shipping'), ('payment', 'checkout')]:
        item = items[key]
        assert item.configuration_url == f'https://shop.test/wp-admin/admin.php?page=wc-settings&tab={tab}'
        assert item.confirmation_url == 'https://shop.test/wp-admin/options-general.php?page=muse-connector'
        assert item.verification_status == 'NOT_VERIFIED'
    assert items['tax'].confirmation_url is None
    assert report.can_publish is False
