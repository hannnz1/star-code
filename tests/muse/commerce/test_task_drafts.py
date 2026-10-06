from fastapi.testclient import TestClient

from muse.main import create_app


def test_task_draft_lifecycle_is_durable_and_start_is_explicit(workflow):
    service, tasks, existing, worker = workflow
    project = service.repo.get_project(existing.project_id)
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        path = f'/api/commerce/projects/{project.id}/task-drafts'
        body = {'kind': 'build_site', 'title': '设计首页', 'prompt': 'Prepare a clear storefront',
                'expected_project_revision': project.revision, 'client_request_id': 'draft-one', 'max_requests': 8}
        created = client.post(path, json=body)
        assert created.status_code == 201, created.text
        draft = created.json()
        assert draft['status'] == 'DRAFT' and draft['revision'] == 1
        assert len(draft['proposed_steps']) == 5
        assert len(tasks.list()) == 1
        assert client.post(path, json=body).json() == draft
        assert client.post(path, json={**body, 'prompt': 'Different'}).status_code == 409
        assert [item['id'] for item in client.get(path).json()] == [draft['id']]

        item = path + '/' + draft['id']
        edit = {key: body[key] for key in ('kind', 'title', 'prompt', 'max_requests')}
        edit.update(expected_revision=1, expected_project_revision=project.revision,
                    import_id=None, theme_source_id=None, title='完善首页')
        updated = client.put(item, json=edit)
        assert updated.status_code == 200, updated.text
        assert updated.json()['title'] == '完善首页' and updated.json()['revision'] == 2
        assert client.put(item, json=edit).status_code == 409

        archived = client.post(item + '/archive', json={'expected_revision': 2}).json()
        assert archived['status'] == 'ARCHIVED'
        assert client.post(item + '/start', json={'expected_revision': 3,
            'expected_project_revision': project.revision}).status_code == 409
        restored = client.post(item + '/restore', json={'expected_revision': 3}).json()
        assert restored['status'] == 'DRAFT' and restored['revision'] == 4
        started = client.post(item + '/start', json={'expected_revision': 4,
            'expected_project_revision': project.revision})
        assert started.status_code == 200, started.text
        assert started.json()['status'] == 'STARTED' and started.json()['plan_id']
        assert len(tasks.list()) == 2
        assert client.post(item + '/start', json={'expected_revision': 4,
            'expected_project_revision': project.revision}).status_code == 409
        assert client.post(item + '/archive', json={'expected_revision': 5}).status_code == 409


def test_draft_start_rejects_stale_project_without_creating_task(workflow):
    service, tasks, existing, worker = workflow
    project = service.repo.get_project(existing.project_id)
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        path = f'/api/commerce/projects/{project.id}/task-drafts'
        draft = client.post(path, json={'kind': 'build_site', 'title': '建站草稿', 'prompt': 'Prepare',
            'expected_project_revision': project.revision, 'client_request_id': 'stale-draft'}).json()
        changed = service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'Minimal'}), project.revision)
        assert changed.revision == project.revision + 1
        response = client.post(path + '/' + draft['id'] + '/start', json={
            'expected_revision': draft['revision'], 'expected_project_revision': project.revision})
        assert response.status_code == 409
        assert len(tasks.list()) == 1
        assert client.get(path).json()[0]['status'] == 'DRAFT'


def test_plan_rename_changes_display_metadata_without_invalidating_plan(workflow):
    service, _tasks, plan, worker = workflow
    project = service.repo.get_project(plan.project_id)
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        root = f'/api/commerce/projects/{project.id}'
        assert client.get(root + '/plan-labels').json() == []
        changed = client.post(root + f'/plans/{plan.id}/rename', json={
            'expected_revision': 0, 'title': '秋季店铺改版'})
        assert changed.status_code == 200, changed.text
        assert changed.json()['revision'] == 1
        assert client.post(root + f'/plans/{plan.id}/rename', json={
            'expected_revision': 0, 'title': '重复版本'}).status_code == 409
        assert client.get(root + '/plan-labels').json()[0]['title'] == '秋季店铺改版'
        assert service.repo.get_plan(plan.id, project_id=project.id) == plan
