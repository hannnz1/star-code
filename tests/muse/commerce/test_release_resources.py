from copy import deepcopy

import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest
from muse.commerce_connector.wordpress import WordPressConnection


def created_page():
    import hashlib
    connection = WordPressConnection('connection', 'project', 'staging', 'https://shop.test', 'service', 'test-password')
    key = 'page-slug:' + hashlib.sha256(b'home').hexdigest()
    operation = ChangeOperation(operation_id='create-home', kind='create_owned_page', resource_key=key,
        expected_fingerprint=digest({'slug': 'home', 'exists': False}),
        payload={'slug': 'home', 'title': 'Home', 'content': 'Merchant text', 'template': 'page'})
    snapshot = normalize_snapshot({'pages': [{'id': 8, 'slug': 'home', 'title': 'Home', 'content': 'Merchant text',
        'status': 'draft', 'muse_project_id': 'project', 'template': 'default'}], 'products': [],
        'settings': {'currency': 'USD', 'language': 'en-US'},
        'theme_identity': {'stylesheet': 'muse-storefront', 'effective_templates': [], 'global_styles': {'styles': {}}}},
        'project', 'staging')
    state = {'slug': 'home', 'exists': True, 'page_id': 8, 'entity_fingerprint': snapshot.resource_fingerprints['page:8']}
    proof = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    receipt = OperationRecord(project_id='project', connection_id='connection', environment='staging',
        operation_id=operation.operation_id, operation_digest=operation_digest(operation), resource_key=key,
        state='SUCCEEDED', fingerprint=proof['fingerprint'])
    return connection, operation, receipt, proof, snapshot


def test_created_page_is_bound_to_success_receipt_and_exact_current_owned_entity():
    from muse.commerce.release_resources import resolve_created_resource
    inputs = created_page()
    bound = resolve_created_resource(*inputs)
    assert bound.resource_key == 'page:8'
    assert bound.entity_id == 8
    assert bound.fingerprint == inputs[-1].resource_fingerprints['page:8']
    assert bound.creator_operation_digest == operation_digest(inputs[1])
    assert bound.creation_fingerprint == inputs[2].fingerprint


def test_created_product_uses_canonical_sku_and_receipt_entity_version():
    import hashlib

    from muse.commerce.release_resources import resolve_created_resource
    connection, _, _, _, original = created_page()
    canonical = 'cup-ss'
    key = 'sku:' + hashlib.sha256(canonical.encode()).hexdigest()
    facts = {'sku': 'CUP-ß', 'title': 'Cup', 'price': '10.00', 'currency': 'USD', 'stock': 3,
             'description': '', 'category': '', 'source_facts': {}, 'media_refs': []}
    operation = ChangeOperation(operation_id='create-cup', kind='create_product_draft', resource_key=key,
        expected_fingerprint=digest({'sku': canonical, 'exists': False}), payload={'product': facts})
    entity = {'id': 12, 'sku': 'CUP-ß', 'name': 'Cup', 'price': '10.00', 'stock_quantity': 3,
              'status': 'draft', 'muse_project_id': 'project'}
    fingerprint = digest(entity)
    snapshot = original.model_copy(update={'pages': [], 'products': [entity], 'resource_fingerprints': {'product:12': fingerprint}})
    state = {'sku': canonical, 'exists': True, 'product_id': 12, 'entity_fingerprint': fingerprint}
    proof = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    receipt = OperationRecord(project_id='project', connection_id='connection', environment='staging',
        operation_id=operation.operation_id, operation_digest=operation_digest(operation), resource_key=key,
        state='SUCCEEDED', fingerprint=proof['fingerprint'])
    bound = resolve_created_resource(connection, operation, receipt, proof, snapshot)
    assert bound.resource_key == 'product:12' and bound.fingerprint == fingerprint


@pytest.mark.parametrize('field,value', [('state', 'FAILED'), ('state', 'NEEDS_RECONCILIATION'),
    ('project_id', 'other'), ('connection_id', 'other'), ('environment', 'live'),
    ('operation_id', 'another-create'), ('operation_digest', 'a' * 64), ('fingerprint', 'a' * 64)])
def test_nonmatching_or_nonterminal_creation_receipt_cannot_supply_followup_id(field, value):
    from muse.commerce.release_resources import resolve_created_resource
    connection, operation, receipt, proof, snapshot = created_page()
    with pytest.raises(CommerceFailure):
        resolve_created_resource(connection, operation, receipt.model_copy(update={field: value}), proof, snapshot)


@pytest.mark.parametrize('change', ['edited_entity', 'updated_proof', 'missing_entity_version', 'extra_key', 'boolean_id', 'wrong_owner'])
def test_creation_binding_rejects_manual_changes_old_proofs_and_wrong_owner(change):
    from muse.commerce.release_resources import resolve_created_resource
    connection, operation, receipt, proof, snapshot = created_page()
    proof = deepcopy(proof)
    if change == 'edited_entity':
        snapshot.pages[0]['content'] = 'Merchant edited'
        snapshot.resource_fingerprints['page:8'] = digest(snapshot.pages[0])
    elif change == 'updated_proof':
        proof['state']['entity_fingerprint'] = 'b' * 64
        proof['fingerprint'] = digest(proof['state'])
    elif change == 'missing_entity_version':
        del proof['state']['entity_fingerprint']
        proof['fingerprint'] = digest(proof['state'])
    elif change == 'extra_key':
        proof['authority'] = 'approved'
    elif change == 'boolean_id':
        proof['state']['page_id'] = True
        proof['fingerprint'] = digest(proof['state'])
    else:
        snapshot.pages[0]['muse_project_id'] = 'other'
    with pytest.raises(CommerceFailure):
        resolve_created_resource(connection, operation, receipt, proof, snapshot)
