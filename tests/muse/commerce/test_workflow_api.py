from fastapi.testclient import TestClient

from muse.commerce.models import SiteBrief
from muse.main import create_app


def test_workflow_api_queues_once_and_enforces_scope_and_revision(workflow):
    service, repo, plan, worker = workflow
    app = create_app(worker.settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        project = service.repo.get_project(plan.project_id)
        path = '/api/commerce/projects/' + project.id
        body = {'kind': 'build_site', 'prompt': 'Prepare another shop plan', 'client_request_id': 'api-team',
                'expected_revision': project.revision, 'max_requests': 8}
        response = client.post(path + '/workflows', json=body)
        assert response.status_code == 201
        created = response.json()
        assert created['state'] == 'PLANNING'
        assert created['steps'][0]['task_id']
        assert client.post(path + '/workflows', json=body).json() == created
        assert len(repo.list()) == 2
        assert sum(task.checkpoint.get('model_requests', 0) for task in repo.list()) == 0
        prefix = path + '/plans/' + created['id']
        assert client.post(prefix + '/advance', json={'expected_revision': 99}).status_code == 409
        assert client.post(prefix + '/advance', json={'expected_revision': created['revision']}).json() == created
        assert client.post(prefix + '/resume', json={'expected_revision': created['revision']}).status_code == 409
        assert client.get(prefix + '/outputs').json() == []
        other = service.repo.create_project(project.workspace_id, SiteBrief(brand_name='Other', language='en-US', currency='USD'), 'other')
        wrong = '/api/commerce/projects/' + other.id + '/plans/' + created['id']
        assert client.get(wrong + '/outputs').status_code == 404
        assert client.post(wrong + '/advance', json={'expected_revision': 1}).status_code == 404
        assert client.post(wrong + '/resume', json={'expected_revision': 1}).status_code == 404
        assert client.post(path + '/workflows', json={**body, 'max_requests': True}).status_code == 422
        assert client.post(path + '/workflows', json={**body, 'base_url': 'https://untrusted.test'}).status_code == 422


def test_workflow_api_fails_without_verified_context_and_preserves_original_tasks(workflow):
    service, repo, plan, worker = workflow
    app = create_app(worker.settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        project = service.repo.get_project(plan.project_id)
        other = service.repo.create_project(project.workspace_id, SiteBrief(brand_name='Other', language='en-US', currency='USD'), 'other')
        response = client.post('/api/commerce/projects/' + other.id + '/workflows', json={
            'kind': 'build_site', 'prompt': 'Prepare', 'client_request_id': 'one', 'expected_revision': 1})
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'VERIFICATION_UNAVAILABLE'
        assert len(repo.list()) == 1
        assert client.post('/api/tasks', json={'prompt': 'Fix a Python function', 'workspace_id': project.workspace_id,
            'scenario': 'coding', 'client_request_id': 'coding-api'}).status_code == 201


def test_restored_theme_listing_and_workflow_selection_are_project_scoped(workflow):
    from tests.muse.commerce.test_code_bridge import restored_seed
    service, _repo, _plan, worker = workflow
    project, identity, _value, _files = restored_seed(workflow)
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        path = '/api/commerce/projects/' + project.id
        response = client.get(path + '/restored-themes')
        assert response.status_code == 200, response.text
        assert [item['id'] for item in response.json()] == [identity]
        assert 'archive_base64' not in response.text
        assert response.json()[0]['deployment_verified'] is False
        body = {'kind': 'build_site', 'prompt': 'Continue restored theme', 'client_request_id': 'api-restored',
                'expected_revision': project.revision, 'theme_source_id': identity}
        created = client.post(path + '/workflows', json=body)
        assert created.status_code == 201, created.text
        assert created.json()['blueprint']['required_settings']['restored_theme_source']['id'] == identity
        assert client.post(path + '/workflows', json=body).json() == created.json()
        assert client.post(path + '/workflows', json={**body, 'theme_source_id': None}).status_code == 409
        other = service.repo.create_project(project.workspace_id, project.brief, 'other-source-owner')
        assert client.get('/api/commerce/projects/' + other.id + '/restored-themes').json() == []
        assert client.get('/api/commerce/projects/' + other.id + '/restored-themes/' + identity).status_code == 404
        assert client.get(path + '/restored-themes', headers={'Authorization': 'Bearer invalid'}).status_code == 401
