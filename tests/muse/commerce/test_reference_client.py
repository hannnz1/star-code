import httpx
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.platforms.reference import ConnectorReferenceService
from muse.commerce_connector.api import create_connector_app
from muse.commerce_connector.reference_service import ReferenceEnvironmentService
from muse.config import CommerceConnectorSettings
from tests.muse.commerce.test_reference_runner import inputs
from tests.muse.commerce.test_reference_service import Runner


def config():
    return CommerceConnectorSettings(service_url='http://127.0.0.1:8787', token='unit-reference-token', versions_lock_path='unused')


async def test_client_reservation_is_shared_db_bound_and_unknown_never_reprovisions(workflow, tmp_path):
    jobs, job, bundle, _ = inputs(workflow, tmp_path)
    runner = Runner(jobs, job)
    host = ReferenceEnvironmentService(jobs, runner, bundle, ports=(63660, 63661))
    app = create_connector_app({}, token='unit-reference-token', reference=host)
    client = ConnectorReferenceService(jobs, config(), transport=httpx.ASGITransport(app=app))
    project = jobs.repo.get_project(job.project_id)
    reserved = await client.reserve(project.id, project.revision, 'client')
    assert reserved.port == 63661 and reserved == jobs.read(project.id, reserved.id)
    with pytest.raises(CommerceFailure): await client.execute(project.id, reserved.id, reserved.revision, 'provision')
    current = jobs.read(project.id, reserved.id)
    assert current.state == 'UNKNOWN'
    assert 'bootstrap' == runner.calls[-1][0]
    with pytest.raises(CommerceFailure): await client.execute(project.id, current.id, current.revision, 'provision')
    assert len(runner.calls) == 2


@pytest.mark.parametrize('attack', ['redirect', 'secret_error', 'oversize', 'encoding', 'fake_ready', 'scope'])
async def test_reference_client_rejects_forged_results_and_never_retries(workflow, tmp_path, attack):
    jobs, job, _, _ = inputs(workflow, tmp_path)
    calls = []
    def remote(request):
        calls.append(request)
        if attack == 'redirect': return httpx.Response(302, headers={'Location': 'https://evil.invalid'})
        if attack == 'secret_error': return httpx.Response(503, json={'error': {'message': 'private-password'}})
        if attack == 'oversize': return httpx.Response(200, content=b'x' * 65537)
        value = job.model_dump(mode='json')
        if attack == 'fake_ready': value['state'] = 'READY'
        if attack == 'scope': value['project_id'] = 'other'
        return httpx.Response(200, json=value, headers={'content-encoding': 'unknown'} if attack == 'encoding' else {})
    client = ConnectorReferenceService(jobs, config(), transport=httpx.MockTransport(remote))
    with pytest.raises(CommerceFailure) as failure:
        await client.execute(job.project_id, job.id, job.revision, 'provision')
    assert len(calls) == 1 and 'private-password' not in str(failure.value)
    assert jobs.read(job.project_id, job.id).state == 'RESERVED'
