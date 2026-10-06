"""Frozen product release declarations. Not a merchant approval or write permit.

Generated IDs are symbolic until a matched successful creation receipt binds
them. The trusted verifier/approval broker must independently load persisted
source code, project/plan, preview evidence and the current merchant decision.
"""
import hashlib
import re
from typing import Literal

from pydantic import Field

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    ChangeOperation,
    CommercePlan,
    Contract,
    EnvironmentRef,
    ProductDraft,
    StoreProject,
    StoreSnapshot,
)
from muse.commerce.repository import digest
from muse.commerce_connector.operations import validate_operation
from muse.commerce_connector.wordpress import WordPressConnection


class ProductReleaseStep(Contract):
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,99}$')
    kind: Literal['create_product_draft', 'publish_product']
    resource_ref: str = Field(pattern=r'^sku:[a-f0-9]{64}$')
    depends_on: list[str] = Field(default_factory=list, max_length=1)
    product: ProductDraft | None = None


class ProductReleaseIntent(Contract):
    version: Literal[2] = 2
    project_id: str
    project_revision: int = Field(ge=1)
    plan_id: str
    plan_revision: int = Field(ge=1)
    plan_source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    target: EnvironmentRef
    snapshot_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    code_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    steps: list[ProductReleaseStep] = Field(min_length=2, max_length=40)
    resource_preconditions: dict[str, str]
    digest: str


def _sku_key(product):
    return 'sku:' + hashlib.sha256(product.sku.strip().casefold().encode('utf-8')).hexdigest()


def _intent_hash(intent):
    return digest(intent.model_dump(mode='json', exclude={'digest'}))


def release_source_hash(plan: CommercePlan) -> str:
    """v2 immutable source only; the broker separately fences phase/revision.

    This deliberately does not alter v1 ApprovalRepository's whole-plan binding.
    """
    return digest(plan.model_dump(mode='json', exclude={'state', 'revision', 'error_code'}))


def validate_product_release(intent: ProductReleaseIntent, *, connection: WordPressConnection | None = None) -> ProductReleaseIntent:
    try:
        frozen = ProductReleaseIntent.model_validate(intent.model_dump(mode='json'))
        if connection is None:
            WordPressConnection(frozen.target.connector_ref, frozen.project_id, frozen.target.environment,
                frozen.target.public_url, 'scope-validation-only', 'not-a-credential')
        elif (not isinstance(connection, WordPressConnection) or connection.project_id != frozen.project_id
                or connection.connection_id != frozen.target.connector_ref
                or connection.environment != frozen.target.environment or connection.base_url != frozen.target.public_url):
            raise ValueError('Invalid configured connection')
        if (frozen.target.project_id != frozen.project_id or frozen.digest != _intent_hash(frozen)
                or len(frozen.steps) % 2 or len(frozen.resource_preconditions) != len(frozen.steps) // 2 + 2
                or any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in frozen.resource_preconditions.values())):
            raise ValueError('Invalid release binding')
        seen = set()
        for index in range(0, len(frozen.steps), 2):
            create, publish = frozen.steps[index:index + 2]
            if (create.kind != 'create_product_draft' or publish.kind != 'publish_product' or create.product is None
                    or publish.product is not None or create.depends_on or publish.depends_on != [create.key]
                    or create.key != f'create-product-{index // 2 + 1}' or publish.key != f'publish-product-{index // 2 + 1}'
                    or create.resource_ref != _sku_key(create.product) or publish.resource_ref != create.resource_ref
                    or create.resource_ref in seen):
                raise ValueError('Invalid symbolic graph')
            seen.add(create.resource_ref)
            canonical = create.product.sku.strip().casefold()
            expected = digest({'sku': canonical, 'exists': False})
            if frozen.resource_preconditions.get(create.resource_ref) != expected:
                raise ValueError('Missing initial SKU absence version')
            validate_operation(ChangeOperation(operation_id=create.key, kind='create_product_draft',
                resource_key=create.resource_ref, expected_fingerprint=expected,
                payload={'product': create.product.model_dump(mode='json')}))
        if set(frozen.resource_preconditions) != seen | {'theme:muse-storefront', 'settings'}:
            raise ValueError('Unexpected dependencies')
        return frozen
    except CommerceFailure:
        raise
    except (ValueError, TypeError, AttributeError):
        raise CommerceFailure('REVIEW_STALE') from None


def prepare_product_release(project: StoreProject, plan: CommercePlan, target: EnvironmentRef,
                            snapshot: StoreSnapshot, sku_proofs: dict, *,
                            connection: WordPressConnection | None = None) -> ProductReleaseIntent:
    if (not isinstance(project, StoreProject) or not isinstance(plan, CommercePlan)
            or not isinstance(target, EnvironmentRef) or not isinstance(snapshot, StoreSnapshot)):
        raise CommerceFailure('INPUT_INVALID', 422)
    if (plan.kind != 'launch_products' or plan.state not in {'VERIFYING', 'REVIEW_REQUIRED'} or not plan.products
            or plan.blueprint is None or plan.code_revision is None):
        raise CommerceFailure('FACTS_INCOMPLETE', 422)
    if (project.id != plan.project_id or project.id != target.project_id or project.id != snapshot.project_id
            or target not in project.environment_refs or target.environment != snapshot.environment
            or plan.snapshot_hash != digest(snapshot)
            or plan.content_hash != digest({'blueprint': plan.blueprint.model_dump(mode='json'),
                'products': [p.model_dump(mode='json') for p in plan.products]})):
        raise CommerceFailure('REVIEW_STALE')
    normalized = normalize_snapshot(snapshot.model_dump(mode='json'), snapshot.project_id, snapshot.environment)
    if normalized != snapshot:
        raise CommerceFailure('REVIEW_STALE')
    if snapshot.theme_identity.get('stylesheet') != 'muse-storefront':
        raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
    if (snapshot.settings.get('currency') != project.brief.currency
            or any(product.currency != project.brief.currency for product in plan.products)):
        raise CommerceFailure('FACTS_INCOMPLETE', 422)
    preconditions = {'theme:muse-storefront': snapshot.resource_fingerprints['theme'],
                     'settings': snapshot.resource_fingerprints['settings']}
    steps = []
    for index, product in enumerate(plan.products, 1):
        if product.media_refs:
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
        key = _sku_key(product)
        state = {'sku': product.sku.strip().casefold(), 'exists': False}
        proof = sku_proofs.get(key) if isinstance(sku_proofs, dict) else None
        if (not isinstance(proof, dict) or set(proof) != {'resource_key', 'fingerprint', 'state'}
                or proof['resource_key'] != key or proof['state'] != state
                or not isinstance(proof['state'], dict) or proof['state'].get('exists') is not False
                or proof['fingerprint'] != digest(state)):
            raise CommerceFailure('REVIEW_STALE')
        preconditions[key] = proof['fingerprint']
        create = ProductReleaseStep(key=f'create-product-{index}', kind='create_product_draft', resource_ref=key,
                                    product=product.model_copy(deep=True))
        steps.extend([create, ProductReleaseStep(key=f'publish-product-{index}', kind='publish_product',
                                                resource_ref=key, depends_on=[create.key])])
    if set(sku_proofs) != set(preconditions) - {'theme:muse-storefront', 'settings'}:
        raise CommerceFailure('REVIEW_STALE')
    intent = ProductReleaseIntent(project_id=project.id, project_revision=project.revision, plan_id=plan.id,
        plan_revision=plan.revision, plan_source_hash=release_source_hash(plan), target=target.model_copy(deep=True),
        snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash, code_revision=plan.code_revision,
        steps=steps, resource_preconditions=preconditions, digest='')
    intent.digest = _intent_hash(intent)
    return validate_product_release(intent, connection=connection)
