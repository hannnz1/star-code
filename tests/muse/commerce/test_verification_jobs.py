"""Private job journal contracts; simulated receipts are not Linux evidence."""
# ruff: noqa: F811
import pytest
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401


def reserve(inputs):
    from muse.commerce.verification_jobs import VerificationJobRepository
    repo, project, plan, *_ = inputs
    jobs = VerificationJobRepository(repo)
    return jobs, jobs.reserve(project.id, plan.id, plan.revision, 'verify-once')


def test_verification_reservation_survives_restart_without_merchant_permission(staging_source_inputs):
    from muse.commerce.verification_jobs import VerificationJobRepository
    jobs, job = reserve(staging_source_inputs)
    assert job.state == 'QUEUED' and job.completed == [] and job.active is None
    assert VerificationJobRepository(jobs.repo).reserve(job.project_id, job.plan_id, job.plan_revision, 'verify-once') == job
    assert jobs.queued(job.project_id) == [job]
    assert jobs.db.rows("SELECT id FROM commerce_artifacts WHERE kind IN ('trusted_merchant_verification','merchant_release_grant')") == []


def test_atomic_claim_and_restart_do_not_repeat_an_inflight_effect(staging_source_inputs):
    from muse.commerce.verification_jobs import VerificationJobRepository
    jobs, job = reserve(staging_source_inputs)
    claimed = jobs.claim(job.project_id, job.id, job.revision, 'reference')
    assert claimed.state == 'RUNNING' and claimed.active.phase == 'reference'
    restarted = VerificationJobRepository(jobs.repo)
    for revision in (job.revision, claimed.revision):
        with pytest.raises(CommerceFailure): restarted.claim(job.project_id, job.id, revision, 'reference')
    unknown = restarted.interrupt(job.project_id, job.id, claimed.revision)
    assert unknown.state == 'NEEDS_RECONCILIATION'
    with pytest.raises(CommerceFailure): restarted.claim(job.project_id, job.id, unknown.revision, 'reference')
    accounted = restarted.record(job.project_id, job.id, unknown.active.token, 'a' * 64)
    assert accounted.state == 'QUEUED' and accounted.completed[0].evidence_digest == 'a' * 64
    assert restarted.record(job.project_id, job.id, unknown.active.token, 'a' * 64) == accounted
    with pytest.raises(CommerceFailure): restarted.record(job.project_id, job.id, unknown.active.token, 'b' * 64)


@pytest.mark.parametrize('change', ['project', 'plan', 'cancel', 'media', 'code'])
def test_changed_source_or_cancel_blocks_the_next_effect(staging_source_inputs, change):
    jobs, job = reserve(staging_source_inputs)
    repo, project, plan, *_ = staging_source_inputs
    if change == 'project': repo.update_brief(project.id, project.brief, project.revision)
    if change == 'plan': repo.save_plan(plan.model_copy(update={'content_hash': 'f' * 64}), plan.revision)
    with repo.db.transaction() as conn:
        if change == 'cancel':
            conn.execute(text('UPDATE tasks SET cancel_requested=1 WHERE id=(SELECT root_task_id FROM commerce_plans WHERE id=:id)'), {'id': plan.id})
        if change in {'media', 'code'}:
            kind = 'product_media' if change == 'media' else 'theme_code_draft'
            conn.execute(text('UPDATE commerce_artifacts SET digest=:sha WHERE project_id=:project AND kind=:kind'),
                {'sha': 'e' * 64, 'project': project.id, 'kind': kind})
    with pytest.raises(CommerceFailure): jobs.claim(project.id, job.id, job.revision, 'reference')
    assert jobs.read(project.id, job.id) == job


def test_late_receipt_is_accounted_after_cancellation_but_never_advances(staging_source_inputs):
    jobs, job = reserve(staging_source_inputs)
    active = jobs.claim(job.project_id, job.id, job.revision, 'reference')
    cancelled = jobs.cancel(job.project_id, job.id, active.revision)
    assert cancelled.state == 'NEEDS_RECONCILIATION' and cancelled.cancel_requested
    late = jobs.record(job.project_id, job.id, active.active.token, 'a' * 64)
    assert late.state == 'CANCELLED' and len(late.completed) == 1
    with pytest.raises(CommerceFailure): jobs.claim(job.project_id, job.id, late.revision, 'source_capture')


def test_fixed_phases_collect_receipt_digests_without_creating_a_passed_report(staging_source_inputs):
    from muse.commerce.verification_jobs import PHASES
    jobs, job = reserve(staging_source_inputs)
    with pytest.raises(CommerceFailure): jobs.claim(job.project_id, job.id, job.revision, 'buyer')
    for phase in PHASES:
        active = jobs.claim(job.project_id, job.id, job.revision, phase)
        with pytest.raises(CommerceFailure): jobs.record(job.project_id, job.id, '0' * 32, digest(phase))
        job = jobs.record(job.project_id, job.id, active.active.token, digest(phase))
    assert job.state == 'COLLECTED' and jobs.queued(job.project_id) == []
    assert jobs.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'") == []
    assert jobs.repo.get_plan(job.plan_id, project_id=job.project_id).state == 'VERIFYING'


@pytest.mark.parametrize('mode', ['foreign', 'changed_request', 'missing_capture', 'bad_digest'])
def test_scope_request_and_integrity_fail_closed(staging_source_inputs, mode):
    jobs, job = reserve(staging_source_inputs)
    if mode == 'foreign':
        with pytest.raises(CommerceFailure): jobs.read('foreign-project', job.id)
    elif mode == 'changed_request':
        with pytest.raises(CommerceFailure): jobs.reserve(job.project_id, job.plan_id, job.plan_revision + 1, 'verify-once')
    elif mode == 'missing_capture':
        with jobs.db.transaction() as conn:
            conn.execute(text("DELETE FROM commerce_artifacts WHERE kind='theme_code_draft'"))
        with pytest.raises(CommerceFailure): jobs.reserve(job.project_id, job.plan_id, job.plan_revision, 'new-request')
    else:
        with jobs.db.transaction() as conn:
            conn.execute(text('UPDATE commerce_artifacts SET digest=:digest WHERE id=:id'), {'id': job.id, 'digest': 'f' * 64})
        with pytest.raises(CommerceFailure): jobs.read(job.project_id, job.id)


def test_a_new_request_cannot_repeat_the_same_frozen_source(staging_source_inputs):
    jobs, job = reserve(staging_source_inputs)
    with pytest.raises(CommerceFailure): jobs.reserve(job.project_id, job.plan_id, job.plan_revision, 'different-request')
    cancelled = jobs.cancel(job.project_id, job.id, job.revision)
    assert cancelled.state == 'CANCELLED'
    with pytest.raises(CommerceFailure): jobs.reserve(job.project_id, job.plan_id, job.plan_revision, 'after-cancel')


def test_completed_backlog_does_not_hide_a_later_queued_job(staging_source_inputs):
    import uuid

    from muse.commerce.repository import encode
    from muse.commerce.verification_jobs import PHASES, VerificationReceipt
    jobs, job = reserve(staging_source_inputs)
    completed = [VerificationReceipt(phase=phase, token=uuid.uuid4().hex, evidence_digest=digest(phase)) for phase in PHASES]
    # Explicit historical fixture data; no fake report or production side effect.
    with jobs.db.transaction() as conn:
        old = job.model_copy(update={'state': 'COLLECTED', 'completed': completed})
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
            {'id': old.id, 'data': encode(old), 'digest': digest(old)})
        for _ in range(100):
            archived = old.model_copy(update={'id': uuid.uuid4().hex})
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'verification_job',:digest,:data)"),
                {'id': archived.id, 'project': job.project_id, 'plan': job.plan_id, 'digest': digest(archived), 'data': encode(archived)})
        later = job.model_copy(update={'id': uuid.uuid4().hex})
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'verification_job',:digest,:data)"),
            {'id': later.id, 'project': job.project_id, 'plan': job.plan_id, 'digest': digest(later), 'data': encode(later)})
    assert jobs.queued(job.project_id) == [later]


@pytest.mark.parametrize('revision', [True, 1.0, '1'])
def test_revision_must_be_an_integer(staging_source_inputs, revision):
    jobs, job = reserve(staging_source_inputs)
    with pytest.raises(CommerceFailure): jobs.claim(job.project_id, job.id, revision, 'reference')


@pytest.mark.asyncio
async def test_worker_commits_claim_before_handler_and_two_workers_do_not_double_send(staging_source_inputs):
    import asyncio

    from muse.commerce.verification_jobs import PHASES
    from muse.commerce.verification_worker import VerificationWorker
    jobs, job = reserve(staging_source_inputs)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(active):
        assert jobs.read(job.project_id, job.id).active == active.active
        calls.append(active.active.phase)
        entered.set()
        await release.wait()
        return digest(['explicit-fake-private-receipt', active.active.phase])
    worker = VerificationWorker(jobs, {phase: handler for phase in PHASES})
    pending = asyncio.create_task(worker.run_step(job.project_id, job.id))
    await entered.wait()
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    release.set()
    saved = await pending
    assert calls == ['reference'] and saved.state == 'QUEUED'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['timeout', 'exception', 'invalid_receipt', 'cancel'])
async def test_worker_failure_keeps_existing_claim_and_never_resends(staging_source_inputs, mode):
    import asyncio

    from muse.commerce.verification_jobs import PHASES
    from muse.commerce.verification_worker import VerificationWorker
    jobs, job = reserve(staging_source_inputs)
    calls = []
    async def handler(active):
        calls.append(active.active.phase)
        if mode == 'timeout': await asyncio.sleep(1)
        if mode == 'exception': raise OSError('private credential must not escape')
        if mode == 'cancel': raise asyncio.CancelledError()
        return {'passed': True}
    worker = VerificationWorker(jobs, {phase: handler for phase in PHASES}, timeout=0.02)
    expected = asyncio.CancelledError if mode == 'cancel' else CommerceFailure
    with pytest.raises(expected) as failure: await worker.run_step(job.project_id, job.id)
    assert 'private credential' not in str(failure.value)
    saved = jobs.read(job.project_id, job.id)
    assert saved.state == 'NEEDS_RECONCILIATION' and saved.active.phase == 'reference'
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    assert calls == ['reference']


def test_worker_rejects_incomplete_configuration_before_claim(staging_source_inputs):
    from muse.commerce.verification_worker import VerificationWorker
    jobs, job = reserve(staging_source_inputs)
    with pytest.raises(CommerceFailure): VerificationWorker(jobs, {})
    assert jobs.read(job.project_id, job.id) == job


@pytest.mark.asyncio
async def test_default_worker_allows_bounded_multi_operation_staging(staging_source_inputs, monkeypatch):
    import asyncio

    from muse.commerce.verification_jobs import PHASES
    from muse.commerce.verification_worker import VerificationWorker
    jobs, job = reserve(staging_source_inputs)
    async def handler(active):
        return digest(['private-test-receipt', active.active.phase])
    observed = []
    original = asyncio.wait_for
    async def wait_for(awaitable, *, timeout):
        observed.append(timeout)
        return await original(awaitable, timeout=timeout)
    monkeypatch.setattr(asyncio, 'wait_for', wait_for)
    worker = VerificationWorker(jobs, {phase: handler for phase in PHASES})
    for _ in range(3):
        await worker.run_step(job.project_id, job.id)
    assert observed == [180, 180, 600]
