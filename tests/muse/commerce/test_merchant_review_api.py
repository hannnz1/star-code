import json

import pytest
from fastapi.testclient import TestClient

from muse.commerce.errors import CommerceFailure
from muse.main import create_app
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_merchant_publisher import merchant_publisher  # noqa: F401


def test_merchant_review_exposes_descriptors_without_private_bytes_or_permits(merchant_review):  # noqa: F811
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    from muse.commerce.merchant_review import MerchantReviewRepository
    repo, project, plan, intent, evidence, connection, clock, _ = merchant_review
    approvals = MerchantReleaseApprovalRepository(repo, clock=lambda: clock[0])
    approvals.stage_review(intent, evidence, connection=connection, expected_plan_revision=plan.revision)
    view = MerchantReviewRepository(approvals).read(project.id, plan.id, intent.digest, plan.revision)
    value = view.model_dump(mode='json')
    assert view.approvable and view.total_steps == 18
    assert view.products[0].sku == 'CUP' and view.images[0].sha256 == intent.images[0].image.sha256
    assert view.source_snapshot_hash == intent.snapshot_hash and view.target_snapshot_hash == intent.target_snapshot_hash
    assert intent.images[0].content_base64 not in json.dumps(value)
    assert not {'intent', 'source_archive', 'content_base64', 'permit', 'credentials'} & set(value)
    with pytest.raises(CommerceFailure):
        MerchantReviewRepository(approvals).read('other', plan.id, intent.digest, plan.revision)


def test_merchant_review_api_auth_scope_stale_and_no_client_evidence(merchant_review, workflow):  # noqa: F811
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    repo, project, plan, intent, evidence, connection, clock, _ = merchant_review
    approvals = MerchantReleaseApprovalRepository(repo, clock=lambda: clock[0])
    approvals.stage_review(intent, evidence, connection=connection, expected_plan_revision=plan.revision)
    app = create_app(workflow[3].settings)
    app.state.commerce_merchant_approvals = approvals
    path = f'/api/commerce/projects/{project.id}/plans/{plan.id}/releases/{intent.digest}'
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        assert client.get(path, params={'revision': plan.revision}).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + workflow[3].settings.access_token.get_secret_value()
        assert client.get(path, params={'revision': plan.revision}).status_code == 200
        assert client.get(path, params={'revision': 999}).status_code == 409
        assert client.post(path + '/approve', json={'expected_revision': plan.revision, 'passed': True}).status_code == 422
        body = {'expected_revision': plan.revision}
        first = client.post(path + '/approve', json=body)
        assert first.status_code == 200, first.text
        assert first.json()['status'] == 'approved' and not first.json()['approvable']
        assert client.post(path + '/approve', json=body).json() == first.json()
        assert client.post(path + '/publish', json={'expected_revision': first.json()['plan_revision']}).status_code == 503
        assert client.post(path + '/reconcile', json={'expected_revision': first.json()['plan_revision']}).status_code == 503
        assert client.post(path, json={'report': {'passed': True}}).status_code == 405
        assert client.get(path.replace(project.id, 'other'), params={'revision': plan.revision}).status_code == 404


@pytest.mark.asyncio
async def test_publication_service_reconcile_is_get_only_and_progress_has_no_operation_payload(merchant_publisher, merchant_review):  # noqa: F811
    from muse.commerce.merchant_review import MerchantPublicationService
    publisher, remote, _grant = merchant_publisher
    repo, project, plan, intent, *_ = merchant_review
    service = MerchantPublicationService(publisher.approvals, lambda ref: publisher)
    revision = repo.get_plan(plan.id, project_id=project.id).revision
    # A recovery click must not prepare/send a fresh write.
    view = await service.execute(project.id, plan.id, intent.digest, revision, reconcile_only=True)
    assert view.completed_steps == 0 and remote['calls'] == []
    remote['lose_reply'] = True
    with pytest.raises(CommerceFailure):
        await service.execute(project.id, plan.id, intent.digest, revision, reconcile_only=False)
    remote['calls'].clear()
    revision = repo.get_plan(plan.id, project_id=project.id).revision
    pending_view = service.review(project.id, plan.id, intent.digest, revision)
    assert pending_view.last_attempt.state == 'NEEDS_RECONCILIATION'
    assert not pending_view.last_attempt.effect_verified
    view = await service.execute(project.id, plan.id, intent.digest, revision, reconcile_only=True)
    assert view.completed_steps == 1 and view.last_attempt.effect_verified
    assert all(method == 'GET' for method, _ in remote['calls'])
    assert 'content_base64' not in view.model_dump_json() and 'operation' not in view.last_attempt.model_dump()


@pytest.mark.asyncio
async def test_publication_service_rejects_wrong_resolved_connection_and_stale_revision_before_network(merchant_publisher, merchant_review):  # noqa: F811
    from muse.commerce.merchant_review import MerchantPublicationService
    from muse.commerce_connector.wordpress import WordPressConnection
    publisher, remote, _ = merchant_publisher
    repo, project, plan, intent, *_ = merchant_review
    service = MerchantPublicationService(publisher.approvals, lambda ref: publisher)
    with pytest.raises(CommerceFailure):
        await service.execute(project.id, plan.id, intent.digest, 999, reconcile_only=False)
    publisher.connection = WordPressConnection('wrong', project.id, 'staging', intent.target.public_url, 'x', 'x')
    with pytest.raises(CommerceFailure):
        await service.execute(project.id, plan.id, intent.digest, repo.get_plan(plan.id, project_id=project.id).revision, reconcile_only=False)
    assert remote['calls'] == []
