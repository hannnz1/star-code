import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.api import create_connector_app
from muse.commerce_connector.wordpress import WordPressConnection, WordPressReader


def connection(**updates):
    return WordPressConnection(connection_id='test-store', project_id='p1', environment='staging',
                               base_url='https://store.example', username='service-user',
                               application_password='secret-for-test', **updates)


@pytest.mark.parametrize('url,environment,approved', [
    ('http://store.example', 'live', False), ('http://192.168.1.8', 'staging', True),
    ('https://user:secret@store.example', 'live', False), ('https://store.example?url=other', 'live', False),
    ('https://store.example/#x', 'live', False), ('http://127.0.0.1', 'live', True),
])
def test_target_rejects_unsafe_configuration(url, environment, approved):
    with pytest.raises(ValueError):
        WordPressConnection(connection_id='c', project_id='p', environment=environment, base_url=url,
                            username='u', application_password='s', approved_development_http=approved)


def test_only_explicit_loopback_staging_allows_http():
    item = WordPressConnection(connection_id='c', project_id='p', environment='staging',
                               base_url='http://127.0.0.1:8081', username='u', application_password='s',
                               approved_development_http=True)
    assert item.base_url == 'http://127.0.0.1:8081'
    assert 'secret-for-test' not in repr(connection())


@pytest.mark.asyncio
async def test_redirect_never_sends_credentials_to_another_target():
    targets = []
    def respond(request):
        targets.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'https://other.example/steal'})
    reader = WordPressReader(connection(), transport=httpx.MockTransport(respond))
    with pytest.raises(CommerceFailure) as error:
        await reader.read('snapshot', remaining_seconds=10)
    assert error.value.public.code == 'PERMISSION_DENIED'
    assert len(targets) == 1


@pytest.mark.asyncio
async def test_only_reads_retry_twice_and_obey_time_budget():
    count, waits = 0, []
    def respond(request):
        nonlocal count
        count += 1
        return httpx.Response(503)
    async def sleep(seconds):
        waits.append(seconds)
    reader = WordPressReader(connection(), transport=httpx.MockTransport(respond), sleep=sleep)
    with pytest.raises(CommerceFailure) as error:
        await reader.read('snapshot', remaining_seconds=20)
    assert error.value.public.code == 'READ_TEMPORARY_FAILURE'
    assert count == 3 and waits == [1, 2]
    count = 0
    with pytest.raises(CommerceFailure):
        await reader.read('snapshot', remaining_seconds=.1)
    assert count == 1
    with pytest.raises(CommerceFailure):
        await reader.read('operations', remaining_seconds=20)
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('retry_after', ['61', '9999999999'])
async def test_long_retry_after_requires_explicit_resume(retry_after):
    calls = []
    async def forbidden_sleep(seconds):
        pytest.fail('must not automatically wait beyond 60 seconds')
    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After': retry_after})
    reader = WordPressReader(connection(), transport=httpx.MockTransport(respond), sleep=forbidden_sleep)
    with pytest.raises(CommerceFailure):
        await reader.read('snapshot', remaining_seconds=100)
    assert len(calls) == 1


def test_connector_auth_and_project_binding_exclude_credentials():
    def respond(request):
        return httpx.Response(200, json={'pages': [], 'products': [], 'settings': {'currency': 'USD', 'language': 'en-US'},
            'theme_identity': {'stylesheet': 'muse-storefront', 'effective_templates': [], 'global_styles': {'styles': {}, 'settings': {}}}})
    app = create_connector_app({'test-store': connection()}, token='connector-secret',
                               transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        route = '/v1/connections/test-store/snapshot?project_id=p1'
        assert client.get(route).status_code == 401
        headers = {'Authorization': 'Bearer connector-secret'}
        assert client.get(route.replace('p1', 'p2'), headers=headers).status_code == 404
        response = client.get(route, headers=headers)
        assert response.status_code == 200
        assert 'secret-for-test' not in response.text
        assert 'service-user' not in response.text
        assert client.post('/v1/connections/test-store/operations', headers=headers, json={}).status_code == 404
        assert client.get('/openapi.json').status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(401, 'AUTH_REQUIRED'), (403, 'PERMISSION_DENIED')])
async def test_remote_failures_are_sanitized(status, code):
    reader = WordPressReader(connection(), transport=httpx.MockTransport(
        lambda request: httpx.Response(status, text='secret-for-test /private/credentials')))
    with pytest.raises(CommerceFailure) as error:
        await reader.read('snapshot', remaining_seconds=10)
    assert error.value.public.code == code
    assert 'secret-for-test' not in json.dumps(error.value.public.model_dump())


@pytest.mark.asyncio
async def test_read_deadline_covers_request_and_wait():
    async def slow(request):
        await asyncio.sleep(.1)
        return httpx.Response(200, json={})
    reader = WordPressReader(connection(), transport=httpx.MockTransport(slow))
    with pytest.raises(CommerceFailure):
        await reader.read('snapshot', remaining_seconds=.01)
