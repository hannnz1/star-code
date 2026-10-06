"""Website step projection from frozen source and authenticated receipt history.

No approval, signing, persistence or HTTP happens here. A receipt alone cannot
refresh a resource version: the exact allowed effect must independently match.
"""
import base64
import copy
import io
import json
import zipfile
from dataclasses import dataclass

from muse.commerce.coding import verify_coding_artifact
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation, StoreSnapshot
from muse.commerce.release_resources import resolve_created_resource
from muse.commerce.release_steps import _approved_product_facts
from muse.commerce.repository import digest
from muse.commerce.site_release import validate_site_release
from muse.commerce.verification import (
    _canonical_header,
    _navigation_header,
    _theme_attributes,
    _woo_header,
)
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest, validate_operation


@dataclass
class CompletedSiteStep:
    operation: ChangeOperation
    receipt: OperationRecord
    snapshot: StoreSnapshot
    proof: dict


@dataclass(frozen=True)
class SiteStepProjection:
    root_digest: str
    index: int
    key: str
    operation: ChangeOperation
    preconditions: dict[str, str]
    identities: dict[str, dict]


def _normalized(intent, snapshot):
    if (not isinstance(snapshot, StoreSnapshot) or snapshot.project_id != intent.project_id
            or snapshot.environment != intent.target.environment
            or normalize_snapshot(snapshot.model_dump(mode='json'), snapshot.project_id, snapshot.environment) != snapshot):
        raise ValueError('Invalid current snapshot')


def _conditions(intent, snapshot, bindings):
    versions = {'theme:muse-storefront': snapshot.resource_fingerprints['theme'],
                'settings': snapshot.resource_fingerprints['settings'],
                'navigation:muse-storefront': snapshot.resource_fingerprints['navigation:muse-storefront']}
    identities = {}
    if any(step.kind == 'set_owned_shipping' for step in intent.steps):
        versions['shipping:muse-storefront'] = snapshot.resource_fingerprints['shipping:muse-storefront']
    if any(step.kind == 'set_owned_store_navigation' for step in intent.steps):
        from muse.commerce.store_configuration import category_targets
        names = {item.category for item in category_targets(intent.blueprint, intent.products)}
        for kind, entity in bindings.values():
            if kind != 'product': continue
            for category in entity.get('categories', []):
                if category['name'] in names:
                    key = 'category:'+str(category['id'])
                    versions[key] = snapshot.resource_fingerprints[key]
    for step in intent.steps:
        if step.kind not in {'create_owned_media', 'create_owned_page', 'create_product_draft'}:
            continue
        ref = step.resource_ref
        if ref in bindings:
            kind, entity = bindings[ref]
            if kind == 'media':
                versions[ref] = digest({'sha256': entity['sha256'], 'exists': True, 'attachment': entity})
            else:
                versions[f'{kind}:{entity["id"]}'] = digest(entity)
        else:
            versions[ref] = intent.resource_preconditions[ref]
            identities[ref] = {'sha256': step.payload['image']['sha256']} if step.kind == 'create_owned_media' else (
                {'slug': step.payload['slug']} if step.kind == 'create_owned_page' else {
                'sku': step.payload['product']['sku'].strip().casefold()})
    return versions, identities


def _operation(intent, code, index, bindings, versions, connection=None):
    step = intent.steps[index]
    key, payload = step.resource_ref, copy.deepcopy(step.payload)
    if step.kind == 'create_owned_media':
        payload = next(image.model_dump(mode='json') for image in intent.images if image.media_ref == payload['media_ref'])
    elif step.kind == 'create_product_draft' and payload['product']['media_refs']:
        media = {entity['media_ref']: entity for kind, entity in bindings.values() if kind == 'media'}
        payload['media_bindings'] = [copy.deepcopy(media[ref]) for ref in payload['product']['media_refs']]
    elif step.kind == 'install_theme_package':
        payload['archive_base64'] = base64.b64encode(code.archive).decode('ascii')
    elif step.kind in {'publish_owned_page', 'publish_product'}:
        kind, entity = bindings[key]
        key, payload = f'{kind}:{entity["id"]}', {kind + '_id': entity['id']}
    elif step.kind == 'set_storefront_options':
        payload = {name.removesuffix('_ref') + '_id': bindings[ref][1]['id'] for name, ref in payload.items()}
    elif step.kind == 'set_owned_navigation':
        payload = {'items': [{'page_id': bindings[item['page_ref']][1]['id'], 'label': item['label']} for item in payload['items']]}
    elif step.kind == 'set_owned_store_navigation':
        from muse.commerce.store_configuration import resolve_category
        products = [entity for kind, entity in bindings.values() if kind == 'product']
        payload = {'items': [({'page_id': bindings[item['page_ref']][1]['id'], 'label':item['label']} if 'page_ref' in item else
            {'category_id':resolve_category(products,item['category_name'],connection)['id'], 'label':item['label']}) for item in payload['items']]}
    prefix = 'merchant' if intent.version == 4 else 'site'
    return validate_operation(ChangeOperation(operation_id=f'{prefix}-{intent.digest}-{index}', kind=step.kind,
        resource_key=key, expected_fingerprint=versions[key], payload=payload))


def _theme_effect(intent, files, before, after):
    old, new = before.theme_identity, after.theme_identity
    expected = copy.deepcopy(old)
    expected['files_sha256'] = {entry['path']: entry['sha256'] for entry in intent.package.files_manifest}
    templates = {entry['id']: copy.deepcopy(entry) for entry in old['effective_templates']}
    for path, content in files.items():
        if not path.endswith('.html'):
            continue
        slug = path.rsplit('/', 1)[-1][:-5]
        identity = 'muse-storefront//' + slug
        actual = next((item for item in new['effective_templates'] if item['id'] == identity), None)
        previous = templates.get(identity)
        # Theme deployment deliberately retains merchant database overrides.
        if previous and previous.get('source') != 'theme':
            if actual != previous:
                raise ValueError('Database override changed during theme installation')
            continue
        allowed = {content, _theme_attributes(content)}
        if path == 'parts/header.html':
            allowed.add(_woo_header(content))
            allowed = {_canonical_header(item) for item in allowed}
        value = actual.get('content') if actual else None
        if path == 'parts/header.html' and isinstance(value, str):
            value = _canonical_header(value)
        if (not actual or actual.get('source') != 'theme' or actual.get('slug') != slug
                or actual.get('type') != ('wp_template_part' if path.startswith('parts/') else 'wp_template')
                or value not in allowed):
            raise ValueError('Installed effective source differs')
        templates[identity] = actual
    expected['effective_templates'] = sorted(templates.values(), key=lambda item: item['id'])
    # This first release supports the declared theme palette and colors. Other
    # resolved setting changes require an explicit platform materialization rule.
    theme = json.loads(files['theme.json'])
    previous_global = copy.deepcopy(old['global_styles'])
    current_global = copy.deepcopy(new['global_styles'])
    colors = current_global.get('styles', {}).pop('color', None)
    previous_global.get('styles', {}).pop('color', None)
    if colors != theme['styles']['color']:
        raise ValueError('Unapproved resolved theme colors')
    previous_global.setdefault('settings', {}).setdefault('color', {}).pop('palette', None)
    palette = current_global.setdefault('settings', {}).setdefault('color', {}).pop('palette', None)
    old_palette = old['global_styles'].get('settings', {}).get('color', {}).get('palette')
    source_palette = theme['settings']['color']['palette']
    if isinstance(palette, dict):
        preserved = copy.deepcopy(old_palette) if isinstance(old_palette, dict) else {}
        preserved['theme'] = source_palette
        valid_palette = palette == preserved
    else:
        valid_palette = palette == source_palette
    if not valid_palette:
        raise ValueError('Unapproved resolved theme palette')
    declared_font = theme.get('styles', {}).get('typography', {}).get('fontFamily')
    if 'font' in intent.blueprint.design_tokens:
        if declared_font not in {'Arial, sans-serif','Georgia, serif'}: raise ValueError('Unsupported declared font')
        if current_global.get('styles', {}).get('typography', {}).get('fontFamily') != declared_font:
            raise ValueError('Unapproved resolved font')
        for value in (current_global, previous_global):
            typography=value.get('styles', {}).get('typography', {})
            typography.pop('fontFamily',None)
            if not typography: value.get('styles', {}).pop('typography',None)
    if current_global != previous_global:
        raise ValueError('Unapproved global styles changed')
    expected['global_styles'] = new['global_styles']
    if new != expected:
        raise ValueError('Unapproved theme effect')


def _effect(intent, connection, files, op, receipt, proof, before, after, bindings):
    raw = before.model_dump(mode='json')
    if op.kind == 'create_owned_media':
        from muse.commerce_connector.media import resolve_created_media
        entity = resolve_created_media(connection, op, receipt, proof)
        bindings[op.resource_key] = ('media', entity.model_dump(mode='json'))
    elif op.kind == 'install_theme_package':
        _theme_effect(intent, files, before, after)
        raw['theme_identity'] = copy.deepcopy(after.theme_identity)
    elif op.kind in {'create_owned_page', 'create_product_draft'}:
        created = resolve_created_resource(connection, op, receipt, proof, after)
        kind = 'page' if op.kind == 'create_owned_page' else 'product'
        entity = next(item for item in getattr(after, kind + 's') if item['id'] == created.entity_id)
        if kind == 'page':
            expected = {'id': entity['id'], 'slug': op.payload['slug'], 'title': op.payload['title'], 'content': op.payload['content'],
                        'status': 'draft', 'template': 'default' if op.payload['template'] == 'page' else op.payload['template'],
                        'muse_project_id': intent.project_id}
            if entity != expected:
                raise ValueError('Page creation changed approved facts')
        else:
            # This payload is rederived from the frozen graph before effects
            # are accepted, including private retained-preview taxonomy seeds.
            from muse.commerce.models import ProductDraft
            product = ProductDraft.model_validate(op.payload['product'])
            _approved_product_facts(product, entity)
            images = op.payload.get('media_bindings', [])
            if (entity.get('status') != 'draft' or entity.get('image_id', 0) != (images[0]['id'] if images else 0)
                    or entity.get('gallery_image_ids', []) != [image['id'] for image in images[1:]]):
                raise ValueError('Product creation has unapproved effects')
        raw[kind + 's'].append(entity)
        bindings[op.resource_key] = (kind, copy.deepcopy(entity))
    elif op.kind in {'publish_owned_page', 'publish_product'}:
        kind = 'page' if op.kind == 'publish_owned_page' else 'product'
        entity = next(item for item in raw[kind + 's'] if item['id'] == op.payload[kind + '_id'])
        entity['status'] = 'publish'
        ref = intent.steps[int(op.operation_id.rsplit('-', 1)[1])].resource_ref
        bindings[ref] = (kind, copy.deepcopy(entity))
    elif op.kind == 'set_storefront_options':
        raw['settings'].update(op.payload)
        raw['settings']['show_on_front'] = 'page'
    elif op.kind == 'set_owned_shipping':
        from muse.commerce.store_configuration import shipping_effect
        configuration = shipping_effect(before.settings.get('shipping_configuration'),
            after.settings.get('shipping_configuration'), intent.project_id, op.payload['rules'])
        raw['settings']['shipping_configuration'] = copy.deepcopy(configuration)
        raw['settings']['shipping_confirmed'] = True
    else:
        # Navigation changes the owned menu plus exactly the source-bound header.
        from types import SimpleNamespace
        header_source = _navigation_header(SimpleNamespace(project_id=intent.project_id, blueprint=intent.blueprint, products=intent.products),
                                          after, connection, files['parts/header.html'], environment=connection.environment)
        previous_menu = before.theme_identity['owned_navigation']['items']
        next_menu = after.theme_identity['owned_navigation']['items']
        if (set(after.theme_identity['owned_navigation']) != {'items'}
                or any(set(item) != {'id', 'content', 'status', 'muse_project_id'} for item in next_menu)):
            raise ValueError('Unsigned navigation fields')
        if header_source is None or (previous_menu and previous_menu[0]['id'] != next_menu[0]['id']):
            raise ValueError('Navigation identity changed')
        raw['theme_identity']['owned_navigation'] = copy.deepcopy(after.theme_identity['owned_navigation'])
        header = next(item for item in raw['theme_identity']['effective_templates'] if item['slug'] == 'header')
        actual = next(item for item in after.theme_identity['effective_templates'] if item['slug'] == 'header')
        expected_header = {**header, 'source': 'custom', 'content': actual['content']}
        if (actual != expected_header or _canonical_header(actual['content']) not in
                {_canonical_header(header_source), _canonical_header(_woo_header(header_source))}):
            raise ValueError('Navigation lost or changed source header')
        header.update(expected_header)
    expected = normalize_snapshot(raw, intent.project_id, connection.environment)
    if expected != after:
        raise ValueError('Unrelated store facts changed')
    fingerprint = proof['fingerprint'] if op.kind in {'create_owned_media', 'create_owned_page', 'create_product_draft'} else after.resource_fingerprints[
        'theme' if op.resource_key == 'theme:muse-storefront' else op.resource_key]
    if receipt.fingerprint != fingerprint:
        raise ValueError('Receipt fingerprint differs from exact effect')


def _project(intent, connection, code, index, history, snapshot, proofs, *, complete=False, validator=validate_site_release):
    try:
        intent = validator(intent, connection=connection)
        if (type(index) is not int or not isinstance(history, list) or len(history) != index
                or not 0 <= index < len(intent.steps) + int(complete) or (complete and index != len(intent.steps))):
            raise ValueError('Invalid history position')
        verify_coding_artifact(code)
        if (code.project_id != intent.project_id or code.plan_id != intent.plan_id or code.snapshot_hash != intent.snapshot_hash
                or code.source_digest != intent.source_digest or code.package != intent.package):
            raise ValueError('Code differs from frozen source')
        with zipfile.ZipFile(io.BytesIO(code.archive)) as archive:
            files = {name.removeprefix('muse-storefront/'): archive.read(name).decode() for name in archive.namelist()}
        _normalized(intent, snapshot)
        before, bindings = intent.initial_snapshot.model_copy(deep=True), {}
        for position, done in enumerate(copy.deepcopy(history)):
            if not isinstance(done, CompletedSiteStep):
                raise TypeError('Invalid history record')
            versions, _ = _conditions(intent, before, bindings)
            expected = _operation(intent, code, position, bindings, versions, connection)
            receipt = done.receipt
            if (operation_digest(done.operation) != operation_digest(expected) or not isinstance(receipt, OperationRecord)
                    or receipt.state != 'SUCCEEDED' or receipt.project_id != intent.project_id
                    or receipt.connection_id != connection.connection_id or receipt.environment != connection.environment
                    or receipt.operation_id != expected.operation_id or receipt.operation_digest != operation_digest(expected)
                    or receipt.resource_key != expected.resource_key):
                raise ValueError('Unauthenticated or out-of-order predecessor')
            _normalized(intent, done.snapshot)
            _effect(intent, connection, files, expected, receipt, done.proof, before, done.snapshot, bindings)
            before = done.snapshot
        if snapshot != before:
            raise ValueError('Current readback differs from proven history')
        versions, identities = _conditions(intent, snapshot, bindings)
        expected_refs = {step.resource_ref for step in intent.steps if step.kind in {'create_owned_media', 'create_owned_page', 'create_product_draft'}}
        if not isinstance(proofs, dict) or set(proofs) != expected_refs:
            raise ValueError('Missing current identity proof')
        for ref in expected_refs:
            create = next(step for step in intent.steps if step.resource_ref == ref)
            if create.kind == 'create_owned_media':
                state = {'sha256': create.payload['image']['sha256'], 'exists': ref in bindings}
                if ref in bindings: state['attachment'] = bindings[ref][1]
                proof = proofs[ref]
                if (not isinstance(proof, dict) or set(proof) != {'resource_key', 'state', 'fingerprint'}
                        or proof['resource_key'] != ref or proof['state'] != state
                        or proof['state'].get('exists') is not state['exists'] or proof['fingerprint'] != digest(state)):
                    raise ValueError('Current image version differs from proven creation')
                continue
            kind, name = ('page', 'slug') if create.kind == 'create_owned_page' else ('product', 'sku')
            identity = create.payload['slug'] if name == 'slug' else create.payload['product']['sku'].strip().casefold()
            state = {name: identity, 'exists': ref in bindings}
            if ref in bindings:
                entity = bindings[ref][1]
                state.update({kind + '_id': entity['id'], 'entity_fingerprint': digest(entity)})
            proof = proofs[ref]
            if (set(proof) != {'resource_key', 'state', 'fingerprint'} or proof['resource_key'] != ref or proof['state'] != state
                    or proof['state'].get('exists') is not state['exists'] or proof['fingerprint'] != digest(state)
                    or (ref in bindings and type(proof['state'].get(kind + '_id')) is not int)):
                raise ValueError('Current identity proof differs')
        if complete:
            return versions
        return SiteStepProjection(intent.digest, index, intent.steps[index].key,
                                  _operation(intent, code, index, bindings, versions, connection), versions, identities)
    except CommerceFailure:
        raise CommerceFailure('REVIEW_STALE') from None
    except (ValueError, TypeError, KeyError, AttributeError, StopIteration, zipfile.BadZipFile):
        raise CommerceFailure('REVIEW_STALE') from None


def project_site_step(intent, connection, code, index, history, snapshot, proofs):
    return _project(intent, connection, code, index, history, snapshot, proofs)


def validate_site_completion(intent, connection, code, history, snapshot, proofs):
    return _project(intent, connection, code, len(intent.steps), history, snapshot, proofs, complete=True)
