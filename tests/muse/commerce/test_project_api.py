import pytest
from fastapi.testclient import TestClient

from muse.config import load_settings
from muse.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = load_settings(data_dir=tmp_path / 'state', require_provider=False)
    app = create_app(settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as api:
        api.headers['Authorization'] = 'Bearer ' + settings.access_token.get_secret_value()
        yield api


def request(client, key='shop-1'):
    workspace = client.get('/api/workspaces').json()[0]
    return {'workspace_id': workspace['id'], 'client_request_id': key,
            'brief': {'brand_name': 'MUSE Demo', 'language': 'zh-CN', 'currency': 'USD',
                      'audience': 'Handmade gift shoppers', 'style': 'Natural green'}}


def test_project_creation_is_idempotent_and_workspace_bound(client):
    body = request(client)
    first = client.post('/api/commerce/projects', json=body)
    assert first.status_code == 201
    project = first.json()
    again = client.post('/api/commerce/projects', json=body)
    assert again.json()['id'] == project['id']
    assert project['platform'] == 'wordpress'
    assert project['revision'] == 1
    assert client.get('/api/commerce/projects').json() == [project]
    changed = {**body, 'brief': {**body['brief'], 'brand_name': 'Other shop'}}
    assert client.post('/api/commerce/projects', json=changed).status_code == 409
    assert len(client.get('/api/commerce/projects').json()) == 1
    unknown = client.post('/api/commerce/projects', json={**body, 'workspace_id': 'missing', 'client_request_id': 'new'})
    assert unknown.status_code == 404


def test_project_lifecycle_auth_archive_and_delete(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    target = '/api/commerce/projects/' + project['id']
    assert client.post(target+'/archive', json={'expected_revision':1}, headers={'Authorization':'Bearer wrong'}).status_code == 401
    archived = client.post(target+'/archive', json={'expected_revision':1})
    assert archived.status_code == 200
    assert client.get('/api/commerce/projects').json() == []
    assert client.get('/api/commerce/archived-projects').json()[0]['id'] == project['id']
    blocked = client.patch(target, json={'expected_revision':2, 'brief':project['brief']})
    assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'PROJECT_ARCHIVED'
    assert client.post(target+'/restore', json={'expected_revision':1}).status_code == 409
    restored = client.post(target+'/restore', json={'expected_revision':2}).json()
    assert restored['revision'] == 3
    assert client.request('DELETE', target, json={'expected_revision':3,'confirmation_name':'wrong'}).status_code == 422
    assert client.request('DELETE', target, json={'expected_revision':3,'confirmation_name':project['brief']['brand_name']}).status_code == 204
    assert client.get(target).status_code == 404
    assert client.get('/api/commerce/projects').json() == []


def test_project_revision_conflict_preserves_merchant_changes(client):
    created = client.post('/api/commerce/projects', json=request(client)).json()
    target = '/api/commerce/projects/' + created['id']
    update = {'expected_revision': 1, 'brief': {**created['brief'], 'style': 'Warm sand'}}
    success = client.patch(target, json=update)
    assert success.status_code == 200
    assert success.json()['revision'] == 2
    assert client.patch(target, json={**update, 'brief': {**created['brief'], 'style': 'Wrong'}}).status_code == 409
    assert client.get(target).json()['brief']['style'] == 'Warm sand'


def test_invalid_brief_and_auth_do_not_create_projects(client):
    body = request(client)
    for field, value in [('brand_name', '  '), ('currency', 'dollars'), ('currency', 'US1')]:
        invalid = {**body, 'brief': {**body['brief'], field: value}}
        response = client.post('/api/commerce/projects', json=invalid)
        assert response.status_code == 422
    assert client.get('/api/commerce/projects').json() == []
    assert client.post('/api/commerce/projects', json=body, headers={'Authorization': 'Bearer wrong'}).status_code == 401


def test_business_errors_do_not_return_internal_inputs(client):
    body = request(client)
    response = client.post('/api/commerce/projects', json={**body, 'workspace_id': '/private/secret-value'})
    assert response.status_code == 404
    error = response.json()['error']
    assert error['code'] == 'NOT_FOUND'
    assert error['retryable'] is False
    assert error['project_id'] is None
    assert '/private/secret-value' not in response.text


def test_invalid_input_has_public_errors_without_echoing_credentials(client):
    body = request(client)
    body['brief']['currency'] = 'sk-private-example-should-not-echo'
    response = client.post('/api/commerce/projects', json=body)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'INPUT_INVALID'
    assert response.json()['error']['field_errors'][0]['field'] == 'brief.currency'
    assert 'sk-private-example' not in response.text


def test_project_events_resume_without_replaying_previous_changes(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    target = '/api/commerce/projects/' + project['id']
    client.patch(target, json={'expected_revision': 1, 'brief': {**project['brief'], 'style': 'New'}})
    events = client.get(target + '/events?after=1').json()
    assert len(events) == 1
    assert events[0]['sequence'] == 2
    assert events[0]['kind'] == 'brief_updated'


def test_business_error_contract_is_published_in_openapi(client):
    schema = client.get('/openapi.json').json()
    response = schema['paths']['/api/commerce/projects']['post']['responses']['422']
    assert response['content']['application/json']['schema']['$ref'] == '#/components/schemas/CommerceErrorEnvelope'
