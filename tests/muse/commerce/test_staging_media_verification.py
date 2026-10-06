import copy

import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_steps import project_merchant_step
from muse.commerce.repository import digest
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_site_release_steps import outcome


@pytest.fixture
def staged_media(merchant_review):  # noqa: F811
    _repo, _project, plan, intent, _evidence, connection, _clock, proofs = merchant_review
    from muse.commerce.code_bridge import load_captured_code
    code = load_captured_code(merchant_review[0], plan)
    snapshot = intent.initial_snapshot
    history = []
    for index in range(len(intent.steps)):
        projection = project_merchant_step(intent, connection, code, index, history, snapshot, proofs)
        done, snapshot = outcome(intent, connection, code, projection, snapshot, proofs)
        history.append(done)
    media_proofs = {key: value for key, value in proofs.items() if key.startswith('media-sha256:')}
    return plan, code, snapshot, intent.images, media_proofs, connection


def test_staging_facts_verify_approved_image_bytes_and_product_primary_gallery(staged_media):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot, images, proofs, connection = staged_media
    result = verify_staging_facts(plan, code, snapshot, connection=connection, images=images, media_proofs=proofs)
    assert result['passed'] and result['site_verified'] is False
    assert result['media_ids'] == {images[0].media_ref: 701}


@pytest.mark.parametrize('attack', ['missing', 'extra', 'sha', 'mime', 'width', 'owner', 'id', 'title', 'alt', 'parent', 'bool', 'primary', 'gallery', 'bytes'])
def test_staging_media_facts_reject_any_unapproved_image_version_or_association(staged_media, attack):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot, images, proofs, connection = copy.deepcopy(staged_media)
    ref = next(iter(proofs))
    if attack == 'missing': proofs = {}
    elif attack == 'extra': proofs['media-sha256:' + 'f' * 64] = copy.deepcopy(proofs[ref])
    elif attack == 'primary': snapshot.products[0]['image_id'] = 999
    elif attack == 'gallery': snapshot.products[0]['gallery_image_ids'] = [999]
    elif attack == 'bytes': images[0].content_base64 = 'bm90LWFuLWltYWdl'
    else:
        field, value = {'sha': ('sha256', 'f' * 64), 'mime': ('mime_type', 'image/svg+xml'), 'width': ('width', 999),
            'owner': ('muse_project_id', 'other'), 'id': ('id', 999), 'title': ('title', 'Merchant edit'),
            'alt': ('alt', 'Merchant edit'), 'parent': ('parent_id', 999), 'bool': ('id', True)}[attack]
        proofs[ref]['state']['attachment'][field] = value
        proofs[ref]['fingerprint'] = digest(proofs[ref]['state'])
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging')
    with pytest.raises(CommerceFailure):
        verify_staging_facts(plan, code, snapshot, connection=connection, images=images, media_proofs=proofs)
