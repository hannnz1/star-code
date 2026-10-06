import httpx

from muse.commerce_connector.api import create_connector_app
from tests.muse.commerce.test_reference_runner import inputs
from tests.muse.commerce.test_reference_service import Runner


async def test_reference_api_requires_auth_and_strict_fixed_actions(workflow, tmp_path):
    from muse.commerce_connector.reference_service import ReferenceEnvironmentService
    jobs, job, bundle, _ = inputs(workflow, tmp_path)
    runner = Runner(jobs, job)
    service = ReferenceEnvironmentService(jobs, runner, bundle, ports=(63660, 63661))
    app = create_connector_app({}, token='unit-reference-token', reference=service)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        url = '/v1/reference-jobs/' + job.id
        assert (await client.get(url, params={'project_id': job.project_id})).status_code == 401
        headers = {'Authorization': 'Bearer unit-reference-token'}
        response = await client.get(url, params={'project_id': job.project_id}, headers=headers)
        assert response.status_code == 200 and response.json()['state'] == 'RESERVED'
        body = {'project_id': job.project_id, 'expected_revision': job.revision, 'action': 'shell'}
        assert (await client.post(url, json=body, headers=headers)).status_code == 422
        body['action'] = 'provision'
        body['url'] = 'https://merchant.example'
        assert (await client.post(url, json=body, headers=headers)).status_code == 422
        assert runner.calls == []
        assert (await client.get('/v1/connections/ref-' + job.id,
            params={'project_id': job.project_id}, headers=headers)).status_code == 404
        reserve = {'project_id': job.project_id, 'expected_revision': job.project_revision, 'client_request_id': 'api'}
        response = await client.post('/v1/reference-jobs', json=reserve, headers=headers)
        assert response.status_code == 200 and response.json()['port'] == 63661
        assert 'password' not in response.text and 'execution_secret' not in response.text
        assert (await client.post('/v1/reference-jobs', json={**reserve, 'port': 80}, headers=headers)).status_code == 422


async def test_reference_api_disabled_by_default():
    app = create_connector_app({}, token='unit-reference-token')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/reference-jobs', headers={'Authorization': 'Bearer unit-reference-token'},
            json={'project_id': 'project', 'expected_revision': 1, 'client_request_id': 'request'})
        assert response.status_code == 503
