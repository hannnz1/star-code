import hashlib

import pytest
from sqlalchemy import text

from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import VerificationReport
from muse.commerce.repository import digest, encode
from tests.muse.commerce.test_code_bridge import developer


@pytest.fixture
def site_review(workflow):
    from muse.commerce.code_bridge import ThemeCodeBridge
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.site_release import prepare_site_release
    from muse.commerce_connector.wordpress import WordPressConnection
    service, runtime, original, worker = workflow
    repo = service.repo
    root = runtime.get(original.steps[0].task_id)
    runtime.control(root.id, 'cancel', expected_revision=root.revision)
    project = repo.get_project(original.project_id)
    context = repo.get_context(project.id, 'staging')
    raw = context.snapshot.model_dump(mode='json')
    raw['theme_identity'].update(effective_templates=[], global_styles={'styles': {}}, owned_navigation={'items': []})
    snapshot = normalize_snapshot(raw, project.id, 'staging')
    repo.save_context(project.id, 'stage', snapshot, context.capabilities, project.revision)
    project = repo.get_project(project.id)
    imported = repo.import_products(project.id,
        'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,10.00,USD,3,,,\n', 'site-products', project.revision)
    plan = service.create_workflow(project.id, 'build_site', 'Build Cup Store', 'site-workflow', project.revision,
                                   import_id=imported.id, max_requests=8)
    bridge = ThemeCodeBridge(developer((service, runtime, plan, worker)))
    bridge.seal(bridge.read('style.css')['draft_hash'])
    plan = repo.get_plan(plan.id, project_id=project.id)
    for step in plan.steps:
        step.status, step.output_hash = 'SUCCEEDED', digest(['explicit-fixture-output', step.id])
    plan = repo.save_plan(plan.model_copy(update={'state': 'REVIEW_REQUIRED'}), plan.revision)
    code = load_captured_code(repo, plan)
    connection = WordPressConnection('stage', project.id, 'staging', project.environment_refs[0].public_url, 'service', 'fixture')
    clock = [1000.0]
    proofs = {}
    for name, identity in [('sku', 'cup'), *[('slug', page.slug) for page in plan.blueprint.pages if page.kind != 'product']]:
        key = ('sku:' if name == 'sku' else 'page-slug:') + hashlib.sha256(identity.encode()).hexdigest()
        state = {name: identity, 'exists': False}
        proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    intent = prepare_site_release(project, plan, project.environment_refs[0], snapshot, code, proofs, connection=connection)
    report = VerificationReport(id='fixture-site-verification', changeset_digest=intent.digest, code_revision=plan.code_revision,
        snapshot_hash=plan.snapshot_hash, passed=True, checks=[{'name': name, 'passed': True} for name in
            ['os_boundary', 'pages', 'layout_desktop', 'layout_tablet', 'layout_mobile', 'links', 'product_facts', 'buyer_flow', 'media']],
        evidence_refs=['explicit-unit-fixture-not-real-linux-evidence'])
    proof = {'report': report.model_dump(mode='json'), 'target': intent.target.model_dump(mode='json'),
             'source_digest': code.source_digest, 'package_sha256': code.package.package_sha256}
    # Unit evidence only; a private trusted producer is still required in real use.
    with repo.db.transaction() as conn:
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'trusted_site_verification',:digest,:data)"),
            {'id': report.id, 'project': project.id, 'plan': plan.id, 'digest': digest(proof), 'data': encode(proof)})
    return repo, project, plan, intent, report.id, connection, clock


def store(fixture):
    from muse.commerce.site_approval import SiteReleaseApprovalRepository
    return SiteReleaseApprovalRepository(fixture[0], clock=lambda: fixture[6][0])


def approve(fixture):
    _, _, plan, intent, evidence, connection, _ = fixture
    repository = store(fixture)
    repository.stage_review(intent, evidence, connection=connection, expected_plan_revision=plan.revision)
    return repository.approve(intent.digest, expected_plan_revision=plan.revision)


def test_site_approval_persists_source_and_idempotent_grant_without_extending_expiry(site_review):
    from muse.commerce.repository import CommerceRepository
    from muse.commerce.site_approval import SiteReleaseApprovalRepository
    from muse.tasks.repository import TaskRepository
    repo, project, plan, intent, _, connection, clock = site_review
    grant = approve(site_review)
    clock[0] = 1100
    restarted = SiteReleaseApprovalRepository(CommerceRepository(TaskRepository(repo.db.engine.url.database)), clock=lambda: clock[0])
    assert restarted.approve(intent.digest, expected_plan_revision=plan.revision) == grant
    assert grant.approved_at == 1000 and grant.expires_at == 2800
    assert restarted.start(grant.id, connection).intent == intent
    assert repo.get_plan(plan.id, project_id=project.id).state == 'PUBLISHING'


@pytest.mark.parametrize('change', ['expiry', 'revoked', 'cancel', 'source', 'report', 'tablet_missing', 'target', 'old_evidence'])
def test_site_approval_rejects_stale_source_and_incomplete_verification(site_review, change):
    repo, project, plan, intent, evidence, connection, clock = site_review
    repository = store(site_review)
    if change in {'tablet_missing', 'old_evidence'}:
        with repo.db.transaction() as conn:
            row = conn.execute(text('SELECT data FROM commerce_artifacts WHERE id=:id'), {'id': evidence}).scalar()
            import json
            proof = json.loads(row)
            if change == 'tablet_missing':
                proof['report']['checks'] = [item for item in proof['report']['checks'] if item['name'] != 'layout_tablet']
                conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                             {'data': encode(proof), 'digest': digest(proof), 'id': evidence})
            else:
                conn.execute(text("UPDATE commerce_artifacts SET kind='trusted_product_verification' WHERE id=:id"), {'id': evidence})
        with pytest.raises(CommerceFailure):
            repository.stage_review(intent, evidence, connection=connection, expected_plan_revision=plan.revision)
        return
    grant = approve(site_review)
    if change == 'expiry': clock[0] = 2800
    elif change == 'revoked': repository.revoke(grant.id, project_id=project.id)
    elif change in {'cancel', 'source'}:
        current = repo.get_plan(plan.id, project_id=project.id)
        if change == 'cancel': current.state = 'CANCELLED'
        else: current.blueprint.pages[0].title = 'Unapproved'
        repo.save_plan(current, current.revision)
    elif change == 'report':
        with repo.db.transaction() as conn:
            conn.execute(text('UPDATE commerce_artifacts SET digest=:hash WHERE id=:id'), {'hash': 'f' * 64, 'id': evidence})
    else:
        connection = connection.__class__(connection.connection_id, connection.project_id, 'staging', 'https://other.test', 'scope', 'fixture')
    with pytest.raises(CommerceFailure): repository.load(grant.id, connection)
