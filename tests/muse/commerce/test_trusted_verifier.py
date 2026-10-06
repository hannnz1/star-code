"""Report integration with explicit simulated Docker/CMS/browser evidence."""
# ruff: noqa: F811
import httpx
import pytest
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.release_approval import CHECKS
from muse.commerce.verification_runtime import VerificationRuntime
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_readback_verification_stage import setup
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401


async def ready(inputs, tmp_path, monkeypatch):
    from muse.commerce.trusted_verifier import TrustedMerchantVerifier
    jobs, job, _browser, _facts, worker, remote = await setup(inputs, tmp_path, monkeypatch)
    await worker.run_step(job.project_id, job.id)
    await worker.run_step(job.project_id, job.id)
    pipeline = VerificationRuntime(jobs, **worker.handlers)
    original, connection, clock, proofs = inputs[3:]
    calls = []
    def transport(request):
        calls.append(request)
        assert request.method == 'GET'
        if str(request.url).startswith(connection.base_url + '/'):
            if request.url.path.endswith('/snapshot'):
                return httpx.Response(200, json=original.initial_snapshot.model_dump(mode='json'))
            param, value = next(iter(request.url.params.items()))
            if param == 'media_sha256': key = 'media-sha256:' + value
            else:
                import hashlib
                prefix = 'page-slug:' if param == 'page_slug' else 'sku:'
                key = prefix + hashlib.sha256((value.casefold() if param == 'sku' else value).encode()).hexdigest()
            return httpx.Response(200, json=proofs[key])
        if request.url.path.endswith('/snapshot'): return httpx.Response(200, json=remote['snapshot'])
        return httpx.Response(200, json=remote['proofs']['media-sha256:' + request.url.params['media_sha256']])
    verifier = TrustedMerchantVerifier(pipeline, transport=httpx.MockTransport(transport))
    return jobs, job, verifier, connection, clock, remote, calls


@pytest.mark.asyncio
async def test_fixed_verifier_persists_nine_checks_bound_to_current_merchant_intent(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, verifier, connection, _clock, _remote, calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    candidate = await verifier.collect(job.project_id, job.id, connection=connection)
    assert candidate.report.passed and {item['name'] for item in candidate.report.checks} == CHECKS | {'layout_tablet'}
    assert candidate.report.changeset_digest == candidate.intent.digest
    assert candidate.intent.target.connector_ref == connection.connection_id
    assert candidate.intent.target.connector_ref != verifier.runtime.worker.handlers['source_capture']._connection(jobs.read(job.project_id, job.id)).connection_id
    assert len(jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")) == 1
    assert jobs.repo.get_plan(job.plan_id, project_id=job.project_id).state == 'VERIFYING'
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")
    repeated = await verifier.collect(job.project_id, job.id, connection=connection)
    assert repeated == candidate and all(request.method == 'GET' for request in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['expired', 'price', 'png', 'order'])
async def test_verifier_refuses_incomplete_or_stale_evidence(staging_source_inputs, tmp_path, monkeypatch, failure):
    jobs, job, verifier, connection, clock, remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    if failure == 'expired': clock[0] += 1800
    elif failure == 'price': remote['snapshot']['products'][0]['price'] = '99.00'
    else:
        kind = 'commerce_preview_frame' if failure == 'png' else 'buyer_price_fact'
        with jobs.db.transaction() as conn:
            conn.execute(text('UPDATE commerce_artifacts SET digest=:bad WHERE project_id=:project AND kind=:kind'),
                {'bad': '0' * 64, 'project': job.project_id, 'kind': kind})
    with pytest.raises(CommerceFailure): await verifier.collect(job.project_id, job.id, connection=connection)
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")


def test_report_producer_has_no_arbitrary_passed_input():
    from muse.commerce.trusted_verifier import TrustedMerchantVerifier
    with pytest.raises(CommerceFailure): TrustedMerchantVerifier({'passed': True})


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['none', 'expired', 'png', 'rewound'])
async def test_approval_rechecks_generated_report_provenance(staging_source_inputs, tmp_path, monkeypatch, change):
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    jobs, job, verifier, connection, clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    candidate = await verifier.collect(job.project_id, job.id, connection=connection)
    # Simulate the separate trusted review transition. collect itself does not
    # perform it and this test never grants permission or sends CMS writes.
    plan = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
    plan = jobs.repo.save_plan(plan.model_copy(update={'state': 'REVIEW_REQUIRED'}), plan.revision)
    approvals = MerchantReleaseApprovalRepository(jobs.repo, clock=lambda: clock[0])
    if change == 'expired': clock[0] += 1800
    if change == 'rewound': clock[0] -= 1
    if change == 'png':
        with jobs.db.transaction() as conn:
            conn.execute(text("UPDATE commerce_artifacts SET data=:data WHERE project_id=:project AND kind='commerce_preview_frame'"),
                {'data': '{}', 'project': job.project_id})
    if change == 'none':
        assert approvals.stage_review(candidate.intent, candidate.report.id, connection=connection,
            expected_plan_revision=plan.revision) == candidate.intent
    else:
        with pytest.raises(CommerceFailure):
            approvals.stage_review(candidate.intent, candidate.report.id, connection=connection,
                expected_plan_revision=plan.revision)
        assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_review'")


@pytest.mark.asyncio
async def test_source_change_during_final_target_read_prevents_report(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, verifier, connection, _clock, _remote, _calls = await ready(staging_source_inputs, tmp_path, monkeypatch)
    transport = verifier.transport
    def changed(request):
        if str(request.url).startswith(connection.base_url + '/'):
            plan = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
            jobs.repo.save_plan(plan.model_copy(update={'state': 'CANCELLED'}), plan.revision)
        return transport.handle_request(request)
    verifier.transport = httpx.MockTransport(changed)
    with pytest.raises(CommerceFailure): await verifier.collect(job.project_id, job.id, connection=connection)
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")
