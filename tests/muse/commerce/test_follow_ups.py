from fastapi.testclient import TestClient

from muse.main import create_app


def test_suggestions_bind_evidence_and_accept_only_drafts_with_retry_protection(workflow):
    service, tasks, plan, worker = workflow
    # Controlled terminal state fixture, not evidence of a real production release.
    plan = service.repo.save_plan(plan.model_copy(update={'state': 'SUCCEEDED'}), plan.revision)
    project = service.repo.get_project(plan.project_id)
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        path = f'/api/commerce/projects/{project.id}/plans/{plan.id}/follow-ups'
        before = len(tasks.list())
        suggestions = client.get(path).json()
        assert len(suggestions) == 2
        assert {item['kind'] for item in suggestions} == {'build_site', 'launch_products'}
        assert len(tasks.list()) == before
        item = suggestions[0]
        body = {'suggestion_id': item['id'], 'review_digest': item['review_digest'], 'client_request_id': 'accept-one'}
        response = client.post(path + '/accept', json=body)
        assert response.status_code == 201, response.text
        draft = response.json()
        assert draft['status'] == 'DRAFT' and draft['plan_id'] is None
        assert draft['source_plan_id'] == plan.id and draft['source_plan_revision'] == plan.revision
        assert draft['suggestion_id'] == item['id']
        assert len(tasks.list()) == before
        assert client.post(path + '/accept', json=body).json() == draft
        other = {**body, 'suggestion_id': suggestions[1]['id'], 'review_digest': suggestions[1]['review_digest']}
        assert client.post(path + '/accept', json=other).status_code == 409
        service.repo.save_plan(plan.model_copy(update={'state': 'FAILED', 'error_code': 'MODEL_UNAVAILABLE'}), plan.revision)
        assert client.post(path + '/accept', json={**body, 'client_request_id': 'stale'}).status_code == 409
        assert client.post(path + '/accept', json=body).json() == draft
        repair = client.get(path).json()
        assert len(repair) == 1 and 'MODEL_UNAVAILABLE' in repair[0]['prompt']
        assert len(service.repo.db.rows('SELECT id FROM commerce_task_drafts')) == 1


def test_running_cancelled_foreign_and_stale_sources_do_not_offer_follow_ups(workflow):
    service, tasks, plan, worker = workflow
    project = service.repo.get_project(plan.project_id)
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        path = f'/api/commerce/projects/{project.id}/plans/{plan.id}/follow-ups'
        assert client.get(path).json() == []
        assert client.get(path.replace(plan.id, 'missing-plan')).status_code == 404
        plan = service.repo.save_plan(plan.model_copy(update={'state': 'BLOCKED', 'error_code': 'MODEL_UNAVAILABLE'}), plan.revision)
        item = client.get(path).json()[0]
        service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'Minimal'}), project.revision)
        assert client.get(path).json() == []
        assert client.post(path + '/accept', json={'suggestion_id': item['id'], 'review_digest': item['review_digest'],
            'client_request_id': 'old-project'}).status_code == 409
        assert len(service.repo.db.rows('SELECT id FROM commerce_task_drafts')) == 0


def test_cancel_request_hides_suggestions_before_plan_advance(workflow):
    service, tasks, plan, worker = workflow
    plan = service.repo.save_plan(plan.model_copy(update={'state': 'BLOCKED', 'error_code': 'MODEL_UNAVAILABLE'}), plan.revision)
    from muse.commerce.follow_ups import FollowUpService
    suggestions = FollowUpService(service.repo, service)
    assert suggestions.list(plan.project_id, plan.id)
    root = tasks.get(next(step.task_id for step in plan.steps if step.role == 'store_manager'))
    tasks.control(root.id, 'cancel', expected_revision=root.revision)
    assert suggestions.list(plan.project_id, plan.id) == []


def test_suggestion_batch_is_atomic_and_retry_does_not_duplicate_drafts(workflow):
    from muse.commerce.follow_ups import FollowUpBatch, FollowUpService
    from muse.commerce.errors import CommerceFailure
    import pytest
    service, tasks, plan, worker = workflow
    plan = service.repo.save_plan(plan.model_copy(update={'state': 'SUCCEEDED'}), plan.revision)
    suggestions = FollowUpService(service.repo, service)
    items = suggestions.list(plan.project_id, plan.id)
    selected = [{'suggestion_id': item.id, 'review_digest': item.review_digest} for item in items]
    bad = FollowUpBatch(items=[selected[0], {**selected[1], 'review_digest': '0' * 64}], client_request_id='bad-batch')
    with pytest.raises(CommerceFailure):
        suggestions.accept_batch(plan.project_id, plan.id, bad)
    assert service.repo.db.rows('SELECT id FROM commerce_task_drafts') == []
    request = FollowUpBatch(items=selected, client_request_id='good-batch')
    values = suggestions.accept_batch(plan.project_id, plan.id, request)
    assert len(values) == 2 and all(item.status == 'DRAFT' for item in values)
    assert suggestions.accept_batch(plan.project_id, plan.id, request) == values
    assert len(tasks.list()) == 1


def test_code_conflict_produces_version_bound_repair_draft(workflow):
    from muse.commerce.api import CodeIntegrationInput
    from muse.commerce.code_integration import CommerceCodeIntegration
    from muse.commerce.follow_ups import FollowUpAccept, FollowUpService
    from tests.muse.commerce.test_code_integration import apply_body, seal
    service, tasks, plan, worker = workflow
    first = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    project = service.repo.get_project(plan.project_id)
    second = service.create_workflow(project.id, 'build_site', 'Other color', 'followup-conflict', project.revision)
    second = seal(service, tasks, second, worker, 'style.css', '\nbody { color: #222; }\n')
    integration = CommerceCodeIntegration(service.repo, worker.settings.data_dir / 'commerce-source.git')
    review = integration.review(project.id, first.id, first.revision)
    integration.apply(project.id, first.id, CodeIntegrationInput(**apply_body(review.model_dump(), 'follow-up-head')))
    suggestions = FollowUpService(service.repo, service)
    item = suggestions.list(project.id, second.id)[0]
    assert item.title == '准备代码冲突修复' and 'style.css' in item.prompt
    before = len(tasks.list())
    draft = suggestions.accept(project.id, second.id, FollowUpAccept(suggestion_id=item.id,
        review_digest=item.review_digest, client_request_id='repair-draft'))
    assert draft.status == 'DRAFT' and draft.code_base_revision == 1
    assert draft.source_plan_id == second.id and len(tasks.list()) == before
    # Release the original executions before admitting the repair plan.
    for original in (first, second):
        root_id = next(step.task_id for step in original.steps if step.role == 'store_manager')
        root = tasks.get(root_id)
        tasks.finish(root_id, root.lease_owner, root.lease_epoch, 'SUCCEEDED', 'controlled fixture')
        developer_id = next(step.task_id for step in original.steps if step.role == 'site_developer')
        developer = tasks.get(developer_id)
        tasks.finish(developer_id, developer.lease_owner, developer.lease_epoch, 'SUCCEEDED', 'controlled fixture')
    from muse.commerce.task_drafts import CommerceDraftService
    from muse.commerce.conflict_context import read_repair_file
    started = CommerceDraftService(service.repo, service).start(project.id, draft.id, draft.revision, project.revision)
    repair = service.repo.get_plan(started.plan_id, project_id=project.id)
    assert repair.blueprint.required_settings['repair_context']['files'] == ['style.css']
    with service.repo.db.transaction() as conn:
        evidence = read_repair_file(service.repo, conn, repair, 'style.css')
    assert 'color: #111' in evidence['current'] and 'color: #222' in evidence['candidate']
    assert 'color: #111' not in evidence['base']
