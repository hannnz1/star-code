"""Production broker integration over an explicitly simulated remote CMS."""
# ruff: noqa: F811
import copy
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation
from muse.commerce.staging_journal import StagingReleaseJournal
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.commerce_connector.staging_authorization import StagingReleaseAuthority
from muse.commerce_connector.staging_publisher import StagingReleasePublisher
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_site_release_steps import outcome
from tests.muse.commerce.test_source_capture_stage import prepared
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401


async def setup(inputs, tmp_path, *, lost_index=None, cancel_index=None):
    from muse.commerce.staging_verification_stage import StagingVerificationStage
    jobs, job, source, worker, connection, _, _ = await prepared(inputs, tmp_path)
    await worker.run_step(job.project_id, job.id)
    grant = source.source(job.project_id, job.id)
    intent = source.sources.load(grant.id, connection).intent
    code = source.sources.frozen_code(intent)
    remote = {'snapshot': intent.initial_snapshot.model_dump(mode='json'), 'proofs': copy.deepcopy(inputs[-1]),
        'posts': 0, 'calls': [], 'receipts': {}}

    def transport(request):
        remote['calls'].append(request.method)
        if request.url.path.endswith('/capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': sorted(StagingReleasePublisher.required_operations | {step.kind for step in intent.steps})})
        if request.url.path.endswith('/snapshot'):
            return httpx.Response(200, json=remote['snapshot'])
        if request.url.path.endswith('/resources'):
            params = request.url.params
            if 'media_sha256' in params: key = 'media-sha256:' + params['media_sha256']
            elif 'page_slug' in params: key = 'page-slug:' + hashlib.sha256(params['page_slug'].encode()).hexdigest()
            else: key = 'sku:' + hashlib.sha256(params['sku'].casefold().encode()).hexdigest()
            return httpx.Response(200, json=remote['proofs'][key])
        if '/receipts/' in request.url.path:
            return httpx.Response(200, json=remote['receipts'][request.url.path.rsplit('/', 1)[1]])
        assert request.method == 'POST'
        operation = ChangeOperation.model_validate(json.loads(request.content)['operation'])
        before = normalize_snapshot(remote['snapshot'], job.project_id, 'staging')
        done, after = outcome(intent, connection, code, SimpleNamespace(operation=operation), before, remote['proofs'])
        remote['snapshot'] = after.model_dump(mode='json')
        remote['receipts'][operation.operation_id] = done.receipt.model_dump(mode='json')
        index = remote['posts']; remote['posts'] += 1
        if index == cancel_index:
            current = jobs.read(job.project_id, job.id)
            jobs.cancel(job.project_id, job.id, current.revision)
        if index == lost_index:
            raise httpx.ReadTimeout('explicit lost CMS reply', request=request)
        return httpx.Response(200, json=done.receipt.model_dump(mode='json'))

    ledger = OperationLedger(tmp_path / 'stage-ledger.sqlite')
    journal = StagingReleaseJournal(source.sources, ledger)
    lock = {'verified': True, 'wordpress': '7.1.2', 'woocommerce': '11.1.2', 'theme': 'muse-storefront',
        'php': '8.4.26', 'database': '11.4.12', 'images': {name: name + '@sha256:' + 'a' * 64
            for name in ('wordpress', 'database', 'cli')}}
    publisher = StagingReleasePublisher(connection, journal, StagingReleaseAuthority(b'x' * 32, clock=source.clock),
        versions_lock=lock, execution_enabled=True, transport=httpx.MockTransport(transport))
    stage = StagingVerificationStage(jobs, source, lambda target: publisher)
    worker.handlers['staging'] = stage
    return jobs, job, stage, worker, remote, intent


@pytest.mark.asyncio
async def test_staging_stage_completes_all_effects_without_merchant_approval(staging_source_inputs, tmp_path):
    jobs, job, _stage, worker, remote, intent = await setup(staging_source_inputs, tmp_path)
    saved = await worker.run_step(job.project_id, job.id)
    assert [receipt.phase for receipt in saved.completed] == ['reference', 'source_capture', 'staging']
    assert remote['posts'] == len(intent.steps) == 18
    assert jobs.repo.get_plan(job.plan_id, project_id=job.project_id).state == 'VERIFYING'
    assert jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'") == []


@pytest.mark.asyncio
async def test_staging_last_lost_reply_reconciles_with_only_gets(staging_source_inputs, tmp_path):
    jobs, job, stage, worker, remote, intent = await setup(staging_source_inputs, tmp_path, lost_index=17)
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'
    remote['calls'].clear()
    saved = await stage.reconcile(job.project_id, job.id)
    assert len(saved.completed) == 3 and remote['posts'] == len(intent.steps)
    assert set(remote['calls']) == {'GET'}


@pytest.mark.asyncio
async def test_staging_partial_reconcile_never_sends_the_remaining_steps(staging_source_inputs, tmp_path):
    jobs, job, stage, worker, remote, _intent = await setup(staging_source_inputs, tmp_path, lost_index=0)
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    remote['calls'].clear()
    with pytest.raises(CommerceFailure): await stage.reconcile(job.project_id, job.id)
    assert remote['posts'] == 1 and set(remote['calls']) == {'GET'}
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'


@pytest.mark.asyncio
async def test_cancel_during_staging_stops_before_second_send(staging_source_inputs, tmp_path):
    jobs, job, _stage, worker, remote, _intent = await setup(staging_source_inputs, tmp_path, cancel_index=0)
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    assert remote['posts'] == 1 and jobs.read(job.project_id, job.id).cancel_requested


@pytest.mark.asyncio
async def test_partial_stage_resume_only_sends_unstarted_steps(staging_source_inputs, tmp_path):
    jobs, job, stage, worker, remote, intent = await setup(staging_source_inputs, tmp_path, lost_index=0)
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    # Resume cannot account an unknown send implicitly.
    with pytest.raises(CommerceFailure): await stage.resume(job.project_id, job.id, jobs.read(job.project_id, job.id).revision)
    assert remote['posts'] == 1
    with pytest.raises(CommerceFailure): await stage.reconcile(job.project_id, job.id)
    revision = jobs.read(job.project_id, job.id).revision
    saved = await stage.resume(job.project_id, job.id, revision)
    assert len(saved.completed) == 3 and remote['posts'] == len(intent.steps)
    with pytest.raises(CommerceFailure): await stage.resume(job.project_id, job.id, revision)
    assert remote['posts'] == len(intent.steps)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['expired', 'cancelled'])
async def test_stage_resume_does_not_renew_expired_or_cancelled_source(staging_source_inputs, tmp_path, change):
    jobs, job, stage, worker, remote, _intent = await setup(staging_source_inputs, tmp_path, lost_index=0)
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    with pytest.raises(CommerceFailure): await stage.reconcile(job.project_id, job.id)
    current = jobs.read(job.project_id, job.id)
    if change == 'expired': staging_source_inputs[-2][0] += 1800
    else: jobs.cancel(job.project_id, job.id, current.revision)
    current = jobs.read(job.project_id, job.id)
    with pytest.raises(CommerceFailure): await stage.resume(job.project_id, job.id, current.revision)
    assert remote['posts'] == 1
