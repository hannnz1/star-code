"""v4 merchant declarations bind cleaned image bytes and accurate code together.

This is a private frozen source bundle, not a write permit. Public views must
only return descriptors, never its base64 bytes. v1/v2/v3 declarations retain
their original semantics and continue rejecting media business graphs.
"""
import copy
import hashlib
import re
from typing import Literal

from pydantic import Field

from muse.commerce.coding import verify_coding_artifact
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Contract
from muse.commerce.release import release_source_hash
from muse.commerce.repository import digest
from muse.commerce.site_release import SiteReleaseIntent, _graph
from muse.commerce.theme import ALLOWED_FILES
from muse.commerce_connector.media import MediaPayload
from muse.commerce_connector.wordpress import WordPressConnection


class MerchantReleaseStep(Contract):
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,99}$')
    kind: Literal['create_owned_media', 'install_theme_package', 'create_owned_page', 'publish_owned_page',
        'set_storefront_options', 'set_owned_navigation', 'create_product_draft', 'publish_product',
        'set_owned_shipping', 'set_owned_store_navigation']
    resource_ref: str
    depends_on: list[str] = Field(max_length=8)
    payload: dict


class MerchantReleaseIntent(SiteReleaseIntent):
    version: Literal[4] = 4
    workflow: Literal['build_site', 'launch_products']
    target_snapshot_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    images: list[MediaPayload] = Field(max_length=100)
    steps: list[MerchantReleaseStep] = Field(min_length=1, max_length=176)


def preview_category_products(workflow, blueprint, products):
    """Deterministic hidden fixtures in a retained independent preview only.

    The merchant launch graph and its approved product list never include them.
    The remote executor additionally requires the isolated v8 preview audience.
    """
    if workflow != 'build_site' or not blueprint.required_settings.get('retain_existing_theme'):
        return []
    from muse.commerce.store_configuration import category_targets
    from muse.commerce.models import ProductDraft
    missing=[item.category for item in category_targets(blueprint,products) if item.category not in {p.category for p in products}]
    if len(products)>20 or len(missing)>10:
        raise CommerceFailure('UNSUPPORTED_CAPABILITY',422)
    return [ProductDraft(sku='CREW-PREVIEW-CAT-'+hashlib.sha256(name.encode()).hexdigest()[:20],
        title='Crew preview category fixture',price='0.00',currency=blueprint.required_settings['currency'],
        stock=0,category=name,source_facts={'crew_preview_seed':'category'}) for name in missing]


def merchant_graph(workflow, blueprint, products, package, images):
    # First-occurrence order is merchant primary/gallery order, not a model's
    # remote ID selection. Shared images are created once per frozen bundle.
    from muse.commerce.design_resources import source_media_refs,design_media_refs,owned_image_path
    retained = workflow == 'launch_products' and blueprint.required_settings.get('retain_existing_theme')
    refs = list(dict.fromkeys(ref for p in products for ref in p.media_refs)) if retained else source_media_refs(blueprint, products)
    design_refs = [] if retained else design_media_refs(blueprint)
    if design_refs:
        records = {image.media_ref:image for image in images}
        expected = {ref:owned_image_path(blueprint.required_settings['store_design']['project_id'], records[ref].image.sha256, records[ref].image.mime_type) for ref in design_refs}
        if blueprint.required_settings.get('design_media_urls') != expected: raise ValueError('Design media path differs from exact owned bytes')
    if refs != [image.media_ref for image in images] or any(len(set(p.media_refs)) != len(p.media_refs) for p in products):
        raise ValueError('Image order or membership differs')
    if sum(image.image.byte_size for image in images) > 100 * 1024 * 1024:
        raise ValueError('Image bundle exceeds project limit')
    rows = [{'key': f'create-image-{index}', 'kind': 'create_owned_media',
        'resource_ref': 'media-sha256:' + image.image.sha256,
        'payload': {'media_ref': image.media_ref, 'image': image.image.model_dump()}}
        for index, image in enumerate(images, 1)]
    graph_products=[*products,*preview_category_products(workflow,blueprint,products)]
    base = _graph(blueprint, graph_products, package)
    if workflow == 'build_site' and store_configuration_enabled(blueprint):
        from muse.commerce.category_navigation import CategoryNavigation
        from muse.commerce.shipping_rules import ShippingRules
        navigation = next(step for step in base if step.kind == 'set_owned_navigation')
        base = [step for step in base if step.kind != 'set_owned_navigation']
        items = list(navigation.payload['items'])
        if 'category_navigation' in blueprint.required_settings:
            categories = CategoryNavigation.model_validate(blueprint.required_settings['category_navigation'])
            names = {product.category for product in graph_products if product.category}
            if any(item.category not in names for item in categories.items):
                raise ValueError('Selected build batch must contain every category target')
            items.extend({'category_name': item.category, 'label': item.label} for item in categories.items)
        rows.extend(step.model_dump(mode='json', exclude={'depends_on'}) for step in base)
        if 'shipping_rules' in blueprint.required_settings:
            rules = ShippingRules.model_validate(blueprint.required_settings['shipping_rules'])
            rows.append({'key':'set-shipping','kind':'set_owned_shipping','resource_ref':'shipping:muse-storefront',
                         'payload':{'rules':rules.model_dump(mode='json')}})
        rows.append({'key':'set-store-navigation','kind':'set_owned_store_navigation',
                     'resource_ref':'navigation:muse-storefront','payload':{'items':items}})
        base = []
    if workflow == 'launch_products':
        if not products: raise ValueError('Launch requires products')
        base = [step for step in base if step.kind in {'install_theme_package', 'create_product_draft', 'publish_product'}]
        if retained:
            base = [step for step in base if step.kind != 'install_theme_package']
    rows.extend(step.model_dump(mode='json', exclude={'depends_on'}) for step in base)
    result = []
    for row in rows:
        # The release is intentionally serial; successful predecessors must
        # all be accounted before projecting any next business write.
        row['depends_on'] = [] if not result else [result[-1].key]
        result.append(MerchantReleaseStep.model_validate(row))
    return result


def store_configuration_enabled(blueprint):
    return 'shipping_rules' in blueprint.required_settings or 'category_navigation' in blueprint.required_settings


def validate_merchant_release(intent, *, connection=None):
    try:
        frozen = MerchantReleaseIntent.model_validate(intent.model_dump(mode='json'))
        target = frozen.target
        if connection is None:
            WordPressConnection(target.connector_ref, frozen.project_id, target.environment,
                target.public_url, 'scope-only', 'not-a-credential')
        elif (not isinstance(connection, WordPressConnection) or connection.connection_id != target.connector_ref
                or connection.project_id != frozen.project_id or connection.environment != target.environment
                or connection.base_url != target.public_url):
            raise ValueError('Wrong configured scope')
        if (type(intent.version) is not int or target.project_id != frozen.project_id
                or frozen.digest != digest(frozen.model_dump(mode='json', exclude={'digest'}))
                or frozen.package.content_sha256 != frozen.content_hash
                or frozen.content_hash != digest({'blueprint': frozen.blueprint.model_dump(mode='json'),
                    'products': [product.model_dump(mode='json') for product in frozen.products]})
                or frozen.steps != merchant_graph(frozen.workflow, frozen.blueprint, frozen.products, frozen.package, frozen.images)
                or any(image.media_ref != digest([frozen.project_id, 'image', image.image.sha256]) for image in frozen.images)):
            raise ValueError('Graph/source binding differs')
        hashes = {entry['path']: entry['sha256'] for entry in frozen.package.files_manifest}
        if set(hashes) != ALLOWED_FILES or len(frozen.package.files_manifest) != 15 or digest(hashes) != frozen.source_digest:
            raise ValueError('Source manifest differs')
        snapshot = frozen.initial_snapshot
        from muse.commerce.retained_storefront import validate_retained_theme
        validate_retained_theme(frozen.workflow, frozen.blueprint, frozen.package, snapshot)
        if (snapshot.project_id != frozen.project_id or snapshot.environment != target.environment
                or digest(snapshot) != frozen.target_snapshot_hash
                or normalize_snapshot(snapshot.model_dump(mode='json'), snapshot.project_id, snapshot.environment) != snapshot):
            raise ValueError('Original snapshot differs')
        conditions = {'theme:muse-storefront': snapshot.resource_fingerprints['theme'],
            'settings': snapshot.resource_fingerprints['settings'],
            'navigation:muse-storefront': snapshot.resource_fingerprints['navigation:muse-storefront']}
        if any(step.kind == 'set_owned_shipping' for step in frozen.steps):
            conditions['shipping:muse-storefront'] = snapshot.resource_fingerprints['shipping:muse-storefront']
        for step in frozen.steps:
            if step.kind not in {'create_owned_media', 'create_owned_page', 'create_product_draft'}: continue
            name, value = ('sha256', step.payload['image']['sha256']) if step.kind == 'create_owned_media' else (
                ('slug', step.payload['slug']) if step.kind == 'create_owned_page' else
                ('sku', step.payload['product']['sku'].strip().casefold()))
            if step.resource_ref in conditions: raise ValueError('Repeated resource creation')
            conditions[step.resource_ref] = digest({name: value, 'exists': False})
            if name != 'sha256':
                entities = snapshot.pages if name == 'slug' else snapshot.products
                if any((entity.get('slug') if name == 'slug' else entity.get('sku', '').strip().casefold()) == value for entity in entities):
                    raise ValueError('Original context contradicts absence')
        if frozen.resource_preconditions != conditions or any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in conditions.values()):
            raise ValueError('Resource conditions differ')
        return frozen
    except CommerceFailure:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommerceFailure('REVIEW_STALE') from None


def prepare_merchant_release(project, plan, target, snapshot, code, absence_proofs, images, *, connection=None):
    try:
        if (plan.state not in {'VERIFYING', 'REVIEW_REQUIRED'} or plan.blueprint is None
                or project.id != plan.project_id or project.id != target.project_id or target not in project.environment_refs
                or snapshot.project_id != project.id or snapshot.environment != target.environment
                or code.project_id != project.id or code.plan_id != plan.id
                or code.snapshot_hash != plan.snapshot_hash or code.package.content_sha256 != plan.content_hash
                or code.package.code_revision != plan.code_revision or snapshot.settings.get('currency') != project.brief.currency
                or snapshot.settings.get('language') != project.brief.language
                or any(p.currency != project.brief.currency for p in plan.products)):
            raise ValueError('Frozen source/current plan differs')
        verify_coding_artifact(code)
        from muse.commerce.retained_storefront import validate_retained_theme
        validate_retained_theme(plan.kind, plan.blueprint, code.package, snapshot)
        if snapshot.theme_identity.get('stylesheet') != 'muse-storefront':
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
        frozen_images = [MediaPayload.model_validate(image.model_dump(mode='json')) for image in images]
        steps = merchant_graph(plan.kind, plan.blueprint, plan.products, code.package, frozen_images)
        conditions = {'theme:muse-storefront': snapshot.resource_fingerprints['theme'],
            'settings': snapshot.resource_fingerprints['settings'],
            'navigation:muse-storefront': snapshot.resource_fingerprints['navigation:muse-storefront']}
        if any(step.kind == 'set_owned_shipping' for step in steps):
            if 'shipping:muse-storefront' not in snapshot.resource_fingerprints:
                raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
            conditions['shipping:muse-storefront'] = snapshot.resource_fingerprints['shipping:muse-storefront']
        refs = set()
        for step in steps:
            if step.kind not in {'create_owned_media', 'create_owned_page', 'create_product_draft'}: continue
            name, value = ('sha256', step.payload['image']['sha256']) if step.kind == 'create_owned_media' else (
                ('slug', step.payload['slug']) if step.kind == 'create_owned_page' else
                ('sku', step.payload['product']['sku'].strip().casefold()))
            state = {name: value, 'exists': False}; proof = absence_proofs.get(step.resource_ref)
            if (not isinstance(proof, dict) or set(proof) != {'resource_key', 'state', 'fingerprint'}
                    or proof['resource_key'] != step.resource_ref or proof['state'] != state
                    or proof['state'].get('exists') is not False or proof['fingerprint'] != digest(state)):
                raise ValueError('Original identity absence differs')
            refs.add(step.resource_ref); conditions[step.resource_ref] = proof['fingerprint']
        if set(absence_proofs) != refs: raise ValueError('Unexpected original identity proof')
        intent = MerchantReleaseIntent(project_id=project.id, project_revision=project.revision, plan_id=plan.id,
            plan_revision=plan.revision, plan_source_hash=release_source_hash(plan), target=target.model_copy(deep=True),
            snapshot_hash=plan.snapshot_hash, target_snapshot_hash=digest(snapshot),
            initial_snapshot=snapshot.model_copy(deep=True), content_hash=plan.content_hash,
            source_digest=code.source_digest, package=code.package.model_copy(deep=True), blueprint=plan.blueprint.model_copy(deep=True),
            products=copy.deepcopy(plan.products), images=frozen_images, workflow=plan.kind, steps=steps,
            resource_preconditions=conditions, digest='')
        intent.digest = digest(intent.model_dump(mode='json', exclude={'digest'}))
        return validate_merchant_release(intent, connection=connection)
    except CommerceFailure:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommerceFailure('REVIEW_STALE') from None
