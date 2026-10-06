import copy
import io
import json
import zipfile

import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_site_release_intent import (
    site_release_inputs,  # noqa: F401
)


def setup(args):
    from muse.commerce.site_release import prepare_site_release
    intent = prepare_site_release(*args)
    connection = WordPressConnection('connection', 'project', 'staging', 'https://shop.test', 'service', 'fixture')
    return intent, connection, args[3], args[4], copy.deepcopy(args[5])


def outcome(intent, connection, code, projection, before, proofs):
    from muse.commerce.site_steps import CompletedSiteStep
    op = projection.operation
    raw = before.model_dump(mode='json')
    proof = {}
    if op.kind == 'create_owned_media':
        payload = op.payload
        entity = {**payload['image'], 'id': 701, 'media_ref': payload['media_ref'], 'muse_project_id': intent.project_id,
            'status': 'inherit', 'parent_id': 0, 'title': 'MUSE image ' + payload['image']['sha256'], 'alt': ''}
        state = {'sha256': entity['sha256'], 'exists': True, 'attachment': entity}
        proof = {'resource_key': op.resource_key, 'state': state, 'fingerprint': digest(state)}
        proofs[op.resource_key] = proof
    elif op.kind == 'install_theme_package':
        with zipfile.ZipFile(io.BytesIO(code.archive)) as archive:
            files = {name.removeprefix('muse-storefront/'): archive.read(name).decode() for name in archive.namelist()}
        raw['theme_identity']['files_sha256'] = {entry['path']: entry['sha256'] for entry in code.package.files_manifest}
        raw['theme_identity']['effective_templates'] = [
            {'id': 'muse-storefront//' + path.rsplit('/', 1)[-1][:-5], 'slug': path.rsplit('/', 1)[-1][:-5],
             'type': 'wp_template_part' if path.startswith('parts/') else 'wp_template', 'source': 'theme', 'content': value}
            for path, value in files.items() if path.endswith('.html')]
        theme = json.loads(files['theme.json'])
        raw['theme_identity']['global_styles']['styles']['color'] = theme['styles']['color']
        raw['theme_identity']['global_styles']['settings'] = {'color': {'palette': {'theme': theme['settings']['color']['palette']}}}
    elif op.kind == 'create_owned_page':
        entity = {'id': 101 + len(raw['pages']), 'slug': op.payload['slug'], 'title': op.payload['title'],
                  'content': '', 'status': 'draft', 'template': 'default' if op.payload['template'] == 'page' else op.payload['template'],
                  'muse_project_id': intent.project_id}
        raw['pages'].append(entity)
        state = {'slug': entity['slug'], 'exists': True, 'page_id': entity['id'], 'entity_fingerprint': digest(entity)}
        proof = {'resource_key': op.resource_key, 'state': state, 'fingerprint': digest(state)}
        proofs[op.resource_key] = proof
    elif op.kind == 'publish_owned_page':
        entity = next(item for item in raw['pages'] if item['id'] == op.payload['page_id'])
        entity['status'] = 'publish'
    elif op.kind == 'set_storefront_options':
        raw['settings'].update(op.payload)
        raw['settings']['show_on_front'] = 'page'
    elif op.kind == 'set_owned_navigation':
        content = ''.join('<!-- wp:navigation-link ' + json.dumps({'label': entry['label'], 'type': 'page',
            'id': entry['page_id'], 'kind': 'post-type', 'url': connection.base_url + '/' if entry['page_id'] == raw['settings']['home_page_id']
            else connection.base_url + '/?page_id=' + str(entry['page_id'])}, separators=(',', ':')) + ' /-->' for entry in op.payload['items'])
        raw['theme_identity']['owned_navigation'] = {'items': [{'id': 301, 'content': content, 'status': 'publish', 'muse_project_id': intent.project_id}]}
        header = next(item for item in raw['theme_identity']['effective_templates'] if item['slug'] == 'header')
        header.update(source='custom', content=('<!-- wp:group {"layout":{"type":"flex","justifyContent":"space-between"}} -->'
            '<div class="wp-block-group"><!-- wp:site-title /--><!-- wp:navigation {"overlayMenu":"mobile","ref":301} /--></div><!-- /wp:group -->'))
    elif op.kind == 'create_product_draft':
        product = op.payload['product']
        entity = {'id': 201 + len(raw['products']), 'sku': product['sku'], 'name': product['title'], 'description': product['description'],
                  'price': product['price'], 'regular_price': product['price'], 'sale_price': '', 'stock_quantity': product['stock'],
                  'manage_stock': True, 'stock_status': 'instock', 'backorders': 'no', 'category_ids': [],
                  'status': 'draft', 'type': 'simple', 'muse_project_id': intent.project_id, 'image_id': 0, 'gallery_image_ids': []}
        raw['products'].append(entity)
        images = op.payload.get('media_bindings', [])
        entity['image_id'] = images[0]['id'] if images else 0
        entity['gallery_image_ids'] = [image['id'] for image in images[1:]]
        state = {'sku': product['sku'].casefold(), 'exists': True, 'product_id': entity['id'], 'entity_fingerprint': digest(entity)}
        proof = {'resource_key': op.resource_key, 'state': state, 'fingerprint': digest(state)}
        proofs[op.resource_key] = proof
    else:
        next(product for product in raw['products'] if product['id'] == op.payload['product_id'])['status'] = 'publish'
    after = normalize_snapshot(raw, intent.project_id, intent.target.environment)
    for key, item in proofs.items():
        state = item['state']
        if state['exists'] and not key.startswith('media-sha256:'):
            kind = 'page' if key.startswith('page-slug:') else 'product'
            state['entity_fingerprint'] = after.resource_fingerprints[f'{kind}:{state[kind + "_id"]}']
            item['fingerprint'] = digest(state)
    fingerprint = proof['fingerprint'] if proof else after.resource_fingerprints[
        'theme' if op.resource_key == 'theme:muse-storefront' else op.resource_key]
    receipt = OperationRecord(project_id=intent.project_id, connection_id=connection.connection_id, environment=connection.environment,
        operation_id=op.operation_id, operation_digest=operation_digest(op), resource_key=op.resource_key,
        state='SUCCEEDED', fingerprint=fingerprint)
    return CompletedSiteStep(op, receipt, after, copy.deepcopy(proof)), after


def complete(args):
    from muse.commerce.site_steps import project_site_step
    intent, connection, snapshot, code, proofs = setup(args)
    history = []
    for index in range(len(intent.steps)):
        projected = project_site_step(intent, connection, code, index, history, snapshot, proofs)
        done, snapshot = outcome(intent, connection, code, projected, snapshot, proofs)
        history.append(done)
    return intent, connection, code, history, snapshot, proofs


def test_site_steps_use_exact_source_and_authenticated_page_ids_for_complete_build(site_release_inputs):  # noqa: F811
    from muse.commerce.site_steps import validate_site_completion
    intent, connection, code, history, snapshot, proofs = complete(site_release_inputs)
    assert history[0].operation.payload['package'] == code.package.model_dump(mode='json')
    assert len(history) == 17
    assert history[2].operation.payload == {'page_id': 101}
    assert history[13].operation.payload['home_page_id'] == 101
    result = validate_site_completion(intent, connection, code, history, snapshot, proofs)
    assert result['theme:muse-storefront'] == snapshot.resource_fingerprints['theme']
    assert result['product:201'] == snapshot.resource_fingerprints['product:201']


@pytest.mark.parametrize('attack', ['unknown', 'receipt_scope', 'digest', 'order', 'page_edit', 'source', 'initial_settings',
                                  'navigation', 'header', 'global_styles', 'bool_index', 'proof', 'unrelated_page',
                                  'old_colors', 'old_palette', 'menu_extra'])
def test_site_projection_rejects_unknown_or_unapproved_intermediate_effects(site_release_inputs, attack):  # noqa: F811
    from muse.commerce.site_steps import project_site_step, validate_site_completion
    intent, connection, code, history, snapshot, proofs = complete(site_release_inputs)
    if attack == 'bool_index':
        with pytest.raises(CommerceFailure):
            project_site_step(intent, connection, code, True, history[:1], history[0].snapshot, proofs)
        return
    if attack in {'unknown', 'receipt_scope', 'digest'}:
        name, value = {'unknown': ('state', 'NEEDS_RECONCILIATION'), 'receipt_scope': ('connection_id', 'other'),
                       'digest': ('operation_digest', 'f' * 64)}[attack]
        history[1].receipt = history[1].receipt.model_copy(update={name: value})
    elif attack == 'order': history[1:3] = reversed(history[1:3])
    elif attack == 'source':
        from dataclasses import replace
        code = replace(code, source_digest='f' * 64)
    elif attack == 'proof': proofs[next(iter(proofs))]['state']['exists'] = 1
    else:
        theme_attack = attack in {'global_styles', 'initial_settings', 'old_colors', 'old_palette'}
        raw = history[0].snapshot.model_dump(mode='json') if theme_attack else snapshot.model_dump(mode='json')
        if attack == 'page_edit': raw['pages'][0]['title'] = 'Merchant edit'
        elif attack == 'initial_settings': raw['settings']['currency'] = 'EUR'
        elif attack == 'global_styles': raw['theme_identity']['global_styles']['styles']['typography'] = {'fontFamily': 'unapproved'}
        elif attack == 'old_colors': raw['theme_identity']['global_styles']['styles'].pop('color')
        elif attack == 'old_palette': raw['theme_identity']['global_styles']['settings']['color'].pop('palette')
        elif attack == 'menu_extra': raw['theme_identity']['owned_navigation']['metadata'] = 'Unsigned'
        elif attack == 'navigation': raw['theme_identity']['owned_navigation']['items'][0]['content'] += '<p>Unsigned</p>'
        elif attack == 'header': next(item for item in raw['theme_identity']['effective_templates'] if item['slug'] == 'header')['content'] += '<p>Unsigned</p>'
        else: raw['pages'].append({**raw['pages'][0], 'id': 999, 'slug': 'unrelated'})
        changed = normalize_snapshot(raw, intent.project_id, connection.environment)
        if theme_attack:
            history[0].snapshot = changed
            history[0].receipt = history[0].receipt.model_copy(update={'fingerprint': changed.resource_fingerprints['theme']})
            with pytest.raises(CommerceFailure):
                project_site_step(intent, connection, code, 1, history[:1], changed, site_release_inputs[5])
            return
        else: snapshot = changed
    with pytest.raises(CommerceFailure):
        validate_site_completion(intent, connection, code, history, snapshot, proofs)


def test_navigation_step_rejects_unsigned_menu_metadata_even_with_matching_receipt(site_release_inputs):  # noqa: F811
    from muse.commerce.site_steps import project_site_step
    intent, connection, code, history, _snapshot, proofs = complete(site_release_inputs)
    raw = history[14].snapshot.model_dump(mode='json')
    raw['theme_identity']['owned_navigation']['metadata'] = 'Unsigned'
    changed = normalize_snapshot(raw, intent.project_id, connection.environment)
    history[14].snapshot = changed
    history[14].receipt = history[14].receipt.model_copy(update={'fingerprint': changed.resource_fingerprints['navigation:muse-storefront']})
    proofs.update({key: value for key, value in site_release_inputs[5].items() if key.startswith('sku:')})
    with pytest.raises(CommerceFailure):
        project_site_step(intent, connection, code, 15, history[:15], changed, proofs)
