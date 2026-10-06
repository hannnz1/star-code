"""Deterministic product steps from frozen intent and authenticated receipt history.

This module performs no approval, signing or network IO. Callers must persist
authenticated outcomes and independently load current source/merchant authority.
"""
import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation, StoreSnapshot
from muse.commerce.release import ProductReleaseIntent, validate_product_release
from muse.commerce.release_resources import resolve_created_resource
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest, validate_operation
from muse.commerce_connector.wordpress import WordPressConnection


@dataclass
class CompletedProductStep:
    operation: ChangeOperation
    receipt: OperationRecord
    snapshot: StoreSnapshot
    proof: dict


@dataclass(frozen=True)
class ProductStepProjection:
    root_digest: str
    index: int
    key: str
    operation: ChangeOperation
    preconditions: dict[str, str]
    sku_identities: dict[str, str]


def _snapshot(intent, snapshot):
    if (not isinstance(snapshot, StoreSnapshot) or snapshot.project_id != intent.project_id
            or snapshot.environment != intent.target.environment
            or normalize_snapshot(snapshot.model_dump(mode='json'), snapshot.project_id, snapshot.environment) != snapshot
            or snapshot.resource_fingerprints.get('theme') != intent.resource_preconditions['theme:muse-storefront']
            or snapshot.resource_fingerprints.get('settings') != intent.resource_preconditions['settings']):
        raise CommerceFailure('REVIEW_STALE')


def _operation(intent, index, bindings):
    step = intent.steps[index]
    if step.kind == 'create_product_draft':
        key = step.resource_ref
        payload = {'product': step.product.model_dump(mode='json')}
        fingerprint = intent.resource_preconditions[key]
    else:
        entity, fingerprint = bindings[step.resource_ref]
        key = f'product:{entity["id"]}'
        payload = {'product_id': entity['id']}
    return validate_operation(ChangeOperation(operation_id=f'release-{intent.digest}-{index}', kind=step.kind,
        resource_key=key, expected_fingerprint=fingerprint, payload=payload))


def _entity(snapshot, identity):
    matches = [item for item in snapshot.products if item.get('id') == identity]
    if len(matches) != 1:
        raise CommerceFailure('REVIEW_STALE')
    return matches[0]


def _approved_product_facts(product, entity):
    """Check business facts independently of the connector's success fingerprint."""
    try:
        prices_match = (Decimal(entity.get('price', '')) == Decimal(product.price)
                        and Decimal(entity.get('regular_price', entity.get('price', ''))) == Decimal(product.price))
    except (InvalidOperation, TypeError, ValueError):
        prices_match = False
    categories = entity.get('categories', [])
    category_matches = not product.category or (
        isinstance(categories, list) and len(categories) == 1 and isinstance(categories[0], dict)
        and set(categories[0]) in ({'id', 'name'}, {'id', 'name', 'slug', 'url'}) and type(categories[0]['id']) is int
        and categories[0]['id'] > 0 and categories[0]['name'] == product.category
        and entity.get('category_ids') == [categories[0]['id']])
    if (not prices_match or entity.get('sku') != product.sku
            or not category_matches
            or entity.get('name') != product.title
            or type(entity.get('stock_quantity')) is not int or entity['stock_quantity'] != product.stock
            or entity.get('description', '') != product.description
            or entity.get('type', 'simple') != 'simple'
            or entity.get('manage_stock', True) is not True
            or entity.get('sale_price', '') != '' or entity.get('backorders', 'no') != 'no'):
        raise CommerceFailure('REVIEW_STALE')
    visibility='hidden' if product.source_facts.get('crew_preview_seed')=='category' else 'visible'
    if (visibility == 'hidden' and entity.get('catalog_visibility') != 'hidden'
            or 'catalog_visibility' in entity and entity['catalog_visibility']!=visibility):
        raise CommerceFailure('REVIEW_STALE')


def _product_projection(intent: ProductReleaseIntent, connection: WordPressConnection, index: int,
                         history: list[CompletedProductStep], snapshot: StoreSnapshot,
                         sku_proofs: dict, *, complete=False):
    """Only exact terminal predecessors may substitute their own resource versions."""
    intent = validate_product_release(intent, connection=connection)
    if (not isinstance(connection, WordPressConnection) or type(index) is not int
            or not 0 <= index < len(intent.steps) + (1 if complete else 0)
            or (complete and index != len(intent.steps))
            or not isinstance(history, list) or len(history) != index
            or connection.project_id != intent.project_id or connection.environment != intent.target.environment
            or connection.connection_id != intent.target.connector_ref or connection.base_url != intent.target.public_url):
        raise CommerceFailure('REVIEW_STALE')
    _snapshot(intent, snapshot)
    bindings = {}
    for position, outcome in enumerate(copy.deepcopy(history)):
        if not isinstance(outcome, CompletedProductStep):
            raise CommerceFailure('REVIEW_STALE')
        expected = _operation(intent, position, bindings)
        receipt = outcome.receipt
        if (operation_digest(outcome.operation) != operation_digest(expected)
                or not isinstance(receipt, OperationRecord) or receipt.state != 'SUCCEEDED'
                or receipt.operation_id != expected.operation_id or receipt.operation_digest != operation_digest(expected)
                or receipt.project_id != connection.project_id or receipt.connection_id != connection.connection_id
                or receipt.environment != connection.environment or receipt.resource_key != expected.resource_key):
            raise CommerceFailure('REVIEW_STALE')
        _snapshot(intent, outcome.snapshot)
        ref = intent.steps[position].resource_ref
        if expected.kind == 'create_product_draft':
            created = resolve_created_resource(connection, expected, receipt, outcome.proof, outcome.snapshot)
            entity = _entity(outcome.snapshot, created.entity_id)
            _approved_product_facts(intent.steps[position].product, entity)
            bindings[ref] = (entity, created.fingerprint)
        else:
            previous, _ = bindings[ref]
            entity = _entity(outcome.snapshot, previous['id'])
            published = {**previous, 'status': 'publish'}
            if entity != published or receipt.fingerprint != digest(entity):
                raise CommerceFailure('REVIEW_STALE')
            bindings[ref] = (entity, receipt.fingerprint)
        # No prior effect may have been silently changed by this later operation.
        for bound, fingerprint in bindings.values():
            if (_entity(outcome.snapshot, bound['id']) != bound
                    or outcome.snapshot.resource_fingerprints.get(f'product:{bound["id"]}') != fingerprint):
                raise CommerceFailure('REVIEW_STALE')
    aliases = {step.resource_ref for step in intent.steps}
    if not isinstance(sku_proofs, dict) or set(sku_proofs) != aliases:
        raise CommerceFailure('REVIEW_STALE')
    preconditions = {key: value for key, value in intent.resource_preconditions.items() if not key.startswith('sku:')}
    for step in intent.steps[::2]:
        ref = step.resource_ref
        state = {'sku': step.product.sku.strip().casefold(), 'exists': False}
        if ref in bindings:
            entity, fingerprint = bindings[ref]
            if (_entity(snapshot, entity['id']) != entity
                    or snapshot.resource_fingerprints.get(f'product:{entity["id"]}') != fingerprint):
                raise CommerceFailure('REVIEW_STALE')
            state = {'sku': step.product.sku.strip().casefold(), 'exists': True,
                     'product_id': entity['id'], 'entity_fingerprint': fingerprint}
            preconditions[f'product:{entity["id"]}'] = fingerprint
        else:
            preconditions[ref] = intent.resource_preconditions[ref]
        proof = sku_proofs[ref]
        if (not isinstance(proof, dict) or set(proof) != {'resource_key', 'fingerprint', 'state'}
                or proof['resource_key'] != ref or proof['state'] != state
                or not isinstance(proof['state'], dict) or proof['state'].get('exists') is not state['exists']
                or proof['fingerprint'] != digest(state)
                or ('product_id' in state and type(proof['state'].get('product_id')) is not int)):
            raise CommerceFailure('REVIEW_STALE')
    if complete:
        return preconditions
    operation = _operation(intent, index, bindings)
    identities = {step.resource_ref: step.product.sku.strip().casefold()
                  for step in intent.steps[::2] if step.resource_ref not in bindings}
    return ProductStepProjection(intent.digest, index, intent.steps[index].key, operation, preconditions, identities)


def project_product_step(intent: ProductReleaseIntent, connection: WordPressConnection, index: int,
                         history: list[CompletedProductStep], snapshot: StoreSnapshot, sku_proofs: dict) -> ProductStepProjection:
    return _product_projection(intent, connection, index, history, snapshot, sku_proofs)


def validate_product_completion(intent: ProductReleaseIntent, connection: WordPressConnection,
                                history: list[CompletedProductStep], snapshot: StoreSnapshot, sku_proofs: dict) -> dict[str, str]:
    """Validate a terminal readback; it grants no permission or further operation."""
    return _product_projection(intent, connection, len(intent.steps), history, snapshot, sku_proofs, complete=True)
