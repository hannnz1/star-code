import base64
import io
import zipfile

import pytest
from PIL import Image

from muse.commerce.coding import SourceStore
from muse.commerce.context import normalize_snapshot
from muse.commerce.repository import digest
from muse.commerce_connector.media import MediaPayload
from tests.muse.commerce.test_coding_artifact import archive
from tests.muse.commerce.test_preview_capture import preview_site  # noqa: F401
from tests.muse.commerce.test_release_approval import product_review  # noqa: F401
from tests.muse.commerce.test_staging_verification import stage  # noqa: F401


@pytest.fixture
def preview_media_site(preview_site, tmp_path):  # noqa: F811
    import hashlib
    plan, original_code, snapshot, connection, data = preview_site
    buffer = io.BytesIO(); Image.new('RGB', (12, 12), 'green').save(buffer, format='PNG')
    content = buffer.getvalue(); sha = hashlib.sha256(content).hexdigest(); media_ref = digest([plan.project_id, 'image', sha])
    image = MediaPayload(media_ref=media_ref, content_base64=base64.b64encode(content).decode(), image={
        'sha256': sha, 'mime_type': 'image/png', 'byte_size': len(content), 'width': 12, 'height': 12})
    plan.products[0].media_refs = [media_ref]
    plan.content_hash = digest({'blueprint': plan.blueprint.model_dump(mode='json'), 'products': [p.model_dump(mode='json') for p in plan.products]})
    with zipfile.ZipFile(io.BytesIO(original_code.archive)) as package:
        files = {name.removeprefix('muse-storefront/'): package.read(name) for name in package.namelist()}
    code = SourceStore(tmp_path / 'media-code').seal(archive(files), project_id=plan.project_id, plan_id=plan.id,
        snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    snapshot.products[0]['image_id'] = 301
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging')
    entity = {**image.image.model_dump(), 'id': 301, 'media_ref': media_ref, 'muse_project_id': plan.project_id,
        'status': 'inherit', 'parent_id': 0, 'title': 'MUSE image ' + sha, 'alt': ''}
    state = {'sha256': sha, 'exists': True, 'attachment': entity}; key = 'media-sha256:' + sha
    proofs = {key: {'resource_key': key, 'state': state, 'fingerprint': digest(state)}}
    data['media_path'] = '/wp-content/uploads/muse-owned/' + plan.project_id + '/' + sha + '.png'
    data['media_bytes'] = content
    return plan, code, snapshot, connection, data, [image], proofs


@pytest.mark.asyncio
async def test_preview_checks_approved_image_is_loaded_and_visible_at_three_widths(preview_media_site):
    from muse.commerce.preview import capture_staging_preview
    plan, code, snapshot, connection, _data, images, proofs = preview_media_site
    result = await capture_staging_preview(plan, code, snapshot, connection, images=images, media_proofs=proofs)
    assert result.passed and result.site_verified is False and len(result.frames) == 21


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['broken_image', 'hidden_image'])
async def test_preview_rejects_broken_or_hidden_approved_product_images(preview_media_site, mode):
    from muse.commerce.preview import capture_staging_preview
    plan, code, snapshot, connection, data, images, proofs = preview_media_site
    data['mode'] = mode
    result = await capture_staging_preview(plan, code, snapshot, connection, images=images, media_proofs=proofs)
    assert result.passed is False and result.site_verified is False
    assert result.checks['pages'] is False and any(item.startswith('PRODUCT_IMAGE_FAILED') for item in result.diagnostics)
