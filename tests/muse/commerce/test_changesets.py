import asyncio
import base64

import pytest

from muse.commerce.approval import ApprovalRepository
from muse.commerce.changesets import create_changeset
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    CommercePlan,
    EnvironmentRef,
    SiteBrief,
    VerificationReport,
)
from muse.commerce.repository import CommerceRepository, digest
from muse.commerce.site import build_site_blueprint
from muse.commerce.theme import build_site_archive, validate_site_archive
from muse.commerce_connector.authorization import ExecutionAuthority
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.commerce_connector.publisher import WordPressPublisher
from muse.commerce_connector.wordpress import WordPressConnection
from muse.tasks.repository import TaskRepository


@pytest.fixture
def source():
    snapshot = normalize_snapshot({
        'pages': [], 'products': [],
        'settings': {'currency': 'USD', 'language': 'en'},
        'theme_identity': {'stylesheet': 'muse-storefront', 'version': '1.0',
                           'effective_templates': [], 'global_styles': {'styles': {}}},
    }, 'shop', 'staging')
    blueprint = build_site_blueprint(SiteBrief(brand_name='Shop', language='en', currency='USD'), snapshot)
    package, archive = build_site_archive(blueprint, [], code_revision='a' * 40)
    plan = CommercePlan(id='plan', project_id='shop', kind='build_site', state='VERIFYING',
                        blueprint=blueprint, code_revision='a' * 40,
                        content_hash=package.content_sha256, snapshot_hash=digest(snapshot))
    return plan, snapshot, package, archive


def test_theme_changeset_binds_exact_archive_and_current_dependencies(source):
    plan, snapshot, package, archive = source
    changeset = create_changeset(plan, snapshot, package)
    assert changeset.environment == 'staging'
    assert changeset.package_hash == package.package_sha256
    assert changeset.content_hash == package.content_sha256
    assert len(changeset.operations) == 1
    operation = changeset.operations[0]
    assert operation.kind == 'install_theme_package'
    assert operation.resource_key == 'theme:muse-storefront'
    assert operation.expected_fingerprint == snapshot.resource_fingerprints['theme']
    assert changeset.resource_preconditions == {
        'theme:muse-storefront': snapshot.resource_fingerprints['theme'],
        'settings': snapshot.resource_fingerprints['settings'],
    }
    actual = base64.b64decode(operation.payload['archive_base64'], validate=True)
    assert actual == archive
    validate_site_archive(actual, package)
    assert changeset == create_changeset(plan, snapshot, package)


def test_captured_code_change_is_reviewed_as_exact_sealed_bytes(source, tmp_path):
    import io
    import tarfile

    from muse.commerce.coding import SourceStore
    from muse.commerce.theme import render_site_files
    plan, snapshot, _, _ = source
    files = render_site_files(plan.blueprint, plan.products)
    files['assets/storefront.css'] += b'\n.product-card { border-radius: 12px; }\n'
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name); info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    artifact = SourceStore(tmp_path / 'source').seal(stream.getvalue(), project_id=plan.project_id,
        plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = artifact.package.code_revision
    candidate = create_changeset(plan, snapshot, artifact.package, coding_artifact=artifact)
    assert base64.b64decode(candidate.operations[0].payload['archive_base64']) == artifact.archive
    assert candidate.package_hash == artifact.package.package_sha256
    from dataclasses import replace
    for changed in [replace(artifact, plan_id='other'), replace(artifact, project_id='other'),
                    replace(artifact, source_digest='e' * 64), replace(artifact, archive=artifact.archive + b'x')]:
        with pytest.raises(CommerceFailure):
            create_changeset(plan, snapshot, artifact.package, coding_artifact=changed)


@pytest.mark.parametrize('state', ['PLANNING', 'BUILDING', 'APPROVED', 'PUBLISHING',
                                  'CANCELLED', 'STALE', 'SUCCEEDED'])
def test_unready_or_terminal_plan_cannot_generate_publish_candidate(source, state):
    plan, snapshot, package, _archive = source
    plan.state = state
    with pytest.raises(CommerceFailure) as error:
        create_changeset(plan, snapshot, package)
    assert error.value.public.code == 'REVIEW_STALE'


@pytest.mark.parametrize('change', ['project', 'snapshot', 'content', 'code', 'blueprint',
                                   'package_hash', 'manifest', 'package_content', 'fingerprint', 'theme_owner'])
def test_changed_source_or_untrusted_resource_blocks_changeset(source, change):
    plan, snapshot, package, _archive = source
    if change == 'project':
        snapshot.project_id = 'other'
    elif change == 'snapshot':
        snapshot.settings['language'] = 'zh'
    elif change == 'content':
        plan.content_hash = 'b' * 64
    elif change == 'code':
        plan.code_revision = 'b' * 40
    elif change == 'blueprint':
        plan.blueprint.pages[0].title = 'Changed'
    elif change == 'package_hash':
        package.package_sha256 = 'b' * 64
    elif change == 'manifest':
        package.files_manifest[0]['sha256'] = 'b' * 64
    elif change == 'package_content':
        package.content_sha256 = 'b' * 64
    elif change == 'fingerprint':
        snapshot.resource_fingerprints['theme'] = 'b' * 64
        plan.snapshot_hash = digest(snapshot)
    else:
        snapshot.theme_identity['stylesheet'] = 'merchant-theme'
        plan.snapshot_hash = digest(snapshot)
    with pytest.raises(CommerceFailure):
        create_changeset(plan, snapshot, package)


def test_paginated_product_list_cannot_authorize_new_sku_creation(source):
    plan, snapshot, _package, _archive = source
    plan.kind = 'launch_products'
    with pytest.raises(CommerceFailure) as error:
        create_changeset(plan, snapshot, None)
    assert error.value.public.code == 'UNSUPPORTED_CAPABILITY'


def test_missing_package_cannot_generate_theme_change(source):
    plan, snapshot, _package, _archive = source
    with pytest.raises(CommerceFailure):
        create_changeset(plan, snapshot, None)


@pytest.mark.parametrize('bad', ['snapshot_text', 'plan_text', 'serialization', 'model_type'])
def test_invalid_serialization_returns_sanitized_input_failure(source, bad):
    plan, snapshot, package, _archive = source
    if bad == 'snapshot_text':
        snapshot.settings['language'] = '\ud800'
    elif bad == 'plan_text':
        plan.id = '\ud800'
    elif bad == 'serialization':
        plan.blueprint.design_tokens['unsupported'] = object()
    else:
        plan = None
    with pytest.raises(CommerceFailure) as error:
        create_changeset(plan, snapshot, package)
    assert error.value.public.code == 'INPUT_INVALID'


def test_new_review_revision_gets_new_operation_identity(source):
    plan, snapshot, package, _archive = source
    old = create_changeset(plan, snapshot, package)
    plan.revision += 1
    new = create_changeset(plan, snapshot, package)
    assert new.id != old.id
    assert new.operations[0].operation_id != old.operations[0].operation_id
    assert new.digest != old.digest


def test_generated_theme_candidate_can_be_persisted_and_approved(tmp_path, source):
    plan, snapshot, package, _archive = source
    root = tmp_path / 'workspace'
    root.mkdir()
    runtime = TaskRepository(tmp_path / 'state.sqlite3')
    repo = CommerceRepository(runtime)
    project = repo.create_project(runtime.register_workspace(str(root))['id'],
                                 SiteBrief(brand_name='Shop', language='en', currency='USD'), 'shop')
    ref = EnvironmentRef(id='stage', project_id=project.id, environment='staging',
                         public_url='https://store.example', connector_ref='stage')
    project = repo.attach_connection(project.id, ref, 'bind', project.revision)
    # A local fixture report, not proof a real website verifier ran.
    snapshot.project_id = plan.project_id = project.id
    plan.snapshot_hash = digest(snapshot)
    plan.state = 'REVIEW_REQUIRED'
    plan = repo.save_plan(plan, 0)
    changeset = create_changeset(plan, snapshot, package)
    report = VerificationReport(id='report', changeset_digest=changeset.digest,
                                code_revision=plan.code_revision, snapshot_hash=plan.snapshot_hash,
                                passed=True, checks=[{'name': 'fixture', 'passed': True}],
                                evidence_refs=['offline-fixture'])
    store = ApprovalRepository(repo, clock=lambda: 1000)
    store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision,
                       expected_plan_revision=plan.revision)
    grant = store.approve(changeset.id, changeset.digest, expected_revision=plan.revision)
    connection = WordPressConnection('stage', project.id, 'staging', 'https://store.example', 'service', 'not-real')
    context = asyncio.run(store.provider(connection)(grant.id))
    assert context.changeset == changeset
    assert context.approval.expires_at == 2800
    authority = ExecutionAuthority(b'x' * 32, clock=lambda: 1000)
    operation = changeset.operations[0]
    token = authority.issue(grant, connection, operation)
    publisher = WordPressPublisher(connection, OperationLedger(tmp_path / 'operations.sqlite3'), authority,
                                   approval_lookup=store.provider(connection), versions_lock={})
    assert asyncio.run(publisher._authorize(grant.id, token, operation)).changeset == changeset
    with pytest.raises(CommerceFailure) as error:
        asyncio.run(publisher.publish(grant.id, token, operation))
    assert error.value.public.code == 'EXECUTION_BOUNDARY_UNAVAILABLE'
    store.revoke(grant.id, project_id=project.id)
    with pytest.raises(CommerceFailure):
        asyncio.run(publisher._authorize(grant.id, token, operation))
