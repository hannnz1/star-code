import hashlib

import pytest

from muse.commerce.models import (
    CommercePlan,
    EnvironmentRef,
    ProductDraft,
    StoreProject,
)
from muse.commerce.repository import digest


def product_release_inputs():
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.models import SiteBrief
    from muse.commerce.site import build_site_blueprint
    snapshot = normalize_snapshot({'pages': [], 'products': [],
        'settings': {'currency': 'USD', 'language': 'en-US'},
        'theme_identity': {'stylesheet': 'muse-storefront', 'effective_templates': [], 'global_styles': {'styles': {}}}},
        'project', 'staging')
    brief = SiteBrief(brand_name='Cup Store', language='en-US', currency='USD')
    target = EnvironmentRef(id='stage', project_id='project', environment='staging', connector_ref='connection', public_url='https://shop.test')
    project = StoreProject(id='project', workspace_id='workspace', brief=brief, environment_refs=[target])
    products = [ProductDraft(sku='CUP', title='Cup', price='10.00', currency='USD', stock=3)]
    blueprint = build_site_blueprint(brief, snapshot)
    content_hash = digest({'blueprint': blueprint.model_dump(mode='json'), 'products': [p.model_dump(mode='json') for p in products]})
    plan = CommercePlan(id='plan', project_id='project', kind='launch_products', state='VERIFYING', products=products,
        blueprint=blueprint, snapshot_hash=digest(snapshot), content_hash=content_hash, code_revision='c' * 40)
    state = {'sku': 'cup', 'exists': False}
    key = 'sku:' + hashlib.sha256(b'cup').hexdigest()
    proofs = {key: {'resource_key': key, 'state': state, 'fingerprint': digest(state)}}
    return project, plan, target, snapshot, proofs


def test_product_release_freezes_create_publish_graph_and_original_absence_proof():
    from muse.commerce.release import prepare_product_release, validate_product_release
    inputs = product_release_inputs()
    intent = prepare_product_release(*inputs)
    assert [step.kind for step in intent.steps] == ['create_product_draft', 'publish_product']
    assert intent.steps[1].depends_on == [intent.steps[0].key]
    assert intent.steps[0].resource_ref == intent.steps[1].resource_ref
    assert intent.resource_preconditions[intent.steps[0].resource_ref] == next(iter(inputs[-1].values()))['fingerprint']
    assert intent.target == inputs[2]
    assert intent.digest == validate_product_release(intent).digest
    inputs[1].products[0].title = 'Later changed'
    assert intent.steps[0].product.title == 'Cup'


@pytest.mark.parametrize('change', ['title', 'order', 'dependency', 'target', 'expiry_forgery'])
def test_frozen_product_release_rejects_altered_graph_or_source(change):
    from muse.commerce.release import prepare_product_release, validate_product_release
    intent = prepare_product_release(*product_release_inputs())
    if change == 'title':
        intent.steps[0].product.title = 'Changed title'
    elif change == 'order':
        intent.steps.reverse()
    elif change == 'dependency':
        intent.steps[1].depends_on = ['not-in-intent']
    elif change == 'target':
        intent.target.public_url = 'https://other.test'
    else:
        intent.version = True
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        validate_product_release(intent)


@pytest.mark.parametrize('change', ['exists', 'missing_proof', 'wrong_identity', 'old_snapshot', 'wrong_project', 'media'])
def test_product_release_does_not_guess_absence_or_accept_rebound_facts(change):
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.release import prepare_product_release
    project, plan, target, snapshot, proofs = product_release_inputs()
    key = next(iter(proofs))
    if change == 'exists':
        proofs[key]['state']['exists'] = True
        proofs[key]['fingerprint'] = digest(proofs[key]['state'])
    elif change == 'missing_proof':
        proofs.clear()
    elif change == 'wrong_identity':
        proofs[key]['state']['sku'] = 'other'
        proofs[key]['fingerprint'] = digest(proofs[key]['state'])
    elif change == 'old_snapshot':
        plan.snapshot_hash = 'f' * 64
    elif change == 'wrong_project':
        target.project_id = 'other'
    else:
        plan.products[0].media_refs = ['image-without-upload-receipt']
    with pytest.raises(CommerceFailure):
        prepare_product_release(project, plan, target, snapshot, proofs)


@pytest.mark.parametrize('change', ['false_as_zero', 'currency', 'foreign_theme'])
def test_product_release_rejects_coercible_absence_and_incompatible_shop(change):
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.release import prepare_product_release
    project, plan, target, snapshot, proofs = product_release_inputs()
    if change == 'false_as_zero':
        proofs[next(iter(proofs))]['state']['exists'] = 0
    elif change == 'currency':
        project.brief.currency = 'EUR'
    else:
        snapshot.theme_identity['stylesheet'] = 'other-theme'
        snapshot.resource_fingerprints['theme'] = digest(snapshot.theme_identity)
        plan.snapshot_hash = digest(snapshot)
    with pytest.raises(CommerceFailure):
        prepare_product_release(project, plan, target, snapshot, proofs)


def test_loopback_release_requires_matching_trusted_development_connection():
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.release import prepare_product_release
    from muse.commerce_connector.wordpress import WordPressConnection
    args = product_release_inputs()
    args[2].public_url = 'http://127.0.0.1:63665'
    with pytest.raises(CommerceFailure):
        prepare_product_release(*args)
    connection = WordPressConnection('connection', 'project', 'staging', args[2].public_url, 'service', 'fixture',
                                     approved_development_http=True)
    intent = prepare_product_release(*args, connection=connection)
    assert intent.target.public_url == connection.base_url
    wrong = WordPressConnection('other', 'project', 'staging', args[2].public_url, 'service', 'fixture',
                                approved_development_http=True)
    with pytest.raises(CommerceFailure):
        prepare_product_release(*args, connection=wrong)


def test_release_source_hash_freezes_facts_while_workflow_state_can_advance():
    from muse.commerce.release import prepare_product_release, release_source_hash
    args = product_release_inputs()
    plan = args[1]
    intent = prepare_product_release(*args)
    assert intent.plan_source_hash == release_source_hash(plan)
    advanced = plan.model_copy(update={'state': 'REVIEW_REQUIRED', 'revision': plan.revision + 1})
    assert release_source_hash(advanced) == intent.plan_source_hash
    advanced.products[0].title = 'Changed source'
    assert release_source_hash(advanced) != intent.plan_source_hash
