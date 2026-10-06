"""Fixed service status/finalization contracts with simulated platform evidence."""
# ruff: noqa: F811
import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401
from tests.muse.commerce.test_trusted_verifier import ready


@pytest.mark.asyncio
async def test_service_finalizes_collected_job_once_and_exposes_safe_status(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.verification_service import CommerceVerificationService
    jobs, job, verifier, connection, _clock, _remote, calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    service = CommerceVerificationService(verifier.runtime, {connection.connection_id: connection}, transport=verifier.transport)
    results = await service.run_once(job.project_id)
    assert results[0].state == 'REVIEW_REQUIRED'
    before = len(calls)
    again = await service.run_once(job.project_id)
    assert again[0].state == 'REVIEW_REQUIRED' and len(calls) == before
    status = service.read(job.project_id, job.id)
    assert status.completed_phases == ['reference', 'source_capture', 'staging', 'buyer', 'browser', 'facts']
    assert not {'source_binding', 'active', 'token', 'evidence_digest'} & set(status.model_dump())
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")


@pytest.mark.asyncio
async def test_service_does_not_repeat_failed_finalization(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.verification_service import CommerceVerificationService
    jobs, job, verifier, connection, clock, _remote, calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    service = CommerceVerificationService(verifier.runtime, {connection.connection_id: connection}, transport=verifier.transport)
    clock[0] += 1800
    result = (await service.run_once(job.project_id))[0]
    assert result.state == 'NEEDS_RECONCILIATION' and result.error_code == 'APPROVAL_EXPIRED'
    count = len(calls)
    assert (await service.run_once(job.project_id))[0] == result and len(calls) == count
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_review'")


@pytest.mark.asyncio
async def test_service_cancellation_invalidates_generated_review(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    from muse.commerce.verification_service import CommerceVerificationService
    jobs, job, verifier, connection, clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    service = CommerceVerificationService(verifier.runtime, {connection.connection_id: connection}, transport=verifier.transport)
    await service.run_once(job.project_id)
    status = service.read(job.project_id, job.id)
    assert service.cancel(job.project_id, job.id, status.revision).state == 'CANCELLED'
    row = jobs.repo.db.rows("SELECT data FROM commerce_artifacts WHERE kind='merchant_release_review'")[0]
    import json
    intent_digest = json.loads(row['data'])['intent']['digest']
    plan = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
    with pytest.raises(CommerceFailure):
        MerchantReleaseApprovalRepository(jobs.repo, clock=lambda: clock[0]).approve(intent_digest, expected_plan_revision=plan.revision)


@pytest.mark.asyncio
async def test_start_from_unavailable_plan_is_atomic_and_idempotent(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.verification_service import CommerceVerificationService
    jobs, job, verifier, connection, _clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    plan = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
    blocked = jobs.repo.save_plan(plan.model_copy(update={'state': 'BLOCKED', 'error_code': 'VERIFICATION_UNAVAILABLE'}), plan.revision)
    service = CommerceVerificationService(verifier.runtime, {connection.connection_id: connection}, transport=verifier.transport)
    status = service.reserve(job.project_id, job.plan_id, blocked.revision, 'start-after-configuration')
    assert status.state == 'QUEUED' and status.id != job.id
    saved = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
    assert saved.state == 'VERIFYING'
    assert service.reserve(job.project_id, job.plan_id, blocked.revision, 'start-after-configuration') == status
    assert jobs.repo.get_plan(job.plan_id, project_id=job.project_id) == saved
    with pytest.raises(CommerceFailure): service.reserve(job.project_id, job.plan_id, saved.revision, 'different-request')


@pytest.mark.asyncio
async def test_connector_reply_is_shared_journal_bound(staging_source_inputs, tmp_path, monkeypatch):
    import httpx

    from muse.commerce.platforms.verification import ConnectorVerificationService
    from muse.commerce.verification_service import CommerceVerificationService
    from muse.commerce_connector.api import create_connector_app
    from tests.muse.commerce.test_reference_client import config

    jobs, job, verifier, connection, _clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    host = CommerceVerificationService(verifier.runtime, {connection.connection_id: connection}, transport=verifier.transport)
    client = ConnectorVerificationService(jobs, config(), transport=httpx.ASGITransport(app=create_connector_app({},
        token='unit-reference-token', verification=host)))
    current = jobs.read(job.project_id, job.id)
    result = await client.cancel(job.project_id, job.id, current.revision)
    assert result.state == 'CANCELLED' and jobs.read(job.project_id, job.id).cancel_requested
    forged = result.model_copy(update={'state': 'REVIEW_REQUIRED'})
    client.transport = httpx.MockTransport(lambda request: httpx.Response(200, json=forged.model_dump(mode='json')))
    with pytest.raises(CommerceFailure) as failure:
        await client.cancel(job.project_id, job.id, result.revision)
    assert failure.value.public.code == 'WRITE_OUTCOME_UNKNOWN'


@pytest.mark.asyncio
async def test_start_rolls_back_when_source_is_invalid(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.verification_service import CommerceVerificationService
    jobs, job, verifier, connection, _clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    plan = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
    invalid = plan.model_copy(update={'state': 'BLOCKED', 'error_code': 'VERIFICATION_UNAVAILABLE',
        'steps': [step.model_copy(update={'status': 'FAILED'}) for step in plan.steps]})
    blocked = jobs.repo.save_plan(invalid, plan.revision)
    service = CommerceVerificationService(verifier.runtime, {connection.connection_id: connection}, transport=verifier.transport)
    with pytest.raises(CommerceFailure): service.reserve(job.project_id, job.plan_id, blocked.revision, 'invalid-start')
    assert jobs.repo.get_plan(job.plan_id, project_id=job.project_id) == blocked
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='verification_start_request'")


@pytest.mark.asyncio
async def test_report_commit_lost_reply_is_read_only_accounted(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.verification_service import CommerceVerificationService
    jobs, job, verifier, connection, _clock, _remote, calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    service = CommerceVerificationService(verifier.runtime, {connection.connection_id: connection}, transport=verifier.transport)
    original = service.verifier.request_review
    async def lost(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError('simulated interruption after committed review')
    monkeypatch.setattr(service.verifier, 'request_review', lost)
    status = (await service.run_once(job.project_id))[0]
    assert status.state == 'NEEDS_RECONCILIATION'
    count = len(calls)
    reconciled = await service.reconcile(job.project_id, job.id, status.revision)
    assert reconciled.state == 'REVIEW_REQUIRED' and len(calls) == count
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")
