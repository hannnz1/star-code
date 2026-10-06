from tests.muse.commerce.test_shipping_draft_api import setup

pytest_plugins = ['tests.muse.commerce.test_project_api']


def test_category_navigation_uses_exact_project_product_batch(client):
    path, plan, _ = setup(client)
    batch = client.post(path+'/product-imports', json={'expected_revision': 1, 'client_request_id': 'categories',
        'csv_text': 'sku,name,price,currency,stock,category,description,image_names\nDOG1,Toy,10,USD,2,Dog toys,Good,\nCAT1,Bowl,15,USD,3,Cat bowls,Good,'}).json()
    body = {'expected_revision': 1, 'expected_plan_revision': plan['revision'], 'plan_id': plan['id'],
            'client_request_id': 'category-nav', 'navigation': {'import_id': batch['id'],
            'items': [{'category': 'Dog toys', 'label': 'For dogs'}, {'category': 'Cat bowls', 'label': 'For cats'}]}}
    saved = client.patch(path+'/category-navigation', json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['blueprint']['required_settings']['category_navigation'] == body['navigation']
    assert client.patch(path+'/category-navigation', json=body).json() == saved.json()
    assert client.patch(path+'/category-navigation', json={**body, 'client_request_id': 'stale'}).status_code == 409
    body.update(expected_plan_revision=saved.json()['revision'], client_request_id='wrong-name')
    for value in [{'import_id': batch['id'], 'items': [{'category': 'Missing', 'label': 'Missing'}]},
                  {'import_id': 'foreign', 'items': []},
                  {'import_id': batch['id'], 'items': [{'category': 'Dog toys', 'label': '<script>'}]}]:
        assert client.patch(path+'/category-navigation', json={**body, 'navigation': value}).status_code in (409, 422)
    assert client.get('/api/tasks').json() == []


def test_repeated_categories_are_rejected():
    import pytest
    from pydantic import ValidationError
    from muse.commerce.category_navigation import CategoryNavigation
    with pytest.raises(ValidationError):
        CategoryNavigation(import_id='batch', items=[{'category': 'Dog toys', 'label': 'One'}, {'category': 'Dog toys', 'label': 'Two'}])
