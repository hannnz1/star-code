"""Main API -> real connector ASGI -> fake external WordPress HTTP boundary."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from muse.commerce_connector.api import create_connector_app
from muse.commerce_connector.wordpress import WordPressConnection
from muse.config import load_settings
from muse.main import create_app


def remote_snapshot():
    return {'pages': [{'id': 1, 'slug': 'home', 'title': 'Home', 'content': 'Original', 'status': 'publish'}],
            'products': [{'id': 2, 'sku': 'CUP', 'name': 'Cup', 'price': '12.50', 'stock_quantity': 5}],
            'settings': {'currency': 'USD', 'language': 'en-US'},
            'theme_identity': {'stylesheet': 'muse-storefront', 'effective_templates': [], 'global_styles': {'styles': {}}}}


def test_invalid_connector_config_does_not_expose_environment_secret(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'
    config.write_text('commerce_connector:\n  service_url: http://127.0.0.1:8787\n  token_env: COMMERCE_TEST_TOKEN\n  versions_lock_path: versions.json\n', encoding='utf-8')
    monkeypatch.setenv('COMMERCE_TEST_TOKEN', 'short-secret')
    with pytest.raises(ValueError) as failure:
        load_settings(config_path=config, data_dir=tmp_path / 'state', require_provider=False)
    assert 'short-secret' not in str(failure.value)


@pytest.fixture
def setup(tmp_path):
    settings = load_settings(data_dir=tmp_path / 'state', require_provider=False)
    app = create_app(settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + settings.access_token.get_secret_value()
        ws = client.get('/api/workspaces').json()[0]['id']
        project = client.post('/api/commerce/projects', json={'workspace_id': ws, 'client_request_id': 'p1',
            'brief': {'brand_name': 'Cups', 'language': 'en-US', 'currency': 'USD'}}).json()
        caps = {'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2', 'theme_id': 'muse-storefront',
                'supported_operations': [], 'missing_requirements': []}
        raw = remote_snapshot()
        def wp(request):
            return httpx.Response(200, json=raw if request.url.path.endswith('/snapshot') else caps)
        connector = create_connector_app({'stage': WordPressConnection('stage', project['id'], 'staging',
            'https://shop.test/base', 'private-username', 'private-password')}, token='service-token-012345', transport=httpx.MockTransport(wp))
        yield client, project, connector, raw, caps


def configure(client, connector, *, verified=True):
    from muse.commerce.platforms.wordpress import WordPressPlatform
    from muse.config import CommerceConnectorSettings
    config = CommerceConnectorSettings(service_url='http://127.0.0.1:8787', token='service-token-012345',
                                        versions_lock_path='unused.json')
    lock = {'wordpress': '7.1.2', 'woocommerce': '11.1.2', 'verified': verified,
            'images': {name: name + '@sha256:' + 'a' * 64 for name in ('wordpress', 'database', 'cli')}}
    client.app.state.commerce_platform = WordPressPlatform(config, lock=lock, transport=httpx.ASGITransport(app=connector))


def bind(client, project, *, key='bind1'):
    return client.post('/api/commerce/projects/' + project['id'] + '/connections', json={
        'connection_id': 'stage', 'expected_revision': project['revision'], 'client_request_id': key})


def refresh(client, project):
    return client.post('/api/commerce/projects/' + project['id'] + '/refresh-context', json={
        'environment': 'staging', 'expected_revision': project['revision']})


def test_binding_is_registry_bound_idempotent_and_secret_free(setup):
    client, project, connector, _, _ = setup
    configure(client, connector)
    response = bind(client, project)
    assert response.status_code == 201
    bound = response.json()
    assert bound['revision'] == 2
    assert bound['environment_refs'] == [{'id': 'stage', 'project_id': project['id'], 'environment': 'staging',
                                         'public_url': 'https://shop.test/base', 'connector_ref': 'stage'}]
    assert bind(client, project).json() == bound
    assert all(secret not in response.text for secret in ('private-username', 'private-password', 'service-token'))
    assert client.get('/api/settings').status_code == 200
    assert 'service-token' not in client.get('/api/settings').text
    assert client.get('/api/tasks').json() == []


def test_cross_project_connection_and_arbitrary_url_are_rejected(setup):
    client, project, connector, _, _ = setup
    configure(client, connector)
    body = {'connection_id': 'stage', 'expected_revision': 1, 'client_request_id': 'bind1', 'base_url': 'https://evil.test'}
    assert client.post('/api/commerce/projects/' + project['id'] + '/connections', json=body).status_code == 422
    other = client.post('/api/commerce/projects', json={'workspace_id': project['workspace_id'], 'client_request_id': 'p2',
        'brief': project['brief']}).json()
    assert bind(client, other).status_code == 404
    assert client.get('/api/commerce/projects/' + other['id']).json()['environment_refs'] == []


def test_unconfigured_and_unverified_platforms_never_persist_binding(setup):
    client, project, connector, _, _ = setup
    response = bind(client, project)
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'VERIFICATION_UNAVAILABLE'
    configure(client, connector, verified=False)
    assert bind(client, project).status_code == 422
    assert client.get('/api/commerce/projects/' + project['id']).json()['revision'] == 1


def test_context_is_durable_sanitized_and_repeated_reads_do_not_create_versions(setup):
    client, project, connector, raw, _ = setup
    configure(client, connector)
    project = bind(client, project).json()
    raw['orders'] = [{'email': 'private@customer.test'}]
    raw['settings']['api_password'] = 'do-not-persist'
    response = refresh(client, project)
    assert response.status_code == 200
    context = response.json()
    assert context['project_revision'] == 3
    assert context['snapshot']['products'][0]['price'] == '12.50'
    assert all(secret not in response.text for secret in ('private@customer.test', 'do-not-persist', 'private-password'))
    route = '/api/commerce/projects/' + project['id']
    project = client.get(route).json()
    again = refresh(client, project)
    assert again.json()['snapshot_id'] == context['snapshot_id']
    assert client.get(route).json()['revision'] == 3
    assert client.get(route + '/context?environment=staging').json() == context
    from muse.commerce.repository import CommerceRepository
    from muse.tasks.repository import TaskRepository
    reopened = CommerceRepository(TaskRepository(client.app.state.settings.data_dir / 'state.sqlite3'))
    assert reopened.get_context(project['id'], 'staging').snapshot_id == context['snapshot_id']


def test_changed_price_invalidates_plan_but_order_does_not(setup):
    client, project, connector, raw, _ = setup
    configure(client, connector)
    project = bind(client, project).json()
    context = refresh(client, project).json()
    route = '/api/commerce/projects/' + project['id']
    project = client.get(route).json()
    plan = client.post(route + '/site-blueprint', json={'expected_revision': project['revision'], 'client_request_id': 'bp'}).json()
    assert plan['snapshot_hash'] == context['snapshot_hash']
    raw['orders'] = [{'id': 100}]
    assert refresh(client, project).json()['snapshot_id'] == context['snapshot_id']
    assert client.get(route + '/plans/' + plan['id']).json()['state'] == 'NEEDS_INPUT'
    raw['products'][0]['price'] = '13.50'
    updated = refresh(client, project)
    assert updated.status_code == 200
    assert updated.json()['snapshot_hash'] != context['snapshot_hash']
    assert client.get(route + '/plans/' + plan['id']).json()['state'] == 'STALE'
    assert refresh(client, project).status_code == 409


def test_failed_refresh_preserves_previous_snapshot(setup):
    client, project, connector, raw, caps = setup
    configure(client, connector)
    project = bind(client, project).json()
    first = refresh(client, project).json()
    route = '/api/commerce/projects/' + project['id']
    project = client.get(route).json()
    raw.clear()
    response = refresh(client, project)
    assert response.status_code == 502
    assert response.json()['error']['code'] == 'READ_TEMPORARY_FAILURE'
    assert client.get(route + '/context?environment=staging').json()['snapshot_id'] == first['snapshot_id']
    assert client.get(route).json()['revision'] == project['revision']
    caps['woocommerce_version'] = 'incompatible'
    assert refresh(client, project).status_code == 422


def test_connector_identity_and_errors_are_sanitized(setup):
    client, project, connector, _, _ = setup
    configure(client, connector)
    from muse.commerce.platforms.wordpress import WordPressPlatform
    platform = client.app.state.commerce_platform
    def bad(request):
        return httpx.Response(503, text='private-password service-token-012345 traceback')
    client.app.state.commerce_platform = WordPressPlatform(platform.config, lock=platform.lock, transport=httpx.MockTransport(bad))
    response = bind(client, project)
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'READ_TEMPORARY_FAILURE'
    assert 'private-password' not in response.text
    assert 'traceback' not in response.text
    def forged(request):
        return httpx.Response(200, json={'id': 'stage', 'project_id': 'wrong', 'environment': 'live',
                                       'public_url': 'https://shop.test', 'connector_ref': 'stage'})
    client.app.state.commerce_platform = WordPressPlatform(platform.config, lock=platform.lock, transport=httpx.MockTransport(forged))
    assert bind(client, project).status_code == 502


def test_connector_config_is_excluded_and_does_not_change_provider(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'
    config.write_text('providers:\n  - name: Original\n    base_url: https://api.openai.com/v1\n    model: original-model\n    api_key: provider-secret\ncommerce_connector:\n  service_url: http://127.0.0.1:8787\n  token_env: TEST_CONNECTOR_TOKEN\n  versions_lock_path: versions.json\n', encoding='utf-8')
    monkeypatch.setenv('TEST_CONNECTOR_TOKEN', 'service-token-012345')
    settings = load_settings(config, data_dir=tmp_path / 'state')
    assert settings.provider.model == 'original-model'
    assert settings.commerce_connector is not None
    assert 'service-token' not in json.dumps(settings.public())
    assert 'commerce_connector' not in settings.public()


def test_rebinding_same_id_to_new_store_invalidates_cached_context(setup):
    client, project, connector, _, _ = setup
    configure(client, connector)
    project = bind(client, project).json()
    assert refresh(client, project).status_code == 200
    route = '/api/commerce/projects/' + project['id']
    project = client.get(route).json()
    # Same admin registry id now refers to a different host: old facts must not be reused.
    from muse.commerce.models import EnvironmentRef
    reference = EnvironmentRef(id='stage', connector_ref='stage', project_id=project['id'],
                               environment='staging', public_url='https://replacement.test')
    client.app.state.commerce.attach_connection(project['id'], reference, 'replace', project['revision'])
    assert client.get(route + '/context?environment=staging').status_code == 404
    plan = client.post(route + '/site-blueprint', json={'expected_revision': project['revision'] + 1, 'client_request_id': 'new-draft'}).json()
    assert plan['snapshot_hash'] is None
