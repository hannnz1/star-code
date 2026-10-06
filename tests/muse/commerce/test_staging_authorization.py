import base64
import hmac
import json

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_release import prepare_merchant_release
from muse.commerce_connector.authorization import _encode
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_merchant_release import merchant_inputs  # noqa: F401
from tests.muse.commerce.test_php_protocol import php, run  # noqa: F401
from tests.muse.commerce.test_remote_media import image_upload  # noqa: F401
from tests.muse.commerce.test_site_release_intent import (
    site_release_inputs,  # noqa: F401
)


def preview_wire(args):
    from muse.commerce_connector.staging_authorization import (
        StagingReleaseAuthority,
        StagingReleaseGrant,
    )
    intent = prepare_merchant_release(*args)
    connection = WordPressConnection('connection', 'project', 'staging', 'https://shop.test', 'fixture', 'fake')
    grant = StagingReleaseGrant('preview-grant', intent.digest, 'project', 'connection', 'staging', connection.base_url,
        'e' * 64, 1000, 1300, 'approved')
    authority = StagingReleaseAuthority(b's' * 32, clock=lambda: 1001)
    token = authority.issue(grant, intent, connection, args[4], 0, [], args[3], args[5])
    step = authority.verify(token, grant, intent, connection, args[4], 0, [], args[3], args[5])
    return authority, grant, intent, connection, {'mode': 'verify_staging', 'token': token,
        'secret': base64.b64encode(b's' * 32).decode(), 'operation': step.operation.model_dump(mode='json'), 'now': 1001,
        'scope': {'project_id': 'project', 'connection_id': 'connection', 'environment': 'staging', 'target_url': connection.base_url}}


def test_preview_permit_is_separate_from_merchant_and_accepted_only_for_staging(php, merchant_inputs):  # noqa: F811
    from muse.commerce_connector.merchant_authorization import MerchantReleaseAuthority
    authority, grant, intent, connection, value = preview_wire(merchant_inputs)
    assert run(php, value) == {'accepted': True, 'grant_id': grant.id}
    for mode in ['verify', 'verify_v2', 'verify_v3', 'verify_v4']:
        assert run(php, {**value, 'mode': mode}) == {'accepted': False}
    with pytest.raises(CommerceFailure):
        MerchantReleaseAuthority(b's' * 32, clock=lambda: 1001).issue(grant, intent, connection,
            merchant_inputs[4], 0, [], merchant_inputs[3], merchant_inputs[5])
    live = WordPressConnection('connection', 'project', 'live', 'https://shop.test', 'fixture', 'fake')
    with pytest.raises(CommerceFailure):
        authority.issue(grant, intent, live, merchant_inputs[4], 0, [], merchant_inputs[3], merchant_inputs[5])


@pytest.mark.parametrize('attack', ['live', 'live-test', 'purpose', 'extra'])
def test_php_rejects_signed_preview_scope_or_purpose_changes(php, merchant_inputs, attack):  # noqa: F811
    *_, value = preview_wire(merchant_inputs)
    body = value['token'].split('.')[0]
    claims = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
    if attack in {'live', 'live-test'}:
        claims['environment'] = attack; value['scope']['environment'] = attack
    elif attack == 'purpose': claims['purpose'] = 'merchant-publish'
    else: claims['command'] = 'shell'
    raw = json.dumps(claims, sort_keys=True, separators=(',', ':')).encode()
    value['token'] = _encode(raw) + '.' + _encode(hmac.digest(b's' * 32, raw, 'sha256'))
    assert run(php, value) == {'accepted': False}
