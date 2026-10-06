"""Bind late-created IDs to matched receipts, never to model-supplied references.

This reader grants no permission, updates no approved fingerprint and performs
no network request. The release broker must separately check frozen intent
membership, current merchant approval, target binding, expiry and cancellation.
"""
import re
from dataclasses import dataclass

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation, StoreSnapshot
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest, validate_operation
from muse.commerce_connector.wordpress import WordPressConnection


@dataclass(frozen=True)
class CreatedResource:
    project_id: str
    connection_id: str
    environment: str
    target_digest: str
    entity_id: int
    resource_key: str
    fingerprint: str
    creator_operation_id: str
    creator_operation_digest: str
    creation_fingerprint: str


def resolve_created_resource(connection: WordPressConnection, operation: ChangeOperation, receipt: OperationRecord,
                             proof: dict, snapshot: StoreSnapshot) -> CreatedResource:
    if (not isinstance(connection, WordPressConnection) or not isinstance(operation, ChangeOperation)
            or not isinstance(receipt, OperationRecord) or not isinstance(snapshot, StoreSnapshot)):
        raise CommerceFailure('INPUT_INVALID', 422)
    operation = validate_operation(operation)
    if operation.kind not in {'create_owned_page', 'create_product_draft'}:
        raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
    expected = {'project_id': connection.project_id, 'connection_id': connection.connection_id,
                'environment': connection.environment, 'operation_id': operation.operation_id,
                'operation_digest': operation_digest(operation), 'resource_key': operation.resource_key}
    if (any(getattr(receipt, name) != value for name, value in expected.items()) or receipt.state != 'SUCCEEDED'
            or snapshot.project_id != connection.project_id or snapshot.environment != connection.environment):
        raise CommerceFailure('REVIEW_STALE')
    page = operation.kind == 'create_owned_page'
    identity_key, id_key = ('slug', 'page_id') if page else ('sku', 'product_id')
    identity = operation.payload['slug'] if page else operation.payload['product']['sku'].strip().casefold()
    try:
        if not isinstance(proof, dict) or set(proof) != {'resource_key', 'fingerprint', 'state'}:
            raise ValueError('Invalid resource proof')
        state = proof['state']
        if (not isinstance(state, dict) or set(state) != {identity_key, id_key, 'exists', 'entity_fingerprint'}
                or state[identity_key] != identity or state['exists'] is not True
                or type(state[id_key]) is not int or state[id_key] <= 0
                or not isinstance(state['entity_fingerprint'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', state['entity_fingerprint'])
                or proof['resource_key'] != operation.resource_key or proof['fingerprint'] != digest(state)
                or proof['fingerprint'] != receipt.fingerprint):
            raise ValueError('Creation proof differs from receipt')
        entity_id = state[id_key]
        resource_key = ('page:' if page else 'product:') + str(entity_id)
        entities = [item for item in snapshot.pages if item.get('id') == entity_id] if page else [
            item for item in snapshot.products if item.get('id') == entity_id]
        if (len(entities) != 1 or entities[0].get('muse_project_id') != connection.project_id
                or (entities[0].get('slug') if page else entities[0].get('sku', '').strip().casefold()) != identity
                or digest(entities[0]) != state['entity_fingerprint']
                or snapshot.resource_fingerprints.get(resource_key) != state['entity_fingerprint']):
            raise ValueError('Current entity differs from created version')
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommerceFailure('REVIEW_STALE') from None
    return CreatedResource(connection.project_id, connection.connection_id, connection.environment,
        digest(connection.base_url), entity_id, resource_key, state['entity_fingerprint'],
        operation.operation_id, operation_digest(operation), receipt.fingerprint)
