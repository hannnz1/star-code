import copy

import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.release import prepare_product_release
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_release_intent import product_release_inputs


def inputs():
    args = product_release_inputs()
    intent = prepare_product_release(*args)
    connection = WordPressConnection('connection', 'project', 'staging', 'https://shop.test', 'service', 'fixture')
    return intent, connection, args[3], args[4]


def creation():
    from muse.commerce.release_steps import CompletedProductStep, project_product_step
    intent, connection, before, absent = inputs()
    first = project_product_step(intent, connection, 0, [], before, absent)
    entity = {'id': 21, 'sku': 'CUP', 'name': 'Cup', 'price': '10.00', 'stock_quantity': 3,
              'status': 'draft', 'muse_project_id': 'project'}
    wire = before.model_dump(mode='json')
    wire['products'] = [entity]
    after = normalize_snapshot(wire, 'project', 'staging')
    state = {'sku': 'cup', 'exists': True, 'product_id': 21, 'entity_fingerprint': after.resource_fingerprints['product:21']}
    key = intent.steps[0].resource_ref
    proof = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    receipt = OperationRecord(project_id='project', connection_id='connection', environment='staging',
        operation_id=first.operation.operation_id, operation_digest=operation_digest(first.operation),
        resource_key=key, state='SUCCEEDED', fingerprint=proof['fingerprint'])
    done = CompletedProductStep(operation=first.operation, receipt=receipt, snapshot=after, proof=proof)
    return intent, connection, after, {key: proof}, done


def test_first_step_preserves_root_conditions_and_fixed_product_facts():
    from muse.commerce.release_steps import project_product_step
    intent, connection, snapshot, proofs = inputs()
    step = project_product_step(intent, connection, 0, [], snapshot, proofs)
    assert step.operation.payload['product'] == intent.steps[0].product.model_dump(mode='json')
    assert step.preconditions == intent.resource_preconditions
    assert step.operation.operation_id == f'release-{intent.digest}-0'
    assert step.root_digest == intent.digest and step.index == 0
    intent.steps[0].product.title = 'Mutated'
    assert step.operation.payload['product']['title'] == 'Cup'


def test_publish_uses_only_matched_created_id_and_unchanged_root_dependencies():
    from muse.commerce.release_steps import project_product_step
    intent, connection, snapshot, proofs, done = creation()
    step = project_product_step(intent, connection, 1, [done], snapshot, proofs)
    assert step.operation.payload == {'product_id': 21}
    assert step.operation.resource_key == 'product:21'
    assert step.operation.expected_fingerprint == snapshot.resource_fingerprints['product:21']
    assert step.preconditions == {**{k: v for k, v in intent.resource_preconditions.items() if not k.startswith('sku:')},
                                  'product:21': snapshot.resource_fingerprints['product:21']}


@pytest.mark.parametrize('change', ['unknown', 'failed', 'receipt_digest', 'receipt_scope', 'operation',
    'manual_edit', 'theme', 'settings', 'target', 'out_of_order', 'index_bool', 'proof_missing', 'proof_edited'])
def test_projection_refuses_unproven_predecessors_or_changed_dependencies(change):
    from muse.commerce.release_steps import project_product_step
    intent, connection, snapshot, proofs, done = creation()
    done = copy.deepcopy(done)
    index, history = 1, [done]
    if change in {'unknown', 'failed'}:
        done.receipt = done.receipt.model_copy(update={'state': 'FAILED' if change == 'failed' else 'NEEDS_RECONCILIATION'})
    elif change == 'receipt_digest':
        done.receipt = done.receipt.model_copy(update={'operation_digest': 'a' * 64})
    elif change == 'receipt_scope':
        done.receipt = done.receipt.model_copy(update={'connection_id': 'other'})
    elif change == 'operation':
        done.operation.payload['product']['title'] = 'Unapproved'
    elif change == 'manual_edit':
        snapshot.products[0]['name'] = 'Merchant edit'
        snapshot.resource_fingerprints['product:21'] = digest(snapshot.products[0])
    elif change == 'theme':
        snapshot.theme_identity['version'] = 'merchant-edit'
        snapshot.resource_fingerprints['theme'] = digest(snapshot.theme_identity)
    elif change == 'settings':
        snapshot.settings['currency'] = 'EUR'
        snapshot.resource_fingerprints['settings'] = digest(snapshot.settings)
    elif change == 'target':
        connection = WordPressConnection('connection', 'project', 'staging', 'https://other.test', 'service', 'fixture')
    elif change == 'out_of_order':
        history = []
    elif change == 'index_bool':
        index = True
    elif change == 'proof_missing':
        proofs = {}
    else:
        proofs[next(iter(proofs))]['state']['product_id'] = 99
    with pytest.raises(CommerceFailure):
        project_product_step(intent, connection, index, history, snapshot, proofs)


def published_history():
    from muse.commerce.release_steps import CompletedProductStep, project_product_step
    intent, connection, snapshot, proofs, created = creation()
    projected = project_product_step(intent, connection, 1, [created], snapshot, proofs)
    wire = copy.deepcopy(snapshot.model_dump(mode='json'))
    wire['products'][0]['status'] = 'publish'
    published = normalize_snapshot(wire, 'project', 'staging')
    state = {**next(iter(proofs.values()))['state'], 'entity_fingerprint': published.resource_fingerprints['product:21']}
    key = intent.steps[0].resource_ref
    proof = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    receipt = OperationRecord(project_id='project', connection_id='connection', environment='staging',
        operation_id=projected.operation.operation_id, operation_digest=operation_digest(projected.operation),
        resource_key='product:21', state='SUCCEEDED', fingerprint=published.resource_fingerprints['product:21'])
    done = CompletedProductStep(projected.operation, receipt, published, proof)
    return intent, connection, [created, done], published, {key: proof}


def test_complete_history_checks_all_effects_without_minting_an_extra_operation():
    from muse.commerce.release_steps import (
        project_product_step,
        validate_product_completion,
    )
    args = published_history()
    assert validate_product_completion(*args) == {**{k: v for k, v in args[0].resource_preconditions.items()
        if not k.startswith('sku:')}, 'product:21': args[-2].resource_fingerprints['product:21']}
    with pytest.raises(CommerceFailure):
        project_product_step(args[0], args[1], 2, args[2], args[3], args[4])


@pytest.mark.parametrize('change', ['incomplete', 'price', 'unknown', 'extra'])
def test_completion_cannot_hide_unknown_extra_or_unapproved_price_change(change):
    from muse.commerce.release_steps import validate_product_completion
    intent, connection, history, snapshot, proofs = published_history()
    if change == 'incomplete': history.pop()
    elif change == 'extra': history.append(history[-1])
    elif change == 'unknown': history[-1].receipt = history[-1].receipt.model_copy(update={'state': 'NEEDS_RECONCILIATION'})
    else:
        history[-1].snapshot = copy.deepcopy(history[-1].snapshot)
        history[-1].snapshot.products[0]['price'] = '15.00'
        history[-1].snapshot.resource_fingerprints['product:21'] = digest(history[-1].snapshot.products[0])
    with pytest.raises(CommerceFailure): validate_product_completion(intent, connection, history, snapshot, proofs)


@pytest.mark.parametrize('field,value', [('name', 'Hook changed title'), ('price', '19.99'), ('stock_quantity', 0),
    ('description', 'New unsupported claim'), ('type', 'variable'), ('manage_stock', False),
    ('regular_price', '20.00'), ('sale_price', '10.00'), ('backorders', 'yes')])
def test_matching_success_receipt_cannot_approve_source_facts_changed_inside_create(field, value):
    from muse.commerce.release_steps import project_product_step
    intent, connection, snapshot, _proofs, done = creation()
    snapshot.products[0][field] = value
    snapshot.resource_fingerprints['product:21'] = digest(snapshot.products[0])
    state = {**done.proof['state'], 'entity_fingerprint': snapshot.resource_fingerprints['product:21']}
    proof = {'resource_key': done.operation.resource_key, 'state': state, 'fingerprint': digest(state)}
    done.proof = proof
    done.receipt = done.receipt.model_copy(update={'fingerprint': proof['fingerprint']})
    with pytest.raises(CommerceFailure):
        project_product_step(intent, connection, 1, [done], snapshot, {proof['resource_key']: proof})
