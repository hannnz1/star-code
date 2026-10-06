import base64
import copy
import hmac
import json

import pytest

from muse.commerce.merchant_release import prepare_merchant_release
from muse.commerce_connector.authorization import _encode
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_merchant_release import merchant_inputs  # noqa: F401
from tests.muse.commerce.test_php_protocol import php, run  # noqa: F401
from tests.muse.commerce.test_remote_media import image_upload  # noqa: F401
from tests.muse.commerce.test_site_release_intent import (
    site_release_inputs,  # noqa: F401
)


def wire(args, business_kind='build_site'):
    from muse.commerce_connector.merchant_authorization import (
        MerchantReleaseAuthority,
        MerchantReleaseGrant,
    )
    args[1].kind = business_kind
    if business_kind == 'launch_products':
        for key in list(args[5]):
            if key.startswith('page-slug:'): args[5].pop(key)
    intent = prepare_merchant_release(*args)
    connection = WordPressConnection('connection', 'project', 'staging', 'https://shop.test', 'fixture', 'fake')
    grant = MerchantReleaseGrant('grant', intent.digest, 'project', 'connection', 'staging', connection.base_url,
        'e' * 64, 1000, 1300, 'approved')
    authority = MerchantReleaseAuthority(b's' * 32, clock=lambda: 1001)
    token = authority.issue(grant, intent, connection, args[4], 0, [], args[3], args[5])
    step = authority.verify(token, grant, intent, connection, args[4], 0, [], args[3], args[5])
    return {'mode': 'verify_v4', 'token': token, 'secret': base64.b64encode(b's' * 32).decode(),
        'operation': step.operation.model_dump(mode='json'), 'now': 1001, 'scope': {
            'project_id': 'project', 'connection_id': 'connection', 'environment': 'staging', 'target_url': connection.base_url}}


@pytest.mark.parametrize('business_kind', ['build_site', 'launch_products'])
def test_php_accepts_only_separate_v4_merchant_image_member(php, merchant_inputs, business_kind):  # noqa: F811
    value = wire(merchant_inputs, business_kind)
    assert run(php, value) == {'accepted': True, 'grant_id': 'grant'}
    for old_mode in ['verify', 'verify_v2', 'verify_v3']:
        assert run(php, {**value, 'mode': old_mode}) == {'accepted': False}


@pytest.mark.parametrize('attack', ['workflow', 'count', 'product_count', 'catalog_count', 'workflow_scope', 'step_index', 'step_key', 'extra', 'identity', 'resource'])
def test_php_rejects_signed_but_invalid_merchant_graph_members(php, merchant_inputs, attack):  # noqa: F811
    value = wire(merchant_inputs)
    body = value['token'].split('.')[0]
    claims = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
    if attack == 'workflow': claims['workflow'] = 'arbitrary_store_write'
    elif attack == 'count': claims['image_count'] = True
    elif attack == 'product_count': claims['product_count'] = 21
    elif attack == 'catalog_count': claims['product_count'] = 0
    elif attack == 'workflow_scope': claims['workflow'] = 'launch_products'
    elif attack == 'step_index': claims['step_index'] = 155
    elif attack == 'step_key': claims['step_key'] = 'install-theme'
    elif attack == 'extra': claims['arbitrary_command'] = 'shell'
    elif attack == 'identity': claims['identities'][value['operation']['resource_key']]['sha256'] = 'f' * 64
    else: claims['preconditions']['media-sha256:' + 'f' * 64] = 'e' * 64
    raw = json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    value['token'] = _encode(raw) + '.' + _encode(hmac.digest(b's' * 32, raw, 'sha256'))
    assert run(php, copy.deepcopy(value)) == {'accepted': False}


@pytest.mark.parametrize('with_images', [False, True])
@pytest.mark.parametrize('product_count', [1, 2])
def test_retained_launch_php_accepts_every_exact_member_without_theme_install(php, merchant_inputs, tmp_path, with_images, product_count):
    from muse.commerce.coding import SourceStore
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.repository import digest
    from muse.commerce.theme import render_site_files
    from muse.commerce_connector.merchant_authorization import MerchantReleaseAuthority, MerchantReleaseGrant
    from tests.muse.commerce.test_coding_artifact import archive
    from tests.muse.commerce.test_site_release_steps import outcome
    project, plan, target, snapshot, old_code, proofs, images = merchant_inputs
    plan.kind = 'launch_products'
    plan.blueprint.required_settings['retain_existing_theme'] = True
    snapshot.theme_identity['files_sha256'] = {entry['path']:entry['sha256'] for entry in old_code.package.files_manifest}
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), project.id, 'staging')
    plan.snapshot_hash = digest(snapshot)
    for key in list(proofs):
        if key.startswith('page-slug:') or (not with_images and key.startswith('media-sha256:')):
            proofs.pop(key)
    if not with_images:
        images = []
        plan.products[0].media_refs = []
    if product_count == 2:
        plan.products.append(plan.products[0].model_copy(deep=True, update={'sku':'cup-second'}))
        import hashlib
        resource = 'sku:' + hashlib.sha256(b'cup-second').hexdigest()
        state = {'sku':'cup-second', 'exists':False}
        proofs[resource] = {'resource_key':resource, 'state':state, 'fingerprint':digest(state)}
    plan.content_hash = digest({'blueprint':plan.blueprint.model_dump(mode='json'),
        'products':[p.model_dump(mode='json') for p in plan.products]})
    code = SourceStore(tmp_path/'retained-permit-source').seal(archive(render_site_files(plan.blueprint, plan.products)),
        project_id=project.id, plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    intent = prepare_merchant_release(project, plan, target, snapshot, code, proofs, images)
    connection = WordPressConnection('connection', project.id, 'staging', target.public_url, 'fixture', 'fake')
    authority = MerchantReleaseAuthority(b's'*32, clock=lambda:1001)
    grant = MerchantReleaseGrant('grant', intent.digest, project.id, 'connection', 'staging', target.public_url,
        'e'*64, 1000, 1300, 'approved')
    history = []
    for index in range(len(intent.steps)):
        token = authority.issue(grant, intent, connection, code, index, history, snapshot, proofs)
        step = authority.verify(token, grant, intent, connection, code, index, history, snapshot, proofs)
        value = {'mode':'verify_retained', 'token':token, 'secret':base64.b64encode(b's'*32).decode(),
            'operation':step.operation.model_dump(mode='json'), 'now':1001,
            'scope':{'project_id':project.id, 'connection_id':'connection', 'environment':'staging', 'target_url':target.public_url}}
        assert run(php, value) == {'accepted':True, 'grant_id':'grant'}
        assert run(php, {**value, 'mode':'verify_dispatch'}) == {'accepted':True, 'grant_id':'grant'}
        states = {proof['state']['sku']:proof['state'] for proof in proofs.values()
            if 'sku' in proof.get('state', {}) and proof['state'].get('exists') is False}
        assert run(php, {**value, 'mode':'verify_identity_fingerprints', 'expected_states':states}) == {'accepted':True, 'grant_id':'grant'}
        for old_mode in ('verify_v4', 'verify_staging'):
            assert run(php, {**value, 'mode':old_mode}) == {'accepted':False}
        if step.operation.kind == 'create_product_draft':
            for attack in ('install_theme', 'workflow', 'extra', 'index', 'audience', 'boolean_count'):
                bad = copy.deepcopy(value)
                body = token.split('.')[0]
                claims = json.loads(base64.urlsafe_b64decode(body + '='*(-len(body)%4)))
                if attack == 'install_theme':
                    claims['step_key'] = 'install-theme'
                    bad['operation'].update(kind='install_theme_package', resource_key='theme:muse-storefront',
                        expected_fingerprint=claims['preconditions']['theme:muse-storefront'], payload={})
                    claims['operation_digest'] = digest(bad['operation'])
                elif attack == 'workflow': claims['workflow'] = 'build_site'
                elif attack == 'extra': claims['arbitrary_command'] = 'shell'
                elif attack == 'index': claims['step_index'] = len(intent.steps)
                elif attack == 'audience': claims['audience'] = 'muse-wp-staging-preview-v5'
                else: claims['image_count'] = True
                raw = json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
                bad['token'] = _encode(raw) + '.' + _encode(hmac.digest(b's'*32, raw, 'sha256'))
                assert run(php, bad) == {'accepted':False}, attack
        done, snapshot = outcome(intent, connection, code, step, snapshot, proofs)
        history.append(done)
    assert all(item.operation.kind != 'install_theme_package' for item in history)
