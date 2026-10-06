"""Source-stage integration with simulated CMS and explicit simulated Docker probes."""
# ruff: noqa: F811
import hashlib

import httpx
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce.staging_source import StagingSourceRepository
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_reference_verification_stage import setup
from tests.muse.commerce.test_staging_source import (  # noqa: F401
    ExplicitFixtureSession,
    staging_source_inputs,
)


async def prepared(inputs, tmp_path, mode=None):
    from muse.commerce.source_capture_stage import SourceCaptureStage
    jobs, job, runner, reference, worker = setup(inputs, tmp_path)
    await worker.run_step(job.project_id, job.id)
    _repo, project, _plan, original, _connection, clock, _proofs = inputs
    target = reference.targets.target(job.project_id, job.plan_id)
    connection = WordPressConnection(target.connector_ref, project.id, 'staging', target.public_url,
        'private-service', 'fixture-secret', approved_development_http=True)
    runner._connection = lambda ref: connection
    requests, sessions = [], []

    def respond(request):
        requests.append(request)
        assert request.method == 'GET'
        if request.url.path.endswith('/snapshot'):
            raw = original.initial_snapshot.model_dump(mode='json')
            if not any(product.stock >= 1 for product in original.products):
                raw['products'].append({'id': 900001, 'sku': 'MUSE-PROBE-' + target.connector_ref[4:],
                    'name': 'MUSE disposable purchase probe', 'price': '12.50', 'regular_price': '12.50',
                    'stock_quantity': 3, 'status': 'publish', 'description': '', 'categories': [], 'category_ids': [],
                    'image_id': 0, 'gallery_image_ids': [], 'type': 'simple', 'manage_stock': True,
                    'sale_price': '', 'backorders': 'no'})
            if mode == 'conflict':
                raw['theme_identity']['stylesheet'] = 'foreign-theme'
            return httpx.Response(200, json=raw)
        param, value = next(iter(request.url.params.items()))
        name = {'sku': 'sku', 'page_slug': 'slug', 'media_sha256': 'sha256'}[param]
        prefix = {'sku': 'sku:', 'page_slug': 'page-slug:', 'media_sha256': 'media-sha256:'}[param]
        value = value.casefold() if name == 'sku' else value
        key = prefix + (value if name == 'sha256' else hashlib.sha256(value.encode()).hexdigest())
        state = {name: value, 'exists': False}
        return httpx.Response(200, json={'resource_key': key, 'state': state, 'fingerprint': digest(state)})

    def boundary():
        session = ExplicitFixtureSession(tmp_path / ('capture-' + str(len(sessions))))
        sessions.append(session)
        if mode == 'cancel':
            original_start = session.start
            async def cancel(files):
                await original_start(files)
                current = jobs.read(job.project_id, job.id)
                jobs.cancel(job.project_id, job.id, current.revision)
            session.start = cancel
        return session

    stage = SourceCaptureStage(jobs, reference.service, boundary,
        transport=httpx.MockTransport(respond), clock=lambda: clock[0])
    worker.handlers['source_capture'] = stage
    return jobs, job, stage, worker, connection, requests, sessions


@pytest.mark.asyncio
async def test_capture_stage_reads_fixed_target_captures_code_and_accounts_private_grant(staging_source_inputs, tmp_path):
    jobs, job, stage, worker, connection, requests, sessions = await prepared(staging_source_inputs, tmp_path)
    saved = await worker.run_step(job.project_id, job.id)
    assert [item.phase for item in saved.completed] == ['reference', 'source_capture']
    grant = stage.source(job.project_id, job.id)
    assert StagingSourceRepository(jobs.repo, clock=stage.clock).load(grant.id, connection).intent.target.connector_ref == connection.connection_id
    assert len(sessions) == 1 and sessions[0].closed
    assert len(requests) == 9  # snapshot, six page identities, one SKU, one image
    assert all(str(req.url).startswith(connection.base_url + '/') for req in requests)
    assert jobs.repo.get_project(job.project_id) == staging_source_inputs[1]
    assert jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'") == []


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['cancel', 'conflict'])
async def test_capture_stage_rejects_cancel_or_foreign_theme_without_preview_grant(staging_source_inputs, tmp_path, mode):
    jobs, job, _stage, worker, _connection, _requests, sessions = await prepared(staging_source_inputs, tmp_path, mode)
    with pytest.raises(CommerceFailure):
        await worker.run_step(job.project_id, job.id)
    assert jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='staging_source_grant'") == []
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'
    assert all(session.closed for session in sessions)


@pytest.mark.asyncio
async def test_lost_capture_receipt_recovers_existing_grant_without_capture_or_http_replay(staging_source_inputs, tmp_path):
    _jobs, job, stage, worker, _connection, requests, sessions = await prepared(staging_source_inputs, tmp_path)
    async def lost(claim):
        await stage(claim)
        raise TimeoutError('reply lost after persisted authorization')
    worker.handlers['source_capture'] = lost
    with pytest.raises(CommerceFailure):
        await worker.run_step(job.project_id, job.id)
    before = len(requests)
    saved = await stage.reconcile(job.project_id, job.id)
    assert len(saved.completed) == 2 and saved.state == 'QUEUED'
    assert len(requests) == before and len(sessions) == 1
    with pytest.raises(CommerceFailure):
        await stage.reconcile(job.project_id, job.id)


@pytest.mark.asyncio
async def test_reconcile_missing_capture_never_reauthorizes(staging_source_inputs, tmp_path):
    _jobs, job, stage, worker, _connection, requests, sessions = await prepared(staging_source_inputs, tmp_path)
    async def unavailable(claim):
        raise TimeoutError('before authorization')
    worker.handlers['source_capture'] = unavailable
    with pytest.raises(CommerceFailure):
        await worker.run_step(job.project_id, job.id)
    with pytest.raises(CommerceFailure):
        await stage.reconcile(job.project_id, job.id)
    assert requests == [] and sessions == []


@pytest.mark.asyncio
async def test_capture_stage_rejects_wrong_connection_before_http(staging_source_inputs, tmp_path):
    _jobs, job, stage, worker, connection, requests, sessions = await prepared(staging_source_inputs, tmp_path)
    from dataclasses import replace
    stage.service.runner._connection = lambda ref: replace(connection, base_url='http://127.0.0.1:63670')
    with pytest.raises(CommerceFailure):
        await worker.run_step(job.project_id, job.id)
    assert requests == [] and sessions == []
