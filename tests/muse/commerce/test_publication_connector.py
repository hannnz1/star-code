import json

import httpx
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_review import MerchantPublicationService
from muse.commerce_connector.api import create_connector_app
from muse.config import CommerceConnectorSettings
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_merchant_publisher import merchant_publisher  # noqa: F401


@pytest.mark.asyncio
async def test_publication_connector_exposes_fixed_commands_not_wordpress_credentials(merchant_publisher, merchant_review):  # noqa: F811
    from muse.commerce.platforms.publication import ConnectorPublicationService
    publisher, remote, _ = merchant_publisher
    repo, project, plan, intent, *_ = merchant_review
    server_service = MerchantPublicationService(publisher.approvals, lambda ref: publisher)
    token = 'separate-connector-token-012345'
    app = create_connector_app({publisher.connection.connection_id: publisher.connection}, token=token, publication=server_service)
    config = CommerceConnectorSettings(service_url='http://127.0.0.1:8787', token=token, versions_lock_path='unused')
    client = ConnectorPublicationService(publisher.approvals, config, transport=httpx.ASGITransport(app=app))
    revision = repo.get_plan(plan.id, project_id=project.id).revision
    view = await client.execute(project.id, plan.id, intent.digest, revision, reconcile_only=False)
    assert view.completed_steps == 1 and len(remote['receipts']) == 1
    assert 'content_base64' not in view.model_dump_json() and 'fixture' not in view.model_dump_json()
    remote['calls'].clear()
    assert await client.review(project.id, plan.id, intent.digest, view.plan_revision) == view
    assert remote['calls'] == []
    path = f'/v1/connections/{publisher.connection.connection_id}/publication/{plan.id}/{intent.digest}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=config.service_url) as raw:
        body = {'project_id': project.id, 'expected_revision': view.plan_revision, 'action': 'publish'}
        assert (await raw.post(path, json=body)).status_code == 401
        raw.headers['Authorization'] = 'Bearer ' + token
        assert (await raw.post(path, json={**body, 'operation': {'kind': 'shell'}})).status_code == 422
        assert (await raw.post(path, json={**body, 'action': 'arbitrary'})).status_code == 422
        assert (await raw.post(path, json={**body, 'project_id': 'other'})).status_code == 404
    assert remote['calls'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('attack', ['redirect', 'scope', 'source', 'progress', 'oversized', 'secret_error'])
async def test_main_publication_client_rejects_remote_scope_and_data_and_never_retries(merchant_publisher, merchant_review, attack):  # noqa: F811
    from muse.commerce.platforms.publication import ConnectorPublicationService
    publisher, _, _ = merchant_publisher
    repo, project, plan, intent, *_ = merchant_review
    revision = repo.get_plan(plan.id, project_id=project.id).revision
    view = MerchantPublicationService(publisher.approvals, lambda ref: publisher).review(project.id, plan.id, intent.digest, revision)
    calls = []
    def transport(request):
        calls.append(request)
        assert request.headers['Authorization'] == 'Bearer separate-token-012345'
        if attack == 'redirect': return httpx.Response(302, headers={'Location': 'https://evil.invalid'})
        if attack == 'oversized': return httpx.Response(200, content=b'x' * (4 * 1024 * 1024 + 1))
        if attack == 'secret_error': return httpx.Response(503, json={'error': {'code': 'WRITE_OUTCOME_UNKNOWN', 'message': 'private-password', 'path': '/private/secret'}})
        value = view.model_dump(mode='json')
        if attack == 'scope': value['target']['connector_ref'] = 'wrong'
        elif attack == 'progress': value['completed_steps'] = 1
        else: value['source_digest'] = 'e' * 64
        return httpx.Response(200, content=json.dumps(value).encode())
    config = CommerceConnectorSettings(service_url='http://127.0.0.1:8787', token='separate-token-012345', versions_lock_path='unused')
    client = ConnectorPublicationService(publisher.approvals, config, transport=httpx.MockTransport(transport))
    with pytest.raises(CommerceFailure) as failure:
        await client.execute(project.id, plan.id, intent.digest, revision, reconcile_only=False)
    assert 'private-password' not in str(failure.value) and len(calls) == 1
    assert 'content_base64' not in calls[0].content.decode()
