import base64
import copy
import io

import pytest
from PIL import Image

from muse.commerce.errors import CommerceFailure
from muse.commerce.media import MediaRepository
from muse.commerce.models import ChangeOperation
from muse.commerce.repository import digest


@pytest.fixture
def image_upload(workflow):
    service, _runtime, plan, _worker = workflow
    project = service.repo.get_project(plan.project_id)
    buffer = io.BytesIO()
    Image.new('RGB', (4, 3), 'purple').save(buffer, format='PNG')
    record = MediaRepository(service.repo).upload(project.id, 'cup.png', 'image/png', buffer.getvalue(), 'image', project.revision)
    state = {'sha256': record.image.sha256, 'exists': False}
    key = 'media-sha256:' + record.image.sha256
    proof = {'resource_key': key, 'fingerprint': digest(state), 'state': state}
    return service.repo, project, record, proof


def test_remote_media_operation_uses_only_clean_project_bytes_and_original_absence_proof(image_upload):
    from muse.commerce_connector.media import prepare_media_operation
    from muse.commerce_connector.operations import validate_operation
    repo, project, record, proof = image_upload
    op = prepare_media_operation(repo, project.id, record.id, proof, 'upload-image')
    assert validate_operation(op) == op
    assert op.kind == 'create_owned_media' and op.resource_key == proof['resource_key']
    assert op.expected_fingerprint == proof['fingerprint']
    assert op.payload['media_ref'] == record.id
    assert op.payload['image'] == {'sha256': record.image.sha256, 'mime_type': 'image/png',
        'byte_size': record.image.byte_size, 'width': 4, 'height': 3}
    content = base64.b64decode(op.payload['content_base64'], validate=True)
    assert content == MediaRepository(repo).content(project.id, record.id)[1]


@pytest.mark.parametrize('attack', ['bytes', 'sha', 'mime', 'size', 'width', 'height', 'extra', 'url', 'path', 'ref', 'resource', 'fingerprint'])
def test_remote_media_closed_contract_rejects_unapproved_content_or_paths(image_upload, attack):
    from muse.commerce_connector.media import prepare_media_operation
    from muse.commerce_connector.operations import validate_operation
    repo, project, record, proof = image_upload
    op = prepare_media_operation(repo, project.id, record.id, proof, 'upload-image')
    if attack == 'bytes': op.payload['content_base64'] = base64.b64encode(b'not an image').decode()
    elif attack == 'sha': op.payload['image']['sha256'] = 'f' * 64
    elif attack == 'mime': op.payload['image']['mime_type'] = 'image/svg+xml'
    elif attack == 'size': op.payload['image']['byte_size'] += 1
    elif attack == 'width': op.payload['image']['width'] = True
    elif attack == 'height': op.payload['image']['height'] = 999
    elif attack == 'extra': op.payload['image']['command'] = 'shell'
    elif attack == 'url': op.payload['source_url'] = 'https://external.test/image.png'
    elif attack == 'path': op.payload['path'] = '../outside.png'
    elif attack == 'ref': op.payload['media_ref'] = '../outside'
    elif attack == 'resource': op.resource_key = 'media-sha256:' + 'f' * 64
    else: op.expected_fingerprint = 'invalid'
    with pytest.raises(CommerceFailure): validate_operation(op)


@pytest.mark.parametrize('attack', ['project', 'missing', 'exists', 'proof_bool', 'proof_hash', 'proof_extra'])
def test_remote_media_factory_requires_project_ownership_and_exact_absence(image_upload, attack):
    from muse.commerce_connector.media import prepare_media_operation
    repo, project, record, original = image_upload
    proof = copy.deepcopy(original)
    project_id, media_id = project.id, record.id
    if attack == 'project': project_id = 'other'
    elif attack == 'missing': media_id = 'f' * 64
    elif attack == 'exists': proof['state']['exists'] = True
    elif attack == 'proof_bool': proof['state']['exists'] = 0
    elif attack == 'proof_hash': proof['fingerprint'] = 'f' * 64
    else: proof['extra'] = True
    with pytest.raises(CommerceFailure): prepare_media_operation(repo, project_id, media_id, proof, 'image')


def test_new_media_operation_does_not_accept_arbitrary_file_write_or_modify_old_media(image_upload):
    from muse.commerce_connector.media import prepare_media_operation
    from muse.commerce_connector.operations import validate_operation
    repo, project, record, proof = image_upload
    op = prepare_media_operation(repo, project.id, record.id, proof, 'image')
    op.payload['overwrite'] = True
    with pytest.raises(CommerceFailure): validate_operation(op)
    with pytest.raises(ValueError):
        ChangeOperation(operation_id='unsafe', kind='write_file', resource_key='path', payload={})
