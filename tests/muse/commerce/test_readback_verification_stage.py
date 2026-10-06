"""Readback stage contracts, with explicit simulated CMS and browser capture."""
# ruff: noqa: F811
import hashlib
import io

import httpx
import pytest
from PIL import Image

from muse.commerce.errors import CommerceFailure
from muse.commerce.preview import PreviewFrame, StagePreviewCapture
from muse.commerce.repository import digest
from tests.muse.commerce.test_buyer_verification_stage import setup as buyer_setup
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401


async def setup(inputs, tmp_path, monkeypatch, *, failed=False):
    from muse.commerce import readback_verification_stage as module
    jobs, job, buyer, worker, _calls = await buyer_setup(inputs, tmp_path)
    await worker.run_step(job.project_id, job.id)
    grant = buyer.source.source(job.project_id, job.id, staged=True)
    connection = buyer.source._connection(jobs.read(job.project_id, job.id))
    intent, history = buyer.source.sources.verification_source(grant.id, connection)
    remote = {'snapshot': history[-1].snapshot.model_dump(mode='json'), 'proofs': {}, 'captures': 0}
    for item in history:
        if item.proof: remote['proofs'][item.proof['resource_key']] = item.proof

    def transport(request):
        assert request.method == 'GET'
        if request.url.path.endswith('/snapshot'): return httpx.Response(200, json=remote['snapshot'])
        return httpx.Response(200, json=remote['proofs']['media-sha256:' + request.url.params['media_sha256']])

    async def capture(plan, code, snapshot, target, **kwargs):
        remote['captures'] += 1
        assert snapshot.products and target == connection and kwargs['images'] == intent.images
        frames = []
        for width in (390, 768, 1440):
            out = io.BytesIO(); Image.new('RGB', (width, 900), 'white').save(out, format='PNG')
            content = out.getvalue()
            for kind in ['home', 'shop', 'cart', 'checkout', 'about', 'contact']:
                frames.append(PreviewFrame(kind, width, 900, hashlib.sha256(content).hexdigest(), content, None))
            skus = [product.sku for product in plan.products]
            if kwargs.get('fixture'): skus.append(kwargs['fixture'].draft.sku)
            for sku in skus:
                frames.append(PreviewFrame('product', width, 900, hashlib.sha256(content).hexdigest(), content, sku))
        checks = dict.fromkeys(['pages', 'layout_desktop', 'layout_tablet', 'layout_mobile', 'links'], True)
        if failed: checks['links'] = False
        return StagePreviewCapture(code.source_digest, digest(snapshot), target.connection_id, target.base_url,
            tuple(frames), checks, ('EXTERNAL_RESOURCE_BLOCKED',) if failed else (), not failed)

    monkeypatch.setattr(module, 'capture_staging_preview', capture)
    browser = module.ReadbackVerificationStage(jobs, buyer.source, 'browser', transport=httpx.MockTransport(transport))
    facts = module.ReadbackVerificationStage(jobs, buyer.source, 'facts', transport=httpx.MockTransport(transport))
    worker.handlers.update(browser=browser, facts=facts)
    return jobs, job, browser, facts, worker, remote


@pytest.mark.asyncio
async def test_browser_and_facts_collect_bound_evidence_without_merchant_pass_report(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, browser, facts, worker, _remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    saved = await worker.run_step(job.project_id, job.id)
    assert len(saved.completed) == 5 and browser.evidence(job.project_id, job.id)['preview_id']
    saved = await worker.run_step(job.project_id, job.id)
    assert saved.state == 'COLLECTED' and facts.evidence(job.project_id, job.id)['facts']['passed']
    assert jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'") == []


@pytest.mark.asyncio
async def test_failed_browser_retains_diagnostics_but_cannot_finish_phase(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, _browser, _facts, worker, _remote = await setup(staging_source_inputs, tmp_path, monkeypatch, failed=True)
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'
    assert jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='commerce_preview'")
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='verification_readback'")


@pytest.mark.asyncio
async def test_lost_browser_phase_receipt_reconciles_saved_capture_without_browser_replay(staging_source_inputs, tmp_path, monkeypatch):
    _jobs, job, browser, _facts, worker, remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    async def lost(claim):
        await browser(claim)
        raise TimeoutError('saved capture reply lost')
    worker.handlers['browser'] = lost
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    saved = await browser.reconcile(job.project_id, job.id)
    assert len(saved.completed) == 5 and remote['captures'] == 1


@pytest.mark.asyncio
async def test_facts_reject_price_changed_after_browser_capture(staging_source_inputs, tmp_path, monkeypatch):
    jobs, job, _browser, _facts, worker, remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    await worker.run_step(job.project_id, job.id)
    remote['snapshot']['products'][0]['price'] = '99.00'
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'


@pytest.mark.asyncio
async def test_browser_reconcile_refuses_corrupt_saved_screenshot(staging_source_inputs, tmp_path, monkeypatch):
    from sqlalchemy import text
    jobs, job, browser, _facts, worker, remote = await setup(staging_source_inputs, tmp_path, monkeypatch)
    async def lost(claim):
        await browser(claim)
        raise TimeoutError('lost after capture')
    worker.handlers['browser'] = lost
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    with jobs.db.transaction() as conn:
        conn.execute(text("UPDATE commerce_artifacts SET digest=:bad WHERE project_id=:project AND kind='commerce_preview_frame'"),
            {'bad': '0' * 64, 'project': job.project_id})
    with pytest.raises(CommerceFailure): await browser.reconcile(job.project_id, job.id)
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION' and remote['captures'] == 1
