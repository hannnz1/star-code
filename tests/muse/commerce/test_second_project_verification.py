"""Restore contract integration; Docker, CMS and browser effects are simulated."""
import base64
import hashlib

import pytest

from muse.commerce.code_bridge import ThemeCodeBridge, load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.export import ProjectExporter
from muse.commerce.media import MediaRepository
from muse.commerce.merchant_release import prepare_merchant_release
from muse.commerce.models import EnvironmentRef
from muse.commerce.repository import digest
from muse.commerce.restore import ProjectRestorer
from muse.commerce_connector.media import MediaPayload, prepare_media_operation
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_code_bridge import developer
from tests.muse.commerce.test_merchant_journal import make_merchant_review
from tests.muse.commerce.test_trusted_verifier import ready


async def test_second_project_recaptures_restored_theme_and_requires_its_own_review(workflow, tmp_path, monkeypatch):
    service, runtime, _original, worker = workflow
    repo, first, old_plan, old_intent, old_report, old_connection, clock, _ = make_merchant_review(workflow)
    bundle = ProjectExporter(repo).download_project(first.id, first.revision)
    restored = ProjectRestorer(repo).restore(first.workspace_id, base64.b64decode(bundle.archive_base64), 'second-shop')
    second = restored.project
    assert second.environment_refs == [] and repo.list_plans(second.id) == []
    assert restored.deployment_verified is False and restored.requires_new_approval
    source = ProjectRestorer(repo).theme_source(second.id, restored.theme_source_ids[0])
    old_code = load_captured_code(repo, old_plan)
    assert base64.b64decode(source.archive_base64) == old_code.archive
    second = repo.attach_connection(second.id, EnvironmentRef(id='second-stage', connector_ref='second-stage',
        project_id=second.id, environment='staging', public_url='https://second-shop.test'), 'second-bind', second.revision)
    context = repo.get_context(first.id, 'staging')
    repo.save_context(second.id, 'second-stage', context.snapshot.model_copy(update={'project_id': second.id}),
        context.capabilities, second.revision)
    second = repo.get_project(second.id)
    imported_source = repo.list_product_imports(second.id)[0]
    with pytest.raises(CommerceFailure):
        service.create_workflow(second.id, 'build_site', 'Restore', 'stale-import', second.revision,
            import_id=imported_source.id, theme_source_id=restored.theme_source_ids[0])
    media = MediaRepository(repo).list(second.id)[0]
    imported = repo.import_products(second.id,
        'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,10.00,USD,3,,,cup.png\n',
        'confirm-restored-facts', second.revision, media_ids=[media.id])
    assert imported.result.drafts == imported_source.result.drafts
    plan = service.create_workflow(second.id, 'build_site', 'Restore', 'new-workflow', second.revision,
        import_id=imported.id, theme_source_id=restored.theme_source_ids[0], max_requests=8)
    bridge = ThemeCodeBridge(developer((service, runtime, plan, worker)))
    bridge.seal(bridge.read('style.css')['draft_hash'])
    plan = repo.get_plan(plan.id, project_id=second.id)
    for step in plan.steps:
        step.status, step.output_hash = 'SUCCEEDED', digest(['explicit-unit-role', step.id])
    plan = repo.save_plan(plan.model_copy(update={'state': 'VERIFYING'}), plan.revision)
    captured = load_captured_code(repo, plan)
    assert captured.archive == old_code.archive and captured.project_id != old_code.project_id
    connection = WordPressConnection('second-stage', second.id, 'staging', 'https://second-shop.test', 'fixture', 'fixture')
    proofs = {}
    for name, identity in [('sku', 'cup'), *[('slug', p.slug) for p in plan.blueprint.pages if p.kind != 'product']]:
        key = ('sku:' if name == 'sku' else 'page-slug:') + hashlib.sha256(identity.encode()).hexdigest()
        state = {name: identity, 'exists': False}
        proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    key = 'media-sha256:' + media.image.sha256
    state = {'sha256': media.image.sha256, 'exists': False}
    proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    payload = MediaPayload.model_validate(prepare_media_operation(repo, second.id, media.id, proofs[key], 'media').payload)
    intent = prepare_merchant_release(second, plan, second.environment_refs[0], context.snapshot.model_copy(
        update={'project_id': second.id}), captured, proofs, [payload], connection=connection)
    inputs = repo, second, plan, intent, connection, clock, proofs
    _jobs, job, verifier, connection, _, _, _ = await ready(inputs, tmp_path, monkeypatch)
    result = await verifier.request_review(second.id, job.id, connection=connection)
    assert result.report.passed and result.report.id != old_report
    assert result.intent.digest != old_intent.digest
    assert result.intent.target.connector_ref == 'second-stage'
    assert result.intent.target.public_url != old_connection.base_url
    assert repo.get_plan(plan.id, project_id=second.id).state == 'REVIEW_REQUIRED'
    assert repo.get_plan(old_plan.id, project_id=first.id).state == 'REVIEW_REQUIRED'
    assert not repo.db.rows("SELECT id FROM commerce_artifacts WHERE project_id=:id AND kind='merchant_release_grant'", {'id': second.id})
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    approvals = MerchantReleaseApprovalRepository(repo, clock=lambda: clock[0])
    with pytest.raises(CommerceFailure):
        approvals.approve(old_intent.digest, expected_plan_revision=plan.revision)
    reviewed = repo.get_plan(plan.id, project_id=second.id)
    grant = approvals.approve(result.intent.digest, expected_plan_revision=reviewed.revision)
    assert grant.project_id == second.id and grant.intent_digest == result.intent.digest
    assert approvals.load(grant.id, connection).intent == result.intent
    with pytest.raises(CommerceFailure):
        approvals.load(grant.id, old_connection)
