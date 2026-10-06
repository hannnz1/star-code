import hashlib

import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from tests.muse.commerce.test_release_intent import product_release_inputs


@pytest.fixture
def site_release_inputs(tmp_path):
    from muse.commerce.coding import SourceStore
    from muse.commerce.theme import render_site_files
    from tests.muse.commerce.test_coding_artifact import archive
    project, plan, target, snapshot, sku_proofs = product_release_inputs()
    raw = snapshot.model_dump(mode='json')
    raw['theme_identity']['owned_navigation'] = {'items': []}
    snapshot = normalize_snapshot(raw, project.id, target.environment)
    plan.kind = 'build_site'
    plan.snapshot_hash = digest(snapshot)
    code = SourceStore(tmp_path / 'source').seal(archive(render_site_files(plan.blueprint, plan.products)),
        project_id=project.id, plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    proofs = dict(sku_proofs)
    for page in plan.blueprint.pages:
        if page.kind != 'product':
            key = 'page-slug:' + hashlib.sha256(page.slug.encode()).hexdigest()
            state = {'slug': page.slug, 'exists': False}
            proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    return project, plan, target, snapshot, code, proofs


def test_site_intent_freezes_exact_source_and_orders_theme_pages_settings_navigation_and_products(site_release_inputs):
    from muse.commerce.site_release import prepare_site_release, validate_site_release
    intent = prepare_site_release(*site_release_inputs)
    assert intent.version == 3 and len(intent.steps) == 17
    assert intent.steps[0].kind == 'install_theme_package'
    assert [step.kind for step in intent.steps[1:13]] == ['create_owned_page', 'publish_owned_page'] * 6
    assert [step.kind for step in intent.steps[13:]] == ['set_storefront_options', 'set_owned_navigation',
                                                     'create_product_draft', 'publish_product']
    assert intent.source_digest == site_release_inputs[4].source_digest
    assert intent.package == site_release_inputs[4].package
    assert validate_site_release(intent) == intent
    assert set(intent.resource_preconditions) >= {'theme:muse-storefront', 'settings', 'navigation:muse-storefront'}
    site_release_inputs[1].blueprint.pages[0].title = 'Changed after capture'
    assert intent.blueprint.pages[0].title != 'Changed after capture'


@pytest.mark.parametrize('mutation', ['reorder', 'dependency', 'page_title', 'theme_source', 'scope', 'extra', 'media', 'proof_bool'])
def test_site_intent_refuses_changed_graph_source_scope_and_unproven_resources(site_release_inputs, mutation):
    from muse.commerce.site_release import prepare_site_release, validate_site_release
    args = site_release_inputs
    if mutation in {'media', 'proof_bool'}:
        if mutation == 'media':
            args[1].products[0].media_refs = ['unbound-image']
        else:
            args[5][next(key for key in args[5] if key.startswith('page-slug:'))]['state']['exists'] = 0
        with pytest.raises(CommerceFailure):
            prepare_site_release(*args)
        return
    intent = prepare_site_release(*args)
    if mutation == 'reorder': intent.steps[1:3] = reversed(intent.steps[1:3])
    elif mutation == 'dependency': intent.steps[2].depends_on = []
    elif mutation == 'page_title': intent.blueprint.pages[0].title = 'Altered'
    elif mutation == 'theme_source': intent.source_digest = 'f' * 64
    elif mutation == 'scope': intent.target.project_id = 'other'
    else: intent.resource_preconditions['page:999'] = 'e' * 64
    with pytest.raises(CommerceFailure):
        validate_site_release(intent)


def test_site_intent_rejects_missing_absence_proofs_and_existing_storefront_page(site_release_inputs):
    from muse.commerce.site_release import prepare_site_release
    args = site_release_inputs
    args[5].pop(next(key for key in args[5] if key.startswith('page-slug:')))
    with pytest.raises(CommerceFailure):
        prepare_site_release(*args)


def test_site_intent_supports_empty_catalog_without_inventing_a_product(site_release_inputs, tmp_path):
    from muse.commerce.coding import SourceStore
    from muse.commerce.site_release import prepare_site_release
    from muse.commerce.theme import render_site_files
    from tests.muse.commerce.test_coding_artifact import archive
    project, plan, target, snapshot, code, proofs = site_release_inputs
    plan.products = []
    plan.content_hash = digest({'blueprint': plan.blueprint.model_dump(mode='json'), 'products': []})
    code = SourceStore(tmp_path / 'empty-source').seal(
        archive(render_site_files(plan.blueprint, [])), project_id=project.id, plan_id=plan.id,
        snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    intent = prepare_site_release(project, plan, target, snapshot, code,
                                  {key: proof for key, proof in proofs.items() if key.startswith('page-slug:')})
    assert len(intent.steps) == 15 and intent.products == []


def test_site_release_has_canonical_page_order_even_when_source_is_resealed(site_release_inputs, tmp_path):
    from muse.commerce.coding import SourceStore
    from muse.commerce.site_release import prepare_site_release
    from muse.commerce.theme import render_site_files
    from tests.muse.commerce.test_coding_artifact import archive
    project, plan, target, snapshot, _code, proofs = site_release_inputs
    plan.blueprint.pages[0:2] = reversed(plan.blueprint.pages[0:2])
    plan.content_hash = digest({'blueprint': plan.blueprint.model_dump(mode='json'),
                               'products': [product.model_dump(mode='json') for product in plan.products]})
    code = SourceStore(tmp_path / 'reordered').seal(archive(render_site_files(plan.blueprint, plan.products)),
        project_id=project.id, plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    with pytest.raises(CommerceFailure):
        prepare_site_release(project, plan, target, snapshot, code, proofs)
