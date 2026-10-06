"""Frozen website graph, separate from the product-only v2 protocol.

This declaration performs no write, approval or signing. The execution broker
must bind symbolic IDs exclusively from authenticated predecessor receipts.
"""
import hashlib
import re
from typing import Literal

from pydantic import Field

from muse.commerce.coding import verify_coding_artifact
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    ChangeOperation,
    Contract,
    EnvironmentRef,
    ProductDraft,
    SiteBlueprint,
    SitePackage,
    StoreSnapshot,
)
from muse.commerce.release import release_source_hash
from muse.commerce.repository import digest
from muse.commerce.theme import ALLOWED_FILES
from muse.commerce_connector.operations import validate_operation
from muse.commerce_connector.wordpress import WordPressConnection


class SiteReleaseStep(Contract):
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,99}$')
    kind: Literal['install_theme_package', 'create_owned_page', 'publish_owned_page',
                  'set_storefront_options', 'set_owned_navigation', 'create_product_draft', 'publish_product']
    resource_ref: str
    depends_on: list[str] = Field(max_length=8)
    payload: dict


class SiteReleaseIntent(Contract):
    version: Literal[3] = 3
    project_id: str
    project_revision: int = Field(ge=1)
    plan_id: str
    plan_revision: int = Field(ge=1)
    plan_source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    target: EnvironmentRef
    snapshot_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    initial_snapshot: StoreSnapshot
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    package: SitePackage
    blueprint: SiteBlueprint
    products: list[ProductDraft] = Field(max_length=20)
    steps: list[SiteReleaseStep] = Field(min_length=15, max_length=55)
    resource_preconditions: dict[str, str]
    digest: str

    @property
    def code_revision(self):
        return self.package.code_revision


def _identity(kind, value):
    value = value.strip().casefold() if kind == 'sku' else value
    return kind + ':' + hashlib.sha256(value.encode()).hexdigest()


def _graph(blueprint, products, package):
    if [page.kind for page in blueprint.pages if page.kind != 'product'] != ['home', 'shop', 'cart', 'checkout', 'about', 'contact']:
        raise ValueError('Canonical website page order is required')
    steps = []
    def add(key, kind, ref, payload, dependencies=()):
        deps = list(dict.fromkeys([*([] if not steps else [steps[-1].key]), *dependencies]))
        steps.append(SiteReleaseStep(key=key, kind=kind, resource_ref=ref, depends_on=deps, payload=payload))
    add('install-theme', 'install_theme_package', 'theme:muse-storefront', {'package': package.model_dump(mode='json')})
    page_refs, published = {}, {}
    for page in blueprint.pages:
        if page.kind == 'product':
            continue
        ref = _identity('page-slug', page.slug)
        page_refs[page.kind] = ref
        add('create-page-' + page.kind, 'create_owned_page', ref,
            {'slug': page.slug, 'title': page.title, 'content': '',
             'template': 'page-' + page.kind if page.kind in {'cart', 'checkout', 'about', 'contact'} else 'page'})
        key = 'publish-page-' + page.kind
        add(key, 'publish_owned_page', ref, {'page_ref': ref})
        published[page.kind] = key
    add('set-storefront', 'set_storefront_options', 'settings',
        {kind + '_page_ref': page_refs[kind] for kind in ('home', 'shop', 'cart', 'checkout')},
        [published[kind] for kind in ('home', 'shop', 'cart', 'checkout')])
    by_slug = {page.slug: page.kind for page in blueprint.pages if page.kind != 'product'}
    if not blueprint.navigation or any(item.slug not in by_slug for item in blueprint.navigation):
        raise ValueError('Navigation must reference distinct real blueprint pages')
    if len({item.slug for item in blueprint.navigation}) != len(blueprint.navigation):
        raise ValueError('Duplicate navigation')
    add('set-navigation', 'set_owned_navigation', 'navigation:muse-storefront',
        {'items': [{'page_ref': page_refs[by_slug[item.slug]], 'label': item.label} for item in blueprint.navigation]},
        [published[by_slug[item.slug]] for item in blueprint.navigation])
    for index, product in enumerate(products, 1):
        ref = _identity('sku', product.sku)
        add(f'create-product-{index}', 'create_product_draft', ref, {'product': product.model_dump(mode='json')})
        add(f'publish-product-{index}', 'publish_product', ref, {'product_ref': ref})
    return steps


def _hash(intent):
    return digest(intent.model_dump(mode='json', exclude={'digest'}))


def validate_site_release(intent, *, connection=None):
    try:
        frozen = SiteReleaseIntent.model_validate(intent.model_dump(mode='json'))
        if {'shipping_rules', 'category_navigation'} & frozen.blueprint.required_settings.keys():
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
        if connection is None:
            WordPressConnection(frozen.target.connector_ref, frozen.project_id, frozen.target.environment,
                                frozen.target.public_url, 'scope-only', 'not-a-credential')
        elif (not isinstance(connection, WordPressConnection) or connection.project_id != frozen.project_id
              or connection.connection_id != frozen.target.connector_ref or connection.environment != frozen.target.environment
              or connection.base_url != frozen.target.public_url):
            raise ValueError('Wrong connection scope')
        if (type(intent.version) is not int or frozen.target.project_id != frozen.project_id or frozen.digest != _hash(frozen)
                or frozen.package.content_sha256 != frozen.content_hash
                or digest({'blueprint': frozen.blueprint.model_dump(mode='json'),
                           'products': [p.model_dump(mode='json') for p in frozen.products]}) != frozen.content_hash
                or frozen.steps != _graph(frozen.blueprint, frozen.products, frozen.package)
                or any(p.media_refs for p in frozen.products)):
            raise ValueError('Graph/source changed')
        manifest = frozen.package.files_manifest
        hashes = {item['path']: item['sha256'] for item in manifest}
        if set(hashes) != ALLOWED_FILES or len(manifest) != 15 or digest(hashes) != frozen.source_digest:
            raise ValueError('Source manifest changed')
        snapshot = frozen.initial_snapshot
        if (snapshot.project_id != frozen.project_id or snapshot.environment != frozen.target.environment
                or digest(snapshot) != frozen.snapshot_hash
                or normalize_snapshot(snapshot.model_dump(mode='json'), snapshot.project_id, snapshot.environment) != snapshot
                or any(frozen.resource_preconditions.get(key) != snapshot.resource_fingerprints.get(source)
                       for key, source in [('theme:muse-storefront', 'theme'), ('settings', 'settings'),
                                           ('navigation:muse-storefront', 'navigation:muse-storefront')])):
            raise ValueError('Initial resource versions differ')
        expected = {'theme:muse-storefront', 'settings', 'navigation:muse-storefront'}
        seen = set()
        for step in frozen.steps:
            if step.kind in {'create_owned_page', 'create_product_draft'}:
                ref = step.resource_ref
                if ref in seen:
                    raise ValueError('Duplicate resource')
                seen.add(ref); expected.add(ref)
                name, identity = ('slug', step.payload['slug']) if step.kind == 'create_owned_page' else (
                    'sku', step.payload['product']['sku'].strip().casefold())
                if frozen.resource_preconditions.get(ref) != digest({name: identity, 'exists': False}):
                    raise ValueError('Missing initial absence')
                validate_operation(ChangeOperation(operation_id=step.key, kind=step.kind, resource_key=ref,
                    expected_fingerprint=frozen.resource_preconditions[ref], payload=step.payload))
        if (set(frozen.resource_preconditions) != expected
                or any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in frozen.resource_preconditions.values())):
            raise ValueError('Unexpected resource dependencies')
        return frozen
    except (ValueError, TypeError, AttributeError, KeyError):
        raise CommerceFailure('REVIEW_STALE') from None


def prepare_site_release(project, plan, target, snapshot, code, absence_proofs, *, connection=None):
    try:
        if plan.blueprint and {'shipping_rules', 'category_navigation'} & plan.blueprint.required_settings.keys():
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
        if (plan.kind != 'build_site' or plan.state not in {'VERIFYING', 'REVIEW_REQUIRED'} or plan.blueprint is None
                or project.id != plan.project_id or project.id != target.project_id or project.id != snapshot.project_id
                or target not in project.environment_refs or target.environment != snapshot.environment
                or plan.snapshot_hash != digest(snapshot)
                or normalize_snapshot(snapshot.model_dump(mode='json'), project.id, snapshot.environment) != snapshot
                or code.project_id != project.id or code.plan_id != plan.id or code.snapshot_hash != plan.snapshot_hash
                or code.package.code_revision != plan.code_revision or code.package.content_sha256 != plan.content_hash
                or snapshot.settings.get('currency') != project.brief.currency
                or snapshot.settings.get('language') != project.brief.language
                or any(p.currency != project.brief.currency for p in plan.products)):
            raise ValueError('Frozen source or shop scope differs')
        if snapshot.theme_identity.get('stylesheet') != 'muse-storefront':
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
        verify_coding_artifact(code)
        preconditions = {'theme:muse-storefront': snapshot.resource_fingerprints['theme'],
                         'settings': snapshot.resource_fingerprints['settings'],
                         'navigation:muse-storefront': snapshot.resource_fingerprints['navigation:muse-storefront']}
        steps = _graph(plan.blueprint, plan.products, code.package)
        expected_proofs = set()
        for step in steps:
            if step.kind not in {'create_owned_page', 'create_product_draft'}:
                continue
            ref = step.resource_ref; expected_proofs.add(ref)
            name, identity = ('slug', step.payload['slug']) if step.kind == 'create_owned_page' else (
                'sku', step.payload['product']['sku'].strip().casefold())
            state = {name: identity, 'exists': False}
            entities = snapshot.pages if name == 'slug' else snapshot.products
            if any((item.get('slug') if name == 'slug' else item.get('sku', '').strip().casefold()) == identity for item in entities):
                raise ValueError('Snapshot contradicts absence')
            proof = absence_proofs.get(ref)
            if (not isinstance(proof, dict) or set(proof) != {'resource_key', 'fingerprint', 'state'}
                    or proof['resource_key'] != ref or proof['state'] != state
                    or proof['state'].get('exists') is not False or proof['fingerprint'] != digest(state)):
                raise ValueError('Absence proof differs')
            preconditions[ref] = proof['fingerprint']
        if set(absence_proofs) != expected_proofs:
            raise ValueError('Unrelated proof')
        intent = SiteReleaseIntent(project_id=project.id, project_revision=project.revision, plan_id=plan.id,
            plan_revision=plan.revision, plan_source_hash=release_source_hash(plan), target=target.model_copy(deep=True),
            snapshot_hash=plan.snapshot_hash, initial_snapshot=snapshot.model_copy(deep=True),
            content_hash=plan.content_hash, source_digest=code.source_digest,
            package=code.package.model_copy(deep=True), blueprint=plan.blueprint.model_copy(deep=True),
            products=[p.model_copy(deep=True) for p in plan.products], steps=steps, resource_preconditions=preconditions, digest='')
        intent.digest = _hash(intent)
        return validate_site_release(intent, connection=connection)
    except CommerceFailure:
        raise
    except (ValueError, TypeError, AttributeError, KeyError):
        raise CommerceFailure('REVIEW_STALE') from None
