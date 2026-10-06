"""Private runtime integration, with explicitly simulated platform producers."""
# ruff: noqa: F811
import asyncio

import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_readback_verification_stage import setup
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401


def runtime(worker):
    from muse.commerce.verification_runtime import VerificationRuntime
    return VerificationRuntime(worker.jobs, **{
        name: handler for name, handler in worker.handlers.items()
    })


@pytest.mark.asyncio
async def test_runtime_advances_one_fixed_phase_and_never_grants_review(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, _browser, _facts, worker, remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    runner = runtime(worker)
    stop = asyncio.Event()
    stop.set()
    await runner.run(job.project_id, stop)
    assert remote['captures'] == 0
    first = await runner.run_once(job.project_id)
    assert len(first) == 1 and len(first[0].completed) == 5
    second = await runner.run_once(job.project_id)
    assert second[0].state == 'COLLECTED' and remote['captures'] == 1
    assert await runner.run_once(job.project_id) == []
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")


@pytest.mark.asyncio
async def test_failed_runtime_phase_is_not_replayed_on_poll(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, _browser, _facts, worker, remote = await setup(staging_source_inputs, tmp_path, monkeypatch, failed=True)
    runner = runtime(worker)
    results = await runner.run_once(job.project_id)
    assert results[0].state == 'NEEDS_RECONCILIATION'
    assert await runner.run_once(job.project_id) == [] and remote['captures'] == 1
    assert jobs.read(job.project_id, job.id).active.phase == 'browser'


@pytest.mark.asyncio
async def test_startup_accounts_interrupted_claim_without_effects(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, _browser, _facts, worker, remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    saved = jobs.read(job.project_id, job.id)
    claimed = jobs.claim(job.project_id, job.id, saved.revision, 'browser')
    runner = runtime(worker)
    recovered = runner.recover_interrupted(job.project_id)
    assert recovered[0].active == claimed.active and recovered[0].state == 'NEEDS_RECONCILIATION'
    assert await runner.run_once(job.project_id) == [] and remote['captures'] == 0
    assert runner.recover_interrupted(job.project_id) == []


@pytest.mark.asyncio
async def test_runtime_refuses_wrong_phase_or_arbitrary_producer(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce.verification_runtime import VerificationRuntime
    jobs, _job, _browser, _facts, worker, _remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    handlers = dict(worker.handlers)
    handlers['facts'] = handlers['browser']
    with pytest.raises(CommerceFailure): VerificationRuntime(jobs, **handlers)
    handlers['facts'] = lambda claim: '0' * 64
    with pytest.raises(CommerceFailure): VerificationRuntime(jobs, **handlers)
    runner = runtime(worker)
    with pytest.raises(CommerceFailure): await runner.run(_job.project_id, asyncio.Event(), poll_seconds=float('nan'))


@pytest.mark.asyncio
async def test_cancelling_host_loop_keeps_inflight_claim_unknown(staging_source_inputs, tmp_path, monkeypatch):
    from muse.commerce import readback_verification_stage as module
    jobs, job, _browser, _facts, worker, _remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    entered = asyncio.Event()
    async def interrupted(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(module, 'capture_staging_preview', interrupted)
    runner = runtime(worker)
    task = asyncio.create_task(runner.run(job.project_id, asyncio.Event()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'
    assert await runner.run_once(job.project_id) == []
