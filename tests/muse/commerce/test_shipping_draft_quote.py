from tests.muse.commerce.test_shipping_draft_api import setup

pytest_plugins = ['tests.muse.commerce.test_project_api']


def test_saved_rules_quote_requires_current_source(client):
    path, plan, body = setup(client)
    saved = client.patch(path+'/shipping-rules', json=body).json()
    query = {'plan_id': plan['id'], 'expected_plan_revision': saved['revision'], 'country': 'AU', 'subtotal': '49.99'}
    assert client.post(path+'/shipping-rules/quote', json=query).json() == {'served': True, 'amount': '6.00', 'currency': 'USD'}
    assert client.post(path+'/shipping-rules/quote', json={**query, 'subtotal': '50.00'}).json()['amount'] == '0.00'
    assert client.post(path+'/shipping-rules/quote', json={**query, 'country': 'US'}).json()['served'] is False
    assert client.post(path+'/shipping-rules/quote', json={**query, 'expected_plan_revision': 1}).status_code == 409
    for value in ['NaN', 'Infinity', '-1.00', '1.001']:
        assert client.post(path+'/shipping-rules/quote', json={**query, 'subtotal': value}).status_code == 422
