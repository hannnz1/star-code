import copy

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ProductDraft
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest, validate_operation
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_remote_media import image_upload  # noqa: F401


@pytest.fixture
def uploaded(image_upload):  # noqa: F811
    from muse.commerce_connector.media import prepare_media_operation
    repo, project, record, absent = image_upload
    connection = WordPressConnection('connection', project.id, 'staging', 'https://shop.test', 'fixture', 'fake')
    operation = prepare_media_operation(repo, project.id, record.id, absent, 'upload')
    entity = {**operation.payload['image'], 'id': 42, 'media_ref': record.id,
        'muse_project_id': project.id, 'status': 'inherit', 'parent_id': 0,
        'title': 'MUSE image ' + record.image.sha256, 'alt': ''}
    state = {'sha256': record.image.sha256, 'exists': True, 'attachment': entity}
    proof = {'resource_key': operation.resource_key, 'state': state, 'fingerprint': digest(state)}
    receipt = OperationRecord(project_id=project.id, connection_id='connection', environment='staging',
        operation_id=operation.operation_id, operation_digest=operation_digest(operation),
        resource_key=operation.resource_key, state='SUCCEEDED', fingerprint=digest(state))
    return repo, project, record, connection, operation, receipt, proof


def test_created_image_requires_matched_successful_receipt_and_exact_owned_readback(uploaded):
    from muse.commerce_connector.media import resolve_created_media
    _repo, _project, record, connection, operation, receipt, proof = uploaded
    binding = resolve_created_media(connection, operation, receipt, proof)
    assert binding.media_ref == record.id and binding.id == 42
    assert binding.sha256 == record.image.sha256


@pytest.mark.parametrize('attack', ['unknown', 'scope', 'connection', 'digest', 'fingerprint', 'bytes', 'sha', 'ref', 'owner', 'status', 'parent', 'title', 'alt', 'bool', 'extra'])
def test_created_media_rejects_unproven_or_changed_attachment(uploaded, attack):
    from muse.commerce_connector.media import resolve_created_media
    _repo, _project, _record, connection, operation, receipt, original = uploaded
    proof = copy.deepcopy(original)
    if attack == 'unknown': receipt = receipt.model_copy(update={'state': 'NEEDS_RECONCILIATION'})
    elif attack == 'scope': receipt = receipt.model_copy(update={'project_id': 'other'})
    elif attack == 'connection': receipt = receipt.model_copy(update={'connection_id': 'other'})
    elif attack == 'digest': receipt = receipt.model_copy(update={'operation_digest': 'f' * 64})
    elif attack == 'fingerprint': receipt = receipt.model_copy(update={'fingerprint': 'f' * 64})
    elif attack == 'bool': proof['state']['attachment']['id'] = True
    elif attack == 'extra': proof['state']['attachment']['url'] = 'https://external.test'
    else:
        field, value = {'bytes': ('byte_size', 99), 'sha': ('sha256', 'f' * 64), 'ref': ('media_ref', 'f' * 64),
            'owner': ('muse_project_id', 'other'), 'status': ('status', 'trash'), 'parent': ('parent_id', 3),
            'title': ('title', 'Merchant changed'), 'alt': ('alt', 'Merchant changed')}[attack]
        proof['state']['attachment'][field] = value
    # Even a receipt hash matching changed readback cannot change frozen bytes.
    if attack not in {'fingerprint', 'unknown', 'scope', 'connection', 'digest'}:
        proof['fingerprint'] = digest(proof['state'])
        receipt = receipt.model_copy(update={'fingerprint': proof['fingerprint']})
    with pytest.raises(CommerceFailure): resolve_created_media(connection, operation, receipt, proof)


def test_product_media_factory_binds_exact_uploaded_image_and_original_sku_absence(uploaded):
    from muse.commerce_connector.media import prepare_product_with_media
    repo, project, record, connection, image_operation, receipt, proof = uploaded
    product = ProductDraft(sku='cup', title='Cup', price='10.00', currency='USD', stock=2, media_refs=[record.id])
    state = {'sku': 'cup', 'exists': False}
    sku_proof = {'resource_key': 'sku:' + __import__('hashlib').sha256(b'cup').hexdigest(), 'state': state, 'fingerprint': digest(state)}
    operation = prepare_product_with_media(repo, project.id, product, connection, sku_proof,
        [(image_operation, receipt, proof)], 'create-cup')
    assert validate_operation(operation) == operation
    assert operation.payload['product']['media_refs'] == [record.id]
    assert operation.payload['media_bindings'] == [proof['state']['attachment']]
    assert operation.expected_fingerprint == sku_proof['fingerprint']


@pytest.mark.parametrize('attack', ['missing', 'duplicate', 'scope', 'unlisted', 'replaced_bytes'])
def test_product_images_cannot_be_model_supplied_ids_without_current_creation_evidence(uploaded, attack):
    from muse.commerce_connector.media import prepare_product_with_media
    repo, project, record, connection, operation, receipt, proof = uploaded
    product = ProductDraft(sku='cup', title='Cup', price='10.00', currency='USD', stock=2, media_refs=[record.id])
    state = {'sku': 'cup', 'exists': False}
    sku_proof = {'resource_key': 'sku:' + __import__('hashlib').sha256(b'cup').hexdigest(), 'state': state, 'fingerprint': digest(state)}
    evidence = [(operation, receipt, proof)]
    if attack == 'missing': evidence = []
    elif attack == 'duplicate': evidence *= 2
    elif attack == 'scope': project = project.model_copy(update={'id': 'other'})
    elif attack == 'unlisted': product.media_refs = ['f' * 64]
    else: proof['state']['attachment']['sha256'] = 'f' * 64
    with pytest.raises(CommerceFailure):
        prepare_product_with_media(repo, project.id, product, connection, sku_proof, evidence, 'cup')
