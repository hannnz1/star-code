from fastapi.testclient import TestClient

from muse.main import create_app


def test_archive_is_atomic_revision_bound_and_does_not_change_plans(workflow):
    service, tasks, first, worker = workflow
    project = service.repo.get_project(first.project_id)
    second = service.create_workflow(first.project_id, 'build_site', 'Second storefront', 'archive-second', project.revision)
    with service.repo.db.transaction() as conn:
        first = service._persist(conn, first.model_copy(update={'state': 'CANCELLED'}))
        second = service._persist(conn, second.model_copy(update={'state': 'FAILED'}))
    before_tasks = tasks.list()
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        path = f'/api/commerce/projects/{first.project_id}/plan-archives'
        items = [{'plan_id': p.id, 'expected_plan_revision': p.revision, 'expected_revision': 0}
                 for p in (first, second)]
        bad = {**items[1], 'expected_plan_revision': second.revision - 1}
        assert client.post(path, json={'archived': True, 'items': [items[0], bad]}).status_code == 409
        assert client.get(path).json() == []
        result = client.post(path, json={'archived': True, 'items': items})
        assert result.status_code == 200, result.text
        assert all(item['archived'] and item['revision'] == 1 for item in result.json())
        assert len(client.get(path).json()) == 2
        assert client.post(path, json={'archived': True, 'items': items}).status_code == 409
        restored = client.post(path, json={'archived': False, 'items': [{**items[0], 'expected_revision': 1}]})
        assert restored.status_code == 200, restored.text
        assert restored.json()[0]['archived'] is False and restored.json()[0]['revision'] == 2
        assert service.repo.get_plan(first.id, project_id=first.project_id) == first
        assert service.repo.get_plan(second.id, project_id=first.project_id) == second
        assert tasks.list() == before_tasks


def test_active_unknown_duplicate_and_empty_archives_are_rejected(workflow):
    service, _tasks, plan, worker = workflow
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        path = f'/api/commerce/projects/{plan.project_id}/plan-archives'
        item = {'plan_id': plan.id, 'expected_plan_revision': plan.revision, 'expected_revision': 0}
        assert client.post(path, json={'archived': True, 'items': [item]}).status_code == 409
        assert client.post(path, json={'archived': True, 'items': [{**item, 'plan_id': 'unknown'}]}).status_code == 404
        assert client.post(path, json={'archived': True, 'items': [item, item]}).status_code == 422
        assert client.post(path, json={'archived': True, 'items': []}).status_code == 422
        assert client.get(path).json() == []
