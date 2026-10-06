import base64
import hmac
import json
from dataclasses import replace

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce_connector.authorization import _encode
from tests.muse.commerce.test_php_protocol import php, run  # noqa: F401
from tests.muse.commerce.test_site_release_intent import (
    site_release_inputs,  # noqa: F401
)
from tests.muse.commerce.test_site_release_steps import complete, setup


def grant_for(intent, connection):
    from muse.commerce_connector.site_authorization import SiteReleaseGrant
    return SiteReleaseGrant('site-approval', intent.digest, intent.project_id, connection.connection_id,
                            connection.environment, connection.base_url, 'e' * 64, 1000, 2800, 'approved')


def test_site_authority_signs_only_rederived_current_step_with_fixed_expiry(site_release_inputs):  # noqa: F811
    from muse.commerce_connector.site_authorization import SiteReleaseAuthority
    intent, connection, snapshot, code, proofs = setup(site_release_inputs)
    grant = grant_for(intent, connection)
    authority = SiteReleaseAuthority(b'x' * 32, clock=lambda: 1100)
    args = (intent, connection, code, 0, [], snapshot, proofs)
    token = authority.issue(grant, *args)
    result = authority.verify(token, grant, *args)
    claims = json.loads(base64.urlsafe_b64decode(token.split('.')[0] + '=='))
    assert claims['v'] == 3 and claims['audience'] == 'muse-wp-site-step-v3'
    assert claims['step_key'] == 'install-theme' and claims['identities'] == result.identities
    assert claims['issued_at'] == 1000 and claims['expires_at'] == 2800
    assert authority.issue(grant, *args) == token
    for mutation in ({'status': 'revoked'}, {'expires_at': 1100}, {'expires_at': 2900}, {'approved_at': 1101},
                     {'intent_digest': 'f' * 64}, {'verification_hash': 'f' * 64}, {'connection_id': 'other'},
                     {'target_url': 'https://other.test'}, {'environment': 'live'}):
        with pytest.raises(CommerceFailure):
            authority.verify(token, replace(grant, **mutation), *args)


def wire(args, index):
    from muse.commerce.site_steps import project_site_step
    from muse.commerce_connector.site_authorization import SiteReleaseAuthority
    intent, connection, code, history, _last, proofs = complete(args)
    before = intent.initial_snapshot if index == 0 else history[index - 1].snapshot
    current_proofs = {}
    for key, proof in proofs.items():
        state = dict(proof['state'])
        kind = 'page' if key.startswith('page-slug:') else 'product'
        entities = getattr(before, kind + 's')
        entity = next((item for item in entities if item.get('slug' if kind == 'page' else 'sku', '').casefold()
                       == state['slug' if kind == 'page' else 'sku'].casefold()), None)
        state = {'slug' if kind == 'page' else 'sku': state['slug' if kind == 'page' else 'sku'], 'exists': entity is not None}
        if entity: state.update({kind + '_id': entity['id'], 'entity_fingerprint': digest(entity)})
        current_proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    projection = project_site_step(intent, connection, code, index, history[:index], before, current_proofs)
    token = SiteReleaseAuthority(b'x' * 32, clock=lambda: 1100).issue(grant_for(intent, connection),
        intent, connection, code, index, history[:index], before, current_proofs)
    return {'mode': 'verify_v3', 'operation': projection.operation.model_dump(mode='json'), 'token': token,
            'secret': base64.b64encode(b'x' * 32).decode(), 'now': 1100,
            'scope': {'project_id': 'project', 'connection_id': 'connection', 'environment': 'staging',
                      'target_url': 'https://shop.test'}}


@pytest.mark.parametrize('index', [0, 1, 2, 11, 12, 13, 14, 15, 16])
def test_php_accepts_separate_site_steps_and_old_protocols_reject_them(php, site_release_inputs, index):  # noqa: F811
    value = wire(site_release_inputs, index)
    assert run(php, value) == {'accepted': True, 'grant_id': 'site-approval'}
    for mode in ('verify', 'verify_v2'):
        value['mode'] = mode
        assert run(php, value) == {'accepted': False}


@pytest.mark.parametrize('attack', ['index_bool', 'step_key', 'operation_id', 'kind', 'audience', 'version', 'extra',
                                  'expiry', 'missing_identity', 'extra_identity', 'identity_hash', 'identity_type'])
def test_php_rejects_signed_but_invalid_site_claims(php, site_release_inputs, attack):  # noqa: F811
    value = wire(site_release_inputs, 0)
    claims = json.loads(base64.urlsafe_b64decode(value['token'].split('.')[0] + '=='))
    if attack == 'index_bool': claims['step_index'] = False
    elif attack == 'step_key': claims['step_key'] = 'set-navigation'
    elif attack == 'operation_id': value['operation']['operation_id'] = 'arbitrary'
    elif attack == 'kind': value['operation']['kind'] = 'update_owned_page'
    elif attack == 'audience': claims['audience'] = 'muse-wp-product-step-v2'
    elif attack == 'version': claims['v'] = 2
    elif attack == 'extra': claims['extra'] = True
    elif attack == 'expiry': claims['expires_at'] = 2801
    elif attack == 'missing_identity': claims['identities'].pop(next(iter(claims['identities'])))
    elif attack == 'extra_identity': claims['identities']['sku:' + 'f' * 64] = {'sku': 'extra'}
    elif attack == 'identity_hash': claims['identities'][next(iter(claims['identities']))] = {'sku': 'other'}
    else: claims['identities'][next(iter(claims['identities']))] = {'slug': True}
    claims['operation_digest'] = digest(value['operation'])
    raw = json.dumps(claims, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    value['token'] = _encode(raw) + '.' + _encode(hmac.digest(b'x' * 32, raw, 'sha256'))
    assert run(php, value) == {'accepted': False}
