import copy

import pytest


@pytest.mark.parametrize('field,value',[('currency','AUD'),('language','zh-CN')])
def test_retained_storefront_rejects_changed_merchant_settings(merchant_inputs,monkeypatch,field,value):
    from types import SimpleNamespace
    from muse.commerce.retained_storefront import retain_published_storefront
    from muse.commerce.repository import encode
    project,plan,target,snapshot,code,proofs,images=merchant_inputs
    plan.kind='build_site';plan.state='SUCCEEDED'
    plan.blueprint.required_settings.update(store_design={'revision':1},currency='USD',language='en-US')
    project.brief.currency='USD';project.brief.language='en-US'
    setattr(project.brief,field,value)
    snapshot.theme_identity['files_sha256']={item['path']:item['sha256'] for item in code.package.files_manifest}
    conn=SimpleNamespace(execute=lambda *args:[(encode(plan),)])
    monkeypatch.setattr('muse.commerce.code_bridge.load_captured_code',lambda *args,**kwargs:code)
    monkeypatch.setattr('muse.commerce.code_integration.CommerceCodeIntegration._save',lambda *args:None)
    with pytest.raises(CommerceFailure) as error:
        retain_published_storefront(conn,None,project,snapshot)
    assert error.value.public.code=='RESOURCE_CONFLICT'


def test_retained_storefront_rechecks_current_setup(merchant_inputs,monkeypatch):
    from types import SimpleNamespace
    from muse.commerce.retained_storefront import retain_published_storefront
    from muse.commerce.repository import encode
    project,plan,target,snapshot,code,proofs,images=merchant_inputs
    plan.kind='build_site';plan.state='SUCCEEDED'
    plan.blueprint.required_settings.update(store_design={'revision':1},currency=project.brief.currency,language=project.brief.language,missing_fields=[])
    snapshot.theme_identity['files_sha256']={item['path']:item['sha256'] for item in code.package.files_manifest}
    snapshot.settings['payment_confirmed']=False
    project.brief.merchant_supplied_policies['returns']=''
    conn=SimpleNamespace(execute=lambda *args:[(encode(plan),)])
    monkeypatch.setattr('muse.commerce.code_bridge.load_captured_code',lambda *args,**kwargs:code)
    monkeypatch.setattr('muse.commerce.code_integration.CommerceCodeIntegration._save',lambda *args:None)
    blueprint,_=retain_published_storefront(conn,None,project,snapshot)
    assert 'payment_confirmed' in blueprint.required_settings['missing_fields']
    assert 'merchant_supplied_policies.returns' in blueprint.required_settings['missing_fields']


def test_retained_launch_never_installs_theme_and_requires_exact_files(merchant_inputs):
    from muse.commerce.merchant_release import merchant_graph
    from muse.commerce.retained_storefront import validate_retained_theme
    project, plan, target, snapshot, code, proofs, images = merchant_inputs
    plan.blueprint.required_settings['retain_existing_theme'] = True
    snapshot.theme_identity['files_sha256'] = {item['path']:item['sha256'] for item in code.package.files_manifest}
    validate_retained_theme('launch_products',plan.blueprint,code.package,snapshot)
    graph = merchant_graph('launch_products',plan.blueprint,plan.products,code.package,images)
    assert {step.kind for step in graph} == {'create_owned_media','create_product_draft','publish_product'}
    snapshot.theme_identity['files_sha256']['style.css'] = 'f'*64
    with pytest.raises(ValueError):
        validate_retained_theme('launch_products',plan.blueprint,code.package,snapshot)


def test_retained_launch_materializes_complete_independent_preview(merchant_inputs,tmp_path):
    from muse.commerce.staging_source import prepare_staging_source
    project,plan,target,snapshot,code,proofs,images=merchant_inputs
    plan.kind='launch_products'
    plan.blueprint.required_settings['retain_existing_theme']=True
    # Use a genuinely sealed launch source including the retained flag in its
    # content hash, rather than mutating an already sealed fixture declaration.
    plan.content_hash=digest({'blueprint':plan.blueprint.model_dump(mode='json'),'products':[p.model_dump(mode='json') for p in plan.products]})
    code=SourceStore(tmp_path/'retained-preview-source').seal(archive(render_site_files(plan.blueprint,plan.products)),
        project_id=project.id,plan_id=plan.id,snapshot_hash=plan.snapshot_hash,content_hash=plan.content_hash)
    plan.code_revision=code.package.code_revision
    intent=prepare_staging_source(project,plan,target,snapshot,code,proofs,images)
    assert intent.workflow=='build_site'
    assert intent.blueprint==plan.blueprint
    assert intent.content_hash==plan.content_hash
    assert any(step.kind=='install_theme_package' for step in intent.steps)
    assert plan.blueprint.required_settings['retain_existing_theme'] is True

from muse.commerce.coding import SourceStore
from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce.theme import render_site_files
from muse.commerce_connector.media import MediaPayload
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_coding_artifact import archive
from tests.muse.commerce.test_remote_media import image_upload  # noqa: F401
from tests.muse.commerce.test_site_release_intent import (
    site_release_inputs,  # noqa: F401
)


@pytest.fixture
def merchant_inputs(site_release_inputs, image_upload, tmp_path):  # noqa: F811
    from muse.commerce_connector.media import prepare_media_operation
    project, plan, target, snapshot, _code, proofs = site_release_inputs
    repo, uploaded_project, record, absence = image_upload
    operation = prepare_media_operation(repo, uploaded_project.id, record.id, absence, 'image')
    # The independent source fixture uses a different project; re-scope its
    # already cleaned bytes explicitly, never accept caller supplied remote IDs.
    payload = copy.deepcopy(operation.payload)
    payload['media_ref'] = digest([project.id, 'image', record.image.sha256])
    plan.products[0].media_refs = [payload['media_ref']]
    plan.content_hash = digest({'blueprint': plan.blueprint.model_dump(mode='json'),
                               'products': [p.model_dump(mode='json') for p in plan.products]})
    code = SourceStore(tmp_path / 'merchant-code').seal(archive(render_site_files(plan.blueprint, plan.products)),
        project_id=project.id, plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    proof = copy.deepcopy(absence)
    proofs[proof['resource_key']] = proof
    return project, plan, target, snapshot, code, proofs, [MediaPayload.model_validate(payload)]


@pytest.mark.parametrize('business_kind', ['build_site', 'launch_products'])
def test_merchant_graph_binds_image_bytes_and_source_before_business_steps(merchant_inputs, business_kind):
    from muse.commerce.merchant_release import (
        prepare_merchant_release,
        validate_merchant_release,
    )
    args = merchant_inputs
    args[1].kind = business_kind
    if business_kind == 'launch_products':
        for key in list(args[5]):
            if key.startswith('page-slug:'): args[5].pop(key)
    intent = prepare_merchant_release(*args)
    assert intent.version == 4 and intent.workflow == business_kind
    assert intent.steps[0].kind == 'create_owned_media'
    assert len(intent.steps) == (18 if business_kind == 'build_site' else 4)
    assert intent.products[0].media_refs == [intent.images[0].media_ref]
    assert intent.content_hash == args[1].content_hash and intent.package == args[4].package
    assert validate_merchant_release(intent) == intent


@pytest.mark.parametrize('attack', ['bytes', 'ref', 'order', 'extra', 'missing', 'scope', 'dependency', 'original_proof'])
def test_merchant_graph_rejects_changed_frozen_image_or_symbolic_dag(merchant_inputs, attack):
    from muse.commerce.merchant_release import (
        prepare_merchant_release,
        validate_merchant_release,
    )
    args = merchant_inputs
    if attack == 'original_proof':
        args[5][next(key for key in args[5] if key.startswith('media-sha256:'))]['state']['exists'] = 0
        with pytest.raises(CommerceFailure): prepare_merchant_release(*args)
        return
    intent = prepare_merchant_release(*args)
    if attack == 'bytes': intent.images[0].content_base64 = 'bm90LWFuLWltYWdl'
    elif attack == 'ref': intent.products[0].media_refs = ['f' * 64]
    elif attack == 'order': intent.steps[:2] = reversed(intent.steps[:2])
    elif attack == 'extra': intent.resource_preconditions['media-sha256:' + 'f' * 64] = 'e' * 64
    elif attack == 'missing': intent.images = []
    elif attack == 'scope': intent.images[0].media_ref = 'f' * 64
    else: intent.steps[1].depends_on = []
    # A newly calculated outer hash must not legalize an altered graph/source.
    intent.digest = digest(intent.model_dump(mode='json', exclude={'digest'}))
    with pytest.raises(CommerceFailure): validate_merchant_release(intent)


def test_merchant_media_step_uses_receipt_bound_ids_and_blocks_unknown_predecessor(merchant_inputs):
    from muse.commerce.merchant_release import prepare_merchant_release
    from muse.commerce.merchant_steps import project_merchant_step
    from muse.commerce.site_steps import CompletedSiteStep
    args = merchant_inputs
    intent = prepare_merchant_release(*args)
    connection = WordPressConnection('connection', 'project', 'staging', 'https://shop.test', 'fixture', 'fake')
    first = project_merchant_step(intent, connection, args[4], 0, [], args[3], args[5])
    assert first.operation.payload == intent.images[0].model_dump(mode='json')
    image = intent.images[0]
    entity = {**image.image.model_dump(), 'id': 700, 'media_ref': image.media_ref, 'muse_project_id': 'project',
        'status': 'inherit', 'parent_id': 0, 'title': 'MUSE image ' + image.image.sha256, 'alt': ''}
    state = {'sha256': image.image.sha256, 'exists': True, 'attachment': entity}
    proof = {'resource_key': first.operation.resource_key, 'state': state, 'fingerprint': digest(state)}
    receipt = OperationRecord(project_id='project', connection_id='connection', environment='staging',
        operation_id=first.operation.operation_id, operation_digest=operation_digest(first.operation),
        resource_key=first.operation.resource_key, state='SUCCEEDED', fingerprint=proof['fingerprint'])
    proofs = copy.deepcopy(args[5]); proofs[proof['resource_key']] = proof
    done = CompletedSiteStep(first.operation, receipt, args[3], proof)
    next_step = project_merchant_step(intent, connection, args[4], 1, [done], args[3], proofs)
    assert next_step.operation.kind == 'install_theme_package'
    assert next_step.preconditions[proof['resource_key']] == proof['fingerprint']
    done.receipt = receipt.model_copy(update={'state': 'NEEDS_RECONCILIATION'})
    with pytest.raises(CommerceFailure): project_merchant_step(intent, connection, args[4], 1, [done], args[3], proofs)


def test_merchant_complete_live_graph_validates_source_navigation_and_image_effects(merchant_inputs, tmp_path):
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.merchant_release import prepare_merchant_release
    from muse.commerce.merchant_steps import (
        project_merchant_step,
        validate_merchant_completion,
    )
    from tests.muse.commerce.test_site_release_steps import outcome
    project, plan, target, original, _old_code, proofs, images = merchant_inputs
    target.environment = 'live'
    snapshot = normalize_snapshot(original.model_dump(mode='json'), project.id, 'live')
    plan.snapshot_hash = digest(snapshot)
    code = SourceStore(tmp_path / 'live-source').seal(archive(render_site_files(plan.blueprint, plan.products)),
        project_id=project.id, plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    connection = WordPressConnection('connection', project.id, 'live', target.public_url, 'fixture', 'fake')
    intent = prepare_merchant_release(project, plan, target, snapshot, code, proofs, images, connection=connection)
    history = []
    for index in range(len(intent.steps)):
        projected = project_merchant_step(intent, connection, code, index, history, snapshot, proofs)
        done, snapshot = outcome(intent, connection, code, projected, snapshot, proofs)
        history.append(done)
    versions = validate_merchant_completion(intent, connection, code, history, snapshot, proofs)
    assert len(history) == 18 and snapshot.products[0]['image_id'] == 701
    assert versions['navigation:muse-storefront'] == snapshot.resource_fingerprints['navigation:muse-storefront']


def test_merchant_live_target_uses_its_own_versions_without_resealing_staging_source(merchant_inputs):
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.merchant_release import prepare_merchant_release
    from muse.commerce.merchant_steps import project_merchant_step
    project, plan, stage_target, stage_snapshot, code, proofs, images = merchant_inputs
    live_target = stage_target.model_copy(update={'id': 'live', 'connector_ref': 'live-connection',
        'environment': 'live', 'public_url': 'https://live-shop.test'})
    project.environment_refs.append(live_target)
    raw = stage_snapshot.model_dump(mode='json')
    raw['settings']['permalink_structure'] = '/%postname%/'
    live_snapshot = normalize_snapshot(raw, project.id, 'live')
    connection = WordPressConnection('live-connection', project.id, 'live', live_target.public_url, 'fixture', 'fake')
    intent = prepare_merchant_release(project, plan, live_target, live_snapshot, code, proofs, images, connection=connection)
    assert intent.snapshot_hash == plan.snapshot_hash == code.snapshot_hash
    assert intent.target_snapshot_hash == digest(live_snapshot) != intent.snapshot_hash
    assert intent.package.code_revision == code.package.code_revision
    first = project_merchant_step(intent, connection, code, 0, [], live_snapshot, proofs)
    assert first.preconditions['settings'] == live_snapshot.resource_fingerprints['settings']
