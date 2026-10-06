from tests.muse.commerce.test_project_api import request

pytest_plugins = ['tests.muse.commerce.test_project_api']


def test_structure_draft_is_durable_and_does_not_start_paid_tasks(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    path = '/api/commerce/projects/' + project['id']
    body = {'expected_revision': 1, 'client_request_id': 'blueprint-one'}
    first = client.post(path + '/site-blueprint', json=body)
    assert first.status_code == 201
    plan = first.json()
    assert len(plan['blueprint']['pages']) == 7
    assert plan['state'] == 'NEEDS_INPUT'
    assert plan['snapshot_hash'] is None
    assert plan['steps'] == []
    assert client.post(path + '/site-blueprint', json=body).json()['id'] == plan['id']
    assert client.get(path + '/plans').json() == [plan]
    assert client.get('/api/tasks').json() == []
    client.patch(path, json={'expected_revision': 1, 'brief': {**project['brief'], 'style': 'Updated'}})
    stale = client.get(path + '/plans').json()[0]
    assert stale['state'] == 'STALE'
    assert client.post(path + '/site-blueprint', json=body).status_code == 409


def test_project_scope_cannot_read_another_project_plan(client):
    first = client.post('/api/commerce/projects', json=request(client, 'p1')).json()
    second = client.post('/api/commerce/projects', json=request(client, 'p2')).json()
    path = '/api/commerce/projects/'
    plan = client.post(path + first['id'] + '/site-blueprint', json={'expected_revision': 1, 'client_request_id': 'one'}).json()
    assert client.get(path + second['id'] + '/plans/' + plan['id']).status_code == 404


def test_structure_reuses_current_draft_and_saves_revision_checked_edits(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    path = '/api/commerce/projects/' + project['id']
    plan = client.post(path + '/site-blueprint', json={'expected_revision': 1, 'client_request_id': 'first'}).json()
    assert client.post(path + '/site-blueprint', json={'expected_revision': 1, 'client_request_id': 'another'}).json()['id'] == plan['id']
    body = {'expected_revision': 1, 'expected_plan_revision': 1,
            'pages': plan['blueprint']['pages'], 'navigation': plan['blueprint']['navigation']}
    body['pages'][0].update(title='Pet Home', slug='pet-home')
    body['navigation'][0].update(label='Pets', slug='pet-home')
    endpoint = path + '/site-blueprint/' + plan['id']
    saved = client.patch(endpoint, json=body)
    assert saved.status_code == 200
    assert saved.json()['revision'] == 2
    assert saved.json()['blueprint']['pages'][0]['title'] == 'Pet Home'
    assert saved.json()['blueprint']['required_settings'] == plan['blueprint']['required_settings']
    assert saved.json()['content_hash'] != plan['content_hash']
    assert client.patch(endpoint, json=body).status_code == 409
    assert client.post(path + '/site-blueprint', json={'expected_revision': 1, 'client_request_id': 'third'}).json() == saved.json()
    body['expected_plan_revision'] = 2
    body['navigation'][0]['slug'] = 'missing-page'
    assert client.patch(endpoint, json=body).status_code == 422
    body['navigation'][0]['slug'] = 'product'
    assert client.patch(endpoint, json=body).status_code == 422
    assert client.patch(endpoint, json={**body, 'navigation': []}).status_code == 422
    body['navigation'][0]['slug'] = 'pet-home'
    client.patch(path, json={'expected_revision': 1, 'brief': {**project['brief'], 'style': 'Updated'}})
    body['expected_revision'] = 2
    assert client.patch(endpoint, json=body).status_code == 409
    new = client.post(path + '/site-blueprint', json={'expected_revision': 2, 'client_request_id': 'new-revision'}).json()
    assert new['id'] != plan['id']
    assert len(client.get(path + '/plans').json()) == 2


def test_build_workflow_uses_saved_structure_and_cannot_be_edited(workflow):
    from muse.commerce.repository import CommerceRepository
    service, runtime, team, worker = workflow
    repo = CommerceRepository(runtime)
    project = repo.get_project(team.project_id)
    draft = repo.create_site_blueprint(project.id, 'structure', project.revision)
    pages = [p.model_copy(deep=True) for p in draft.blueprint.pages]
    pages[0].title = 'Pet Home'
    saved = repo.edit_site_blueprint(project.id, draft.id, project.revision, draft.revision, pages, draft.blueprint.navigation)
    built = service.create_workflow(project.id, 'build_site', 'Use edited structure', 'edited-workflow', project.revision)
    assert built.blueprint.pages[0].title == 'Pet Home'
    assert built.blueprint.required_settings['buyer_flow_verified'] is False
    import pytest
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        repo.edit_site_blueprint(project.id, built.id, project.revision, built.revision, pages, saved.blueprint.navigation)
