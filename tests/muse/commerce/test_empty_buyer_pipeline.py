"""Empty and zero-stock merchant facts remain unchanged; effects explicitly simulated."""
import pytest

from muse.commerce.preview_repository import PreviewRepository
from tests.muse.commerce.test_merchant_journal import make_merchant_review
from tests.muse.commerce.test_readback_verification_stage import setup
from tests.muse.commerce.test_staging_source import staging_source_inputs


@pytest.mark.parametrize('mode', ['empty', 'zero'])
async def test_disposable_product_buyer_and_screenshots_do_not_change_merchant_facts(workflow, tmp_path, monkeypatch, mode):
    inputs = staging_source_inputs.__wrapped__(make_merchant_review(workflow, mode))
    jobs, job, _browser, _facts, worker, _remote = await setup(inputs, tmp_path, monkeypatch)
    await worker.run_step(job.project_id, job.id)
    saved = await worker.run_step(job.project_id, job.id)
    assert saved.state == 'COLLECTED'
    plan = jobs.repo.get_plan(job.plan_id, project_id=job.project_id)
    assert len(plan.products) == (0 if mode == 'empty' else 1)
    assert all(product.stock == 0 and not product.sku.startswith('MUSE-PROBE-') for product in plan.products)
    preview = PreviewRepository(jobs.repo).latest(job.project_id, job.plan_id, plan.revision)
    assert preview.passed and any(frame.sku and frame.sku.startswith('MUSE-PROBE-') for frame in preview.frames)
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")


@pytest.mark.parametrize('mode', ['empty', 'zero'])
async def test_disposable_product_can_verify_but_is_absent_from_formal_release(workflow, tmp_path, monkeypatch, mode):
    from tests.muse.commerce.test_trusted_verifier import ready
    inputs = staging_source_inputs.__wrapped__(make_merchant_review(workflow, mode))
    jobs, job, verifier, connection, _clock, _remote, _calls = await ready(inputs, tmp_path, monkeypatch)
    result = await verifier.request_review(job.project_id, job.id, connection=connection)
    assert result.report.passed
    assert all(not product.sku.startswith('MUSE-PROBE-') for product in result.intent.products)
    assert len(result.intent.products) == (0 if mode == 'empty' else 1)
    assert jobs.repo.get_plan(job.plan_id, project_id=job.project_id).state == 'REVIEW_REQUIRED'
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")


async def test_changed_disposable_source_cannot_generate_a_report(workflow, tmp_path, monkeypatch):
    import json

    from sqlalchemy import text

    from muse.commerce.errors import CommerceFailure
    from muse.commerce.repository import digest, encode
    from tests.muse.commerce.test_trusted_verifier import ready
    inputs = staging_source_inputs.__wrapped__(make_merchant_review(workflow, 'empty'))
    jobs, job, verifier, connection, _clock, _remote, _calls = await ready(inputs, tmp_path, monkeypatch)
    with jobs.db.transaction() as conn:
        row = conn.execute(text("SELECT id,data FROM commerce_artifacts WHERE kind='buyer_fixture_binding'")).mappings().one()
        value = json.loads(row['data']); value['proof']['product_id'] += 1
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
            {'id': row['id'], 'data': encode(value), 'digest': digest(value)})
    with pytest.raises(CommerceFailure): await verifier.request_review(job.project_id, job.id, connection=connection)
    assert not jobs.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")
