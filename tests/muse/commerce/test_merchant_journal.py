import copy
import hashlib
import io
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import text

from muse.commerce.code_bridge import ThemeCodeBridge, load_captured_code
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.media import MediaRepository
from muse.commerce.models import VerificationReport
from muse.commerce.repository import digest, encode
from muse.commerce_connector.media import MediaPayload, prepare_media_operation
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_code_bridge import developer
from tests.muse.commerce.test_release_approval import send_fence
from tests.muse.commerce.test_site_release_steps import outcome


@pytest.fixture
def merchant_review(workflow):
    return make_merchant_review(workflow)


def make_merchant_review(workflow, mode='stocked'):
    from muse.commerce.merchant_release import prepare_merchant_release
    service, runtime, original, worker = workflow
    repo = service.repo; root = runtime.get(original.steps[0].task_id)
    runtime.control(root.id, 'cancel', expected_revision=root.revision)
    project = repo.get_project(original.project_id); context = repo.get_context(project.id, 'staging')
    raw = context.snapshot.model_dump(mode='json')
    raw['theme_identity'].update(effective_templates=[], global_styles={'styles': {}}, owned_navigation={'items': []})
    snapshot = normalize_snapshot(raw, project.id, 'staging')
    repo.save_context(project.id, 'stage', snapshot, context.capabilities, project.revision)
    project = repo.get_project(project.id)
    data = io.BytesIO(); Image.new('RGB', (4, 3), 'blue').save(data, format='PNG')
    image = MediaRepository(repo).upload(project.id, 'cup.png', 'image/png', data.getvalue(), 'cup-image', project.revision)
    imported = repo.import_products(project.id,
        'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,10.00,USD,' + ('0' if mode == 'zero' else '3') + ',,,cup.png\n',
        'merchant-products', project.revision, media_ids=[image.id])
    plan = service.create_workflow(project.id, 'build_site', 'Build Image Store', 'merchant-workflow', project.revision,
        import_id=None if mode == 'empty' else imported.id, max_requests=8)
    bridge = ThemeCodeBridge(developer((service, runtime, plan, worker)))
    bridge.seal(bridge.read('style.css')['draft_hash'])
    plan = repo.get_plan(plan.id, project_id=project.id)
    for step in plan.steps: step.status, step.output_hash = 'SUCCEEDED', digest(['explicit-unit-role-output', step.id])
    plan = repo.save_plan(plan.model_copy(update={'state': 'REVIEW_REQUIRED'}), plan.revision)
    code = load_captured_code(repo, plan)
    connection = WordPressConnection('stage', project.id, 'staging', project.environment_refs[0].public_url, 'service', 'fixture')
    proofs = {}
    for name, identity in [*([] if mode == 'empty' else [('sku', 'cup')]), *[('slug', page.slug) for page in plan.blueprint.pages if page.kind != 'product']]:
        key = ('sku:' if name == 'sku' else 'page-slug:') + hashlib.sha256(identity.encode()).hexdigest()
        state = {name: identity, 'exists': False}
        proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    state = {'sha256': image.image.sha256, 'exists': False}; key = 'media-sha256:' + image.image.sha256
    proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    payload = MediaPayload.model_validate(prepare_media_operation(repo, project.id, image.id, proofs[key], 'media').payload)
    if mode == 'empty': proofs.pop(key)
    intent = prepare_merchant_release(project, plan, project.environment_refs[0], snapshot, code, proofs, [] if mode == 'empty' else [payload], connection=connection)
    report = VerificationReport(id='unit-merchant-verification', changeset_digest=intent.digest, code_revision=plan.code_revision,
        snapshot_hash=plan.snapshot_hash, passed=True, checks=[{'name': name, 'passed': True} for name in
            ['os_boundary', 'pages', 'layout_desktop', 'layout_tablet', 'layout_mobile', 'links', 'product_facts', 'buyer_flow', 'media']],
        evidence_refs=['explicit-unit-fixture-not-linux-evidence'])
    proof = {'report': report.model_dump(mode='json'), 'target': intent.target.model_dump(mode='json'),
        'source_digest': code.source_digest, 'package_sha256': code.package.package_sha256}
    with repo.db.transaction() as conn:
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'trusted_merchant_verification',:digest,:data)"),
            {'id': report.id, 'project': project.id, 'plan': plan.id, 'digest': digest(proof), 'data': encode(proof)})
    return repo, project, plan, intent, report.id, connection, [1000.0], proofs


def merchant_journal(fixture, tmp_path):
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    from muse.commerce.merchant_journal import MerchantReleaseJournal
    repo, project, plan, intent, evidence, connection, clock, _proofs = fixture
    approvals = MerchantReleaseApprovalRepository(repo, clock=lambda: clock[0])
    approvals.stage_review(intent, evidence, connection=connection, expected_plan_revision=plan.revision)
    grant = approvals.approve(intent.digest, expected_plan_revision=plan.revision)
    ledger = OperationLedger(tmp_path / 'merchant-ledger.sqlite')
    ledger.bind_target(project.id, connection.connection_id, connection.environment, connection.base_url)
    return MerchantReleaseJournal(approvals, ledger), grant


def test_merchant_approved_images_and_all_eighteen_effects_survive_restart(merchant_review, tmp_path):
    from muse.commerce.merchant_journal import MerchantReleaseJournal
    journal, grant = merchant_journal(merchant_review, tmp_path)
    repo, project, plan, intent, _evidence, connection, _clock, proofs = merchant_review
    snapshot = intent.initial_snapshot; code = journal.approvals.frozen_code(intent)
    for index in range(len(intent.steps)):
        attempt = journal.prepare(grant.id, connection, snapshot, proofs)
        assert attempt.index == index
        send_fence(journal, attempt, connection)
        done, snapshot = outcome(intent, connection, code, SimpleNamespace(operation=attempt.operation), snapshot, proofs)
        journal.ledger.confirm(project.id, connection.connection_id, connection.environment, attempt.operation.operation_id,
            operation_digest=done.receipt.operation_digest, succeeded=True, fingerprint=done.receipt.fingerprint)
        result = journal.record_success(attempt.id, connection, done, proofs)
        assert result.effect_verified and result.state == 'SUCCEEDED'
        journal = MerchantReleaseJournal(journal.approvals, journal.ledger)
    assert len(journal.history(grant.id, connection)) == 18
    assert journal.progress(grant.id, connection)['status'] == 'consumed'
    assert repo.get_plan(plan.id, project_id=project.id).state == 'SUCCEEDED'


@pytest.mark.parametrize('mode', ['unknown', 'revoked_late', 'edited_image'])
def test_merchant_unknown_or_changed_image_cannot_authorize_next_business_step(merchant_review, tmp_path, mode):
    journal, grant = merchant_journal(merchant_review, tmp_path)
    _repo, project, _plan, intent, _evidence, connection, _clock, proofs = merchant_review
    attempt = journal.prepare(grant.id, connection, intent.initial_snapshot, proofs)
    send_fence(journal, attempt, connection)
    if mode == 'unknown':
        assert journal.prepare(grant.id, connection, intent.initial_snapshot, proofs).state == 'NEEDS_RECONCILIATION'
        return
    if mode == 'revoked_late': journal.approvals.revoke(grant.id, project_id=project.id)
    done, after = outcome(intent, connection, journal.approvals.frozen_code(intent), SimpleNamespace(operation=attempt.operation),
        intent.initial_snapshot, proofs)
    if mode == 'edited_image':
        proofs = copy.deepcopy(proofs)
        proofs[attempt.operation.resource_key]['state']['attachment']['alt'] = 'Merchant changed'
        proofs[attempt.operation.resource_key]['fingerprint'] = digest(proofs[attempt.operation.resource_key]['state'])
    journal.ledger.confirm(project.id, connection.connection_id, connection.environment, attempt.operation.operation_id,
        operation_digest=done.receipt.operation_digest, succeeded=True, fingerprint=done.receipt.fingerprint)
    result = journal.record_success(attempt.id, connection, done, proofs)
    assert result.state == 'SUCCEEDED'
    assert result.effect_verified is (mode == 'revoked_late')
    with pytest.raises(CommerceFailure): journal.prepare(grant.id, connection, after, proofs)
