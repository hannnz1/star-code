from fastapi.testclient import TestClient

from muse.main import create_app
from tests.muse.commerce.test_content_proposals import pending_content


def test_merchant_api_confirms_exact_frozen_wording_and_rejects_scope_and_extra_fields(workflow):
    proposals, service, _runtime, plan, *_ = pending_content(workflow)
    worker = workflow[3]
    view = proposals.latest(plan.project_id, plan.id)
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        prefix = f'/api/commerce/projects/{plan.project_id}/plans/{plan.id}/content-proposal'
        assert client.get(prefix).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        assert client.get(prefix).json()['content_digest'] == view.content_digest
        path = prefix + '/' + view.id + '/confirm'
        body = {'expected_project_revision': view.project_revision, 'expected_plan_revision': view.plan_revision,
                'content_digest': view.content_digest}
        assert client.post(path, json={**body, 'passed': True}).status_code == 422
        assert client.post(path, json={**body, 'expected_project_revision': True}).status_code == 422
        assert client.post(path, json={**body, 'content_digest': '0' * 64}).status_code == 409
        assert client.get(prefix.replace(plan.project_id, 'another')).status_code == 404
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        assert response.json()['batch']['result']['drafts'][0]['title'] == 'Ceramic Cup'
        assert client.post(path, json=body).json() == response.json()
        assert service.repo.get_plan(plan.id, project_id=plan.project_id).state == 'STALE'


def test_content_actor_has_no_merchant_confirmation_tool(workflow):
    from muse.tools.registry import ToolRegistry
    _proposals, _service, _runtime, _plan, _manager, ctx, *_ = pending_content(workflow)
    names = {tool.name for tool in ToolRegistry(ctx).definitions()}
    assert 'submit_product_drafts' in names
    assert not any('confirm' in name for name in names)
