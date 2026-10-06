"""Authenticated control surface; integration evidence lives in service tests."""
import httpx
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.api import create_connector_app
from muse.commerce_connector.runtime import (
    VerificationHostLease,
    create_verification_service,
)


async def test_verification_controls_default_off_and_reject_evidence_upload():
    app = create_connector_app({}, token='unit-verification-token')
    headers = {'Authorization': 'Bearer unit-verification-token'}
    body = {'project_id': 'project', 'plan_id': 'plan', 'expected_revision': 1, 'client_request_id': 'request'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post('/v1/verification-jobs', json=body)).status_code == 401
        response = await client.post('/v1/verification-jobs', json=body, headers=headers)
        assert response.status_code == 503 and response.json()['error']['code'] == 'VERIFICATION_UNAVAILABLE'
        assert (await client.post('/v1/verification-jobs', json={**body, 'report': {'passed': True}}, headers=headers)).status_code == 422
        assert (await client.post('/v1/verification-jobs/job', json={'project_id': 'project', 'expected_revision': 1,
            'action': 'publish'}, headers=headers)).status_code == 422


async def test_verification_routes_forward_only_validated_fields():
    class Service:
        def reserve(self, *args):
            assert args == ('project', 'plan', 2, 'request')
            return {'id': 'job', 'state': 'QUEUED'}
        def list(self, *args):
            assert args == ('project', 'plan')
            return [{'id': 'job'}]
        def read(self, *args):
            assert args == ('project', 'job')
            return {'id': 'job'}
        def cancel(self, *args):
            assert args == ('project', 'job', 3)
            return {'id': 'job', 'state': 'CANCELLED'}
    app = create_connector_app({}, token='unit-verification-token', verification=Service())
    headers = {'Authorization': 'Bearer unit-verification-token'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post('/v1/verification-jobs', json={'project_id': 'project', 'plan_id': 'plan',
            'expected_revision': 2, 'client_request_id': 'request'}, headers=headers)).json()['state'] == 'QUEUED'
        assert (await client.get('/v1/verification-jobs', params={'project_id': 'project', 'plan_id': 'plan'}, headers=headers)).status_code == 200
        assert (await client.get('/v1/verification-jobs/job', params={'project_id': 'project'}, headers=headers)).status_code == 200
        assert (await client.post('/v1/verification-jobs/job', json={'project_id': 'project',
            'expected_revision': 3, 'action': 'cancel'}, headers=headers)).json()['state'] == 'CANCELLED'


async def test_background_start_requires_exclusive_host_lease():
    app = create_connector_app({}, token='unit-verification-token', verification=object())
    with pytest.raises(CommerceFailure):
        async with app.router.lifespan_context(app):
            pytest.fail('Unowned verifier cannot run')


def test_factory_and_lease_reject_unsupported_windows_host(tmp_path):
    import platform
    if platform.system() != 'Windows':
        pytest.skip('Windows fail-closed contract')
    with pytest.raises(CommerceFailure): VerificationHostLease(tmp_path)
    with pytest.raises(CommerceFailure): create_verification_service({}, None)


async def test_lifecycle_holds_lease_until_cancelled_worker_finishes():
    import asyncio
    entered, stopped = asyncio.Event(), asyncio.Event()
    class Lease:
        fd = 123
        def close(self):
            assert stopped.is_set()
            self.fd = None
    class Service:
        host_lease = Lease()
        def recover_owned(self):
            assert self.host_lease.fd is not None
        async def run(self, stop):
            entered.set()
            try: await stop.wait()
            finally:
                assert self.host_lease.fd is not None
                stopped.set()
    service = Service()
    app = create_connector_app({}, token='unit-verification-token', verification=service)
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(entered.wait(), 2)
        assert service.host_lease.fd == 123
    assert service.host_lease.fd is None


async def test_lifecycle_releases_lease_when_recovery_fails():
    from types import SimpleNamespace

    lease = SimpleNamespace(fd=123)
    lease.close = lambda: setattr(lease, 'fd', None)
    class Service:
        host_lease = lease
        def recover_owned(self): raise CommerceFailure('RESOURCE_CONFLICT')
    app = create_connector_app({}, token='unit-verification-token', verification=Service())
    with pytest.raises(CommerceFailure):
        async with app.router.lifespan_context(app):
            pytest.fail('Recovery must fail closed')
    assert lease.fd is None
