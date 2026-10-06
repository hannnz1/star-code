import copy

import pytest

from muse.commerce_connector.media import prepare_media_operation
from tests.muse.commerce.test_php_protocol import php, run  # noqa: F401
from tests.muse.commerce.test_remote_media import image_upload  # noqa: F401


def wire(fixture):
    repo, project, record, proof = fixture
    operation = prepare_media_operation(repo, project.id, record.id, proof, 'image')
    return {'mode': 'media', 'project_id': project.id, 'operation': operation.model_dump(mode='json')}


def test_php_accepts_exact_scoped_image_metadata_and_bytes(php, image_upload):  # noqa: F811
    assert run(php, wire(image_upload)) == {'accepted': True}


@pytest.mark.parametrize('attack', ['bytes', 'sha', 'mime', 'size', 'width', 'height', 'extra', 'url', 'path', 'ref', 'scope', 'resource'])
def test_php_rejects_scoped_media_contract_tampering(php, image_upload, attack):  # noqa: F811
    value = copy.deepcopy(wire(image_upload))
    payload = value['operation']['payload']
    if attack == 'bytes': payload['content_base64'] = 'bm90IGFuIGltYWdl'
    elif attack == 'sha': payload['image']['sha256'] = 'f' * 64
    elif attack == 'mime': payload['image']['mime_type'] = 'image/svg+xml'
    elif attack == 'size': payload['image']['byte_size'] += 1
    elif attack == 'width': payload['image']['width'] = True
    elif attack == 'height': payload['image']['height'] = 999
    elif attack == 'extra': payload['image']['command'] = 'shell'
    elif attack == 'url': payload['source_url'] = 'https://external.test/image.png'
    elif attack == 'path': payload['path'] = '../outside.png'
    elif attack == 'ref': payload['media_ref'] = 'f' * 64
    elif attack == 'scope': value['project_id'] = 'other'
    else: value['operation']['resource_key'] = 'media-sha256:' + 'f' * 64
    assert run(php, value) == {'accepted': False}
