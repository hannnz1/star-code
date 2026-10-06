import base64
import copy
import json
from dataclasses import replace

import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_release_steps import creation, inputs


def approved(intent, connection):
    from muse.commerce_connector.release_authorization import ProductReleaseGrant
    return ProductReleaseGrant('root-approval', intent.digest, intent.project_id, connection.connection_id,
        connection.environment, connection.base_url, 'e' * 64, 1000, 2800, 'approved')


def test_v2_permit_is_bound_to_root_and_derived_step_without_v1_approval_rewrite():
    from muse.commerce_connector.release_authorization import ProductReleaseAuthority
    intent, connection, snapshot, proofs, done = creation()
    authority = ProductReleaseAuthority(b'x' * 32, clock=lambda: 1100)
    grant = approved(intent, connection)
    args = (intent, connection, 1, [done], snapshot, proofs)
    token = authority.issue(grant, *args)
    step = authority.verify(token, grant, *args)
    claims = json.loads(base64.urlsafe_b64decode(token.split('.')[0] + '=='))
    assert claims['v'] == 2 and claims['audience'] == 'muse-wp-product-step-v2'
    assert claims['changeset_digest'] == intent.digest
    assert claims['issued_at'] == 1000 and claims['expires_at'] == 2800
    assert claims['step_index'] == 1 and claims['step_key'] == 'publish-product-1'
    assert step.operation.payload == {'product_id': 21}
    assert claims['preconditions'] == step.preconditions
    assert authority.issue(grant, *args) == token


@pytest.mark.parametrize('change', ['revoked', 'expired', 'future', 'extended', 'root', 'verification',
                                  'project', 'connection', 'target', 'environment', 'signature', 'history'])
def test_v2_permit_rechecks_current_grant_and_exact_history(change):
    from muse.commerce_connector.release_authorization import ProductReleaseAuthority
    intent, connection, snapshot, proofs, done = creation()
    authority = ProductReleaseAuthority(b'x' * 32, clock=lambda: 1100)
    grant = approved(intent, connection)
    args = (intent, connection, 1, [done], snapshot, proofs)
    token = authority.issue(grant, *args)
    if change == 'revoked': grant = replace(grant, status='revoked')
    elif change == 'expired': grant = replace(grant, expires_at=1100)
    elif change == 'future': grant = replace(grant, approved_at=1101)
    elif change == 'extended': grant = replace(grant, expires_at=2900)
    elif change == 'root': grant = replace(grant, intent_digest='f' * 64)
    elif change == 'verification': grant = replace(grant, verification_hash='f' * 64)
    elif change == 'project': grant = replace(grant, project_id='other')
    elif change == 'connection': grant = replace(grant, connection_id='other')
    elif change == 'target': grant = replace(grant, target_url='https://other.test')
    elif change == 'environment': grant = replace(grant, environment='live')
    elif change == 'signature': token = token[:-1] + ('A' if token[-1] != 'A' else 'B')
    else:
        done.operation.payload['product']['title'] = 'Unapproved'
    with pytest.raises(CommerceFailure):
        authority.verify(token, grant, *args)


def test_changed_intent_and_v1_permit_cannot_enter_product_authority():
    from muse.commerce.models import ApprovalGrant
    from muse.commerce.release_steps import project_product_step
    from muse.commerce_connector.authorization import ExecutionAuthority
    from muse.commerce_connector.release_authorization import ProductReleaseAuthority
    intent, connection, snapshot, proofs = inputs()
    args = (intent, connection, 0, [], snapshot, proofs)
    operation = project_product_step(*args).operation
    old = ApprovalGrant(id='old', changeset_digest=intent.digest, project_id='project', environment='staging',
        resource_preconditions=intent.resource_preconditions, verification_hash='e' * 64, expires_at=2800)
    token = ExecutionAuthority(b'x' * 32, clock=lambda: 1000).issue(old, connection, operation)
    authority = ProductReleaseAuthority(b'x' * 32, clock=lambda: 1000)
    grant = approved(intent, connection)
    with pytest.raises(CommerceFailure):
        authority.verify(token, grant, *args)
    altered = copy.deepcopy(intent)
    altered.steps[0].product.title = 'Unapproved'
    with pytest.raises(CommerceFailure):
        authority.issue(grant, altered, connection, 0, [], snapshot, proofs)


def maximum_unicode_release():
    import hashlib

    from muse.commerce.models import ProductDraft
    from muse.commerce.release import prepare_product_release
    from muse.commerce.repository import digest
    from tests.muse.commerce.test_release_intent import product_release_inputs
    project, plan, target, snapshot, _ = product_release_inputs()
    plan.products = [ProductDraft(sku=('商品𐐀' * 32) + str(i), title='Cup', price='10.00', currency='USD', stock=3)
                     for i in range(20)]
    plan.content_hash = digest({'blueprint': plan.blueprint.model_dump(mode='json'),
                               'products': [p.model_dump(mode='json') for p in plan.products]})
    proofs = {}
    for product in plan.products:
        state = {'sku': product.sku.strip().casefold(), 'exists': False}
        key = 'sku:' + hashlib.sha256(state['sku'].encode()).hexdigest()
        proofs[key] = {'resource_key': key, 'state': state, 'fingerprint': digest(state)}
    intent = prepare_product_release(project, plan, target, snapshot, proofs)
    return intent, inputs()[1], snapshot, proofs


def test_twenty_long_unicode_skus_fit_bounded_v2_permit():
    from muse.commerce_connector.release_authorization import ProductReleaseAuthority
    intent, connection, snapshot, proofs = maximum_unicode_release()
    authority = ProductReleaseAuthority(b'x' * 32, clock=lambda: 1000)
    grant = approved(intent, connection)
    args = (intent, connection, 0, [], snapshot, proofs)
    token = authority.issue(grant, *args)
    assert 8192 < len(token) <= 32768
    assert authority.verify(token, grant, *args).index == 0
    with pytest.raises(CommerceFailure):
        authority.verify('a' * 32769, grant, *args)
