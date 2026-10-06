import io

import pytest
from PIL import Image

from tests.muse.commerce.test_project_api import request

pytest_plugins = ['tests.muse.commerce.test_project_api']


def picture(color='red'):
    output = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(output, 'PNG')
    return output.getvalue()


def project(client, key='shop-one'):
    return client.post('/api/commerce/projects', json=request(client, key)).json()


def upload(client, record, data=None, *, name='cup.png', key='upload-one'):
    return client.post(f"/api/commerce/projects/{record['id']}/media",
        params={'name': name, 'client_request_id': key, 'expected_revision': record['revision']},
        content=picture() if data is None else data, headers={'Content-Type': 'image/png'})


def test_validated_image_is_durable_scoped_and_available_to_csv(client):
    record = project(client)
    response = upload(client, record)
    assert response.status_code == 201, response.text
    media = response.json()
    assert media['image']['name'] == 'cup.png'
    assert media['width'] == 8 and media['height'] == 8
    assert 'content' not in media and 'storage_path' not in media
    assert upload(client, record).json() == media
    listed = client.get(f"/api/commerce/projects/{record['id']}/media").json()
    assert listed == [media]
    content = client.get(f"/api/commerce/projects/{record['id']}/media/{media['id']}/content")
    assert content.status_code == 200 and content.headers['content-type'] == 'image/png'
    assert content.headers['x-content-type-options'] == 'nosniff'
    Image.open(io.BytesIO(content.content)).load()
    csv = 'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,19.99,USD,3,Cups,Ceramic,cup.png'
    imported = client.post(f"/api/commerce/projects/{record['id']}/product-imports", json={
        'expected_revision': record['revision'], 'client_request_id': 'batch-one', 'csv_text': csv, 'media_ids': [media['id']]})
    assert imported.status_code == 201, imported.text
    assert imported.json()['result']['drafts'][0]['media_refs'] == [media['image']['artifact_ref']]
    assert client.get('/api/tasks').json() == []
    import base64
    import json
    import zipfile
    exported = client.get(f"/api/commerce/projects/{record['id']}/export?revision=1").json()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['archive_base64']))) as archive:
        entries = json.loads(archive.read('media.json'))
        assert entries[0]['media_id'] == media['id']
        assert archive.read(entries[0]['path']) == content.content
        assert json.loads(archive.read('project.json'))['format_version'] == 2


@pytest.mark.parametrize('data,name', [(b'<svg onload="alert(1)"></svg>', 'fake.png'),
                                     (b'not an image', '../cup.png'), (picture()[:20], 'short.png')])
def test_bad_images_leave_no_media_records(client, data, name):
    record = project(client)
    assert upload(client, record, data, name=name).status_code == 422
    assert client.get(f"/api/commerce/projects/{record['id']}/media").json() == []


def test_upload_request_and_filename_cannot_be_rebound_to_different_bytes(client):
    record = project(client)
    first = upload(client, record).json()
    assert upload(client, record, picture('blue')).status_code == 409
    assert upload(client, record, picture('blue'), key='other-upload').status_code == 409
    duplicate = upload(client, record, key='duplicate-upload')
    assert duplicate.status_code == 201 and duplicate.json()['id'] == first['id']
    assert len(client.get(f"/api/commerce/projects/{record['id']}/media").json()) == 1


def test_media_cannot_be_read_or_imported_from_another_project(client):
    first, second = project(client), project(client, 'shop-two')
    media = upload(client, first).json()
    assert client.get(f"/api/commerce/projects/{second['id']}/media/{media['id']}/content").status_code == 404
    csv = 'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,19.99,USD,3,Cups,Ceramic,cup.png'
    result = client.post(f"/api/commerce/projects/{second['id']}/product-imports", json={
        'expected_revision': 1, 'client_request_id': 'batch', 'csv_text': csv, 'media_ids': [media['id']]})
    assert result.status_code == 404


def test_stale_revision_cannot_upload_and_original_metadata_is_stripped(client):
    record = project(client)
    from PIL.PngImagePlugin import PngInfo
    metadata = PngInfo(); metadata.add_text('private_fixture', 'should-not-survive')
    output = io.BytesIO(); Image.new('RGB', (8, 8), 'green').save(output, 'PNG', pnginfo=metadata)
    media = upload(client, record, output.getvalue()).json()
    response = client.get(f"/api/commerce/projects/{record['id']}/media/{media['id']}/content")
    assert b'should-not-survive' not in response.content
    client.patch(f"/api/commerce/projects/{record['id']}", json={'expected_revision': 1, 'brief': {**record['brief'], 'style': 'New'}})
    assert upload(client, record, key='after-edit').status_code == 409
