import base64
import hashlib
import hmac
import json

import pytest

from muse.commerce.repository import digest
from tests.muse.commerce.test_php_protocol import php, run  # noqa: F401
from tests.muse.commerce.test_release_authorization import approved
from tests.muse.commerce.test_release_steps import creation, inputs


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def wire(publish):
    from muse.commerce_connector.release_authorization import ProductReleaseAuthority
    if publish:
        intent, connection, snapshot, proofs, done = creation()
        index, history = 1, [done]
    else:
        intent, connection, snapshot, proofs = inputs()
        index, history = 0, []
    grant = approved(intent, connection)
    authority = ProductReleaseAuthority(b'x' * 32, clock=lambda: 1000)
    args = (intent, connection, index, history, snapshot, proofs)
    token = authority.issue(grant, *args)
    operation = authority.verify(token, grant, *args).operation
    return {'mode': 'verify_v2', 'operation': operation.model_dump(mode='json'), 'token': token,
            'secret': base64.b64encode(b'x' * 32).decode(), 'now': 1000,
            'scope': {'project_id': 'project', 'connection_id': 'connection', 'environment': 'staging',
                      'target_url': 'https://shop.test'}}


@pytest.mark.parametrize('publish', [False, True])
def test_php_accepts_separate_product_step_permit_and_v1_rejects_it(php, publish):  # noqa: F811 - registered pytest fixture
    value = wire(publish)
    assert run(php, value) == {'accepted': True, 'grant_id': 'root-approval'}
    value['mode'] = 'verify'
    assert run(php, value) == {'accepted': False}


@pytest.mark.parametrize('attack', ['index', 'index_bool', 'step_key', 'id', 'kind', 'audience', 'version',
                                   'extra', 'expiry', 'identity_missing', 'identity_extra', 'identity_hash'])
def test_php_rejects_signed_but_invalid_product_step_contract(php, attack):  # noqa: F811 - registered pytest fixture
    value = wire(False)
    claims = json.loads(base64.urlsafe_b64decode(value['token'].split('.')[0] + '=='))
    if attack == 'index': claims['step_index'] = 1
    elif attack == 'index_bool': claims['step_index'] = False
    elif attack == 'step_key': claims['step_key'] = 'publish-product-1'
    elif attack == 'id': value['operation']['operation_id'] = 'not-the-root-step'
    elif attack == 'kind': value['operation']['kind'] = 'create_owned_page'
    elif attack == 'audience': claims['audience'] = 'muse-wp-operation-v1'
    elif attack == 'version': claims['v'] = 1
    elif attack == 'extra': claims['extra'] = True
    elif attack == 'expiry': claims['expires_at'] = 2801
    elif attack == 'identity_missing': claims['sku_identities'] = {}
    elif attack == 'identity_extra': claims['sku_identities'] = {'sku:' + 'f' * 64: 'cup'}
    else: claims['sku_identities'] = {next(iter(claims['sku_identities'])): 'other'}
    claims['operation_digest'] = digest(value['operation'])
    raw = json.dumps(claims, sort_keys=True, separators=(',', ':')).encode()
    value['token'] = encoded(raw) + '.' + encoded(hmac.digest(b'x' * 32, raw, hashlib.sha256))
    assert run(php, value) == {'accepted': False}


def test_php_accepts_maximum_unicode_batch_only_in_v2(php):  # noqa: F811
    from muse.commerce_connector.release_authorization import ProductReleaseAuthority
    from tests.muse.commerce.test_release_authorization import maximum_unicode_release
    intent, connection, snapshot, proofs = maximum_unicode_release()
    authority = ProductReleaseAuthority(b'x' * 32, clock=lambda: 1000)
    grant = approved(intent, connection)
    args = (intent, connection, 0, [], snapshot, proofs)
    token = authority.issue(grant, *args)
    value = wire(False)
    value['token'] = token
    value['operation'] = authority.verify(token, grant, *args).operation.model_dump(mode='json')
    assert run(php, value) == {'accepted': True, 'grant_id': 'root-approval'}
    value['mode'] = 'verify'
    assert run(php, value) == {'accepted': False}
