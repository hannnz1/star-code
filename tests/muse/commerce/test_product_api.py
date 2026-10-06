from tests.muse.commerce.test_project_api import request

pytest_plugins = ['tests.muse.commerce.test_project_api']

CSV = 'sku,name,price,currency,stock,category,description,image_names\nSKU1,Cup,19.990000,USD,3,Cups,Ceramic cup.,'


def test_product_import_is_durable_idempotent_and_revision_bound(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    path = '/api/commerce/projects/' + project['id']
    body = {'csv_text': CSV, 'expected_revision': 1, 'client_request_id': 'import-one'}
    first = client.post(path + '/product-imports', json=body)
    assert first.status_code == 201
    record = first.json()
    assert record['result']['drafts'][0]['price'] == '19.990000'
    assert record['store_conflicts_checked'] is False
    assert client.post(path + '/product-imports', json=body).json()['id'] == record['id']
    assert len(client.get(path + '/product-imports').json()) == 1
    assert client.post(path + '/product-imports', json={**body, 'csv_text': CSV.replace('19.990000', '9.99')}).status_code == 409
    client.patch(path, json={'expected_revision': 1, 'brief': {**project['brief'], 'currency': 'CNY'}})
    assert client.post(path + '/product-imports', json={**body, 'client_request_id': 'other'}).status_code == 409
    assert client.get('/api/tasks').json() == []


def test_product_import_errors_do_not_create_artifacts_or_tasks(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    path = '/api/commerce/projects/' + project['id'] + '/product-imports'
    response = client.post(path, json={'csv_text': CSV.replace('USD', 'CNY'), 'expected_revision': 1, 'client_request_id': 'invalid'})
    assert response.status_code == 422
    assert response.json()['error']['field_errors'][0]['field'] == 'currency'
    assert client.get(path).json() == []
    assert client.get('/api/tasks').json() == []
