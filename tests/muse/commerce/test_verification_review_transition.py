"""Atomic review integration; platform and isolation are explicit fixtures."""
# ruff: noqa: F811
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.preview_repository import PreviewRepository
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401
from tests.muse.commerce.test_trusted_verifier import ready


@pytest.mark.asyncio
async def test_review_transition_preserves_readonly_preview_and_retry_without_grant(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, verifier, connection, _clock, _remote, calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    candidate = await verifier.request_review(job.project_id, job.id, connection=connection)
    plan = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
    assert plan.state == 'REVIEW_REQUIRED'
    preview = PreviewRepository(jobs.repo).latest(job.project_id, job.plan_id, plan.revision)
    assert preview.passed and preview.plan_revision == plan.revision
    assert jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_review'")
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")
    count = len(calls)
    assert await verifier.request_review(job.project_id, job.id, connection=connection) == candidate
    assert len(calls) == count and jobs.repo.get_plan(job.plan_id, project_id=job.project_id) == plan
    with pytest.raises(CommerceFailure): verifier.source.source(job.project_id, job.id)


@pytest.mark.asyncio
async def test_review_failure_rolls_back_plan_report_and_review_together(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    jobs, job, verifier, connection, _clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    def fail(*args): raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
    monkeypatch.setattr(MerchantReleaseApprovalRepository, '_review_extra', fail)
    with pytest.raises(CommerceFailure): await verifier.request_review(job.project_id, job.id, connection=connection)
    assert jobs.repo.get_plan(job.plan_id, project_id=job.project_id).state == 'VERIFYING'
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind IN ('trusted_merchant_verification','merchant_release_review','verification_review_transition')")


@pytest.mark.asyncio
async def test_review_retry_after_expiry_cannot_renew_permission(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, verifier, connection, clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    await verifier.request_review(job.project_id, job.id, connection=connection)
    clock[0] += 1800
    with pytest.raises(CommerceFailure): await verifier.request_review(job.project_id, job.id, connection=connection)
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")
