"""Independent staging readback checks. Not an OS/browser/buyer attestation.

Only the trusted verifier may combine these checks with real probe results.
No report, approval, HTTP request or write permit is produced by this module.
"""
import io
import json
import re
import zipfile

from muse.commerce.coding import verify_coding_artifact
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan, StoreSnapshot
from muse.commerce.release_steps import _approved_product_facts
from muse.commerce.repository import digest
from muse.commerce.theme import ALLOWED_FILES
from muse.commerce_connector.wordpress import WordPressConnection

PAGE_TEMPLATES = {'home': 'default', 'shop': 'default', 'cart': 'page-cart', 'checkout': 'page-checkout',
                  'about': 'page-about', 'contact': 'page-contact'}


def _unique_attributes(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate block attribute')
        result[key] = value
    return result


def _materialize_header(content, navigation_id):
    pattern = r'<!-- wp:navigation(?: (\{.*?\}))?\s*(?:/-->|-->(.*?)<!-- /wp:navigation -->)'
    matches = list(re.finditer(pattern, content, re.DOTALL))
    if len(matches) != 1:
        raise ValueError('Exactly one header navigation is required')
    match = matches[0]
    attrs = json.loads(match.group(1) or '{}', object_pairs_hook=_unique_attributes)
    if not isinstance(attrs, dict):
        raise TypeError('Invalid navigation attributes')
    attrs['ref'] = navigation_id
    block = '<!-- wp:navigation ' + json.dumps(attrs, ensure_ascii=False, separators=(',', ':')) + ' /-->'
    return content[:match.start()] + block + content[match.end():]


def _canonical_header(content):
    def canonical(match):
        attrs = json.loads(match.group(2), object_pairs_hook=_unique_attributes)
        return match.group(1) + json.dumps(attrs, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + match.group(3)
    content = re.sub(r'(<!-- wp:[\w/-]+ )(\{.*?\})(\s*/?-->)', canonical, content, flags=re.DOTALL)
    return re.sub(r'>\s+<', '><', content).strip()


def _navigation_header(plan, snapshot, connection, source_header, *, environment='staging'):
    items = snapshot.theme_identity.get('owned_navigation', {}).get('items', [])
    if not items:
        return None
    if (not isinstance(connection, WordPressConnection) or connection.project_id != plan.project_id
            or connection.environment != environment or snapshot.environment != environment or len(items) != 1):
        raise ValueError('Invalid staging/navigation scope')
    item = items[0]
    if (type(item.get('id')) is not int or item['id'] <= 0 or item.get('status') != 'publish'
            or item.get('muse_project_id') != plan.project_id):
        raise ValueError('Navigation is not owned')
    content = item.get('content', '')
    pattern = r'<!-- wp:navigation-link (.*?) /-->'
    matches = list(re.finditer(pattern, content, re.DOTALL))
    from muse.commerce.store_configuration import category_targets, resolve_category
    targets = category_targets(plan.blueprint, getattr(plan, 'products', []))
    if re.sub(pattern, '', content, flags=re.DOTALL).strip() or len(matches) != len(plan.blueprint.navigation)+len(targets):
        raise ValueError('Unexpected navigation blocks')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate navigation attribute')
            result[key] = value
        return result
    structure = snapshot.settings.get('permalink_structure')
    if structure not in {None, '', '/%postname%/', '/%year%/%monthnum%/%day%/%postname%/'}:
        raise ValueError('Unsupported staging permalink structure')
    for match, reference in zip(matches[:len(plan.blueprint.navigation)], plan.blueprint.navigation, strict=True):
        pages = [page for page in snapshot.pages if page.get('slug') == reference.slug]
        if len(pages) != 1:
            raise ValueError('Unresolved navigation page')
        page = pages[0]
        url = connection.base_url + ('/' + reference.slug + '/' if structure else '/?page_id=' + str(page['id']))
        if snapshot.settings.get('show_on_front') == 'page' and page['id'] == snapshot.settings.get('home_page_id'):
            url = connection.base_url + '/'
        attrs = json.loads(match.group(1), object_pairs_hook=unique)
        if (attrs != {'label': reference.label, 'type': 'page', 'id': page['id'], 'kind': 'post-type', 'url': url}
                or type(attrs.get('id')) is not int):
            raise ValueError('Navigation facts or URL changed')
    for match, reference in zip(matches[len(plan.blueprint.navigation):], targets, strict=True):
        category = resolve_category(snapshot.products, reference.category, connection)
        attrs = json.loads(match.group(1), object_pairs_hook=unique)
        if (attrs != {'label':reference.label,'type':'product_cat','id':category['id'],'kind':'taxonomy','url':category['url']}
            or type(attrs.get('id')) is not int):
            raise ValueError('Category navigation facts or permalink changed')
    return _materialize_header(source_header, item['id'])


def _theme_attributes(content):
    def inject(match):
        attrs = json.loads(match.group(1))
        if attrs.get('theme') not in {None, 'muse-storefront'} or attrs.get('slug') not in {'header', 'footer'}:
            raise ValueError('Foreign template part')
        attrs['theme'] = 'muse-storefront'
        return '<!-- wp:template-part ' + json.dumps(attrs, ensure_ascii=False, separators=(',', ':')) + ' /-->'
    return re.sub(r'<!-- wp:template-part (.*?) /-->', inject, content)


def _woo_header(content):
    # Fixed, observed Woo 11.1.2 hooks; no general relaxation for plugin output.
    def metadata(match):
        attrs = json.loads(match.group(1), object_pairs_hook=_unique_attributes)
        attrs['metadata'] = {'ignoredHookedBlocks': ['woocommerce/customer-account']}
        return '<!-- wp:navigation ' + json.dumps(attrs, ensure_ascii=False, separators=(',', ':')) + match.group(2)
    content = re.sub(r'<!-- wp:navigation (\{[^<>]*?\})(\s*/?-->)', metadata, content, flags=re.DOTALL)
    before, separator, after = content.rpartition('</div>')
    if not separator:
        return content
    return before + (
        '<!-- wp:woocommerce/customer-account {"displayStyle":"icon_only","iconStyle":"line","iconClass":"wc-block-customer-account__account-icon"} /-->'
        '<!-- wp:woocommerce/mini-cart /--></div>') + after


def _approved_media(plan, images, proofs, connection):
    from muse.commerce_connector.media import MediaPayload, RemoteAttachment
    from muse.commerce.design_resources import source_media_refs
    refs = source_media_refs(plan.blueprint, plan.products)
    frozen = [MediaPayload.model_validate(image.model_dump(mode='json')) for image in (images or [])]
    proofs = {} if proofs is None else proofs
    if (refs != [image.media_ref for image in frozen] or not isinstance(proofs, dict)
            or set(proofs) != {'media-sha256:' + image.image.sha256 for image in frozen}
            or (refs and (not isinstance(connection, WordPressConnection)
                or connection.project_id != plan.project_id or connection.environment != 'staging'))):
        raise ValueError('Missing exact approved staging image source')
    bindings = {}
    for image in frozen:
        sha = image.image.sha256; key = 'media-sha256:' + sha; proof = proofs[key]
        if (image.media_ref != digest([plan.project_id, 'image', sha])
                or not isinstance(proof, dict) or set(proof) != {'resource_key', 'state', 'fingerprint'}
                or proof['resource_key'] != key or not isinstance(proof['state'], dict)
                or set(proof['state']) != {'sha256', 'exists', 'attachment'}
                or proof['state']['sha256'] != sha or proof['state']['exists'] is not True
                or proof['fingerprint'] != digest(proof['state'])):
            raise ValueError('Staging attachment proof differs')
        entity = RemoteAttachment.model_validate(proof['state']['attachment'])
        expected = {**image.image.model_dump(), 'id': entity.id, 'media_ref': image.media_ref,
            'muse_project_id': plan.project_id, 'status': 'inherit', 'parent_id': 0,
            'title': 'MUSE image ' + sha, 'alt': ''}
        if entity.model_dump() != expected or entity.id in bindings.values():
            raise ValueError('Staging attachment facts changed')
        bindings[image.media_ref] = entity.id
    return bindings


def verify_staging_facts(plan, code, snapshot, *, connection=None, images=None, media_proofs=None):
    try:
        if (not isinstance(plan, CommercePlan) or not isinstance(snapshot, StoreSnapshot)
                or plan.blueprint is None or snapshot.environment != 'staging'
                or plan.project_id != snapshot.project_id or plan.project_id != code.project_id
                or plan.id != code.plan_id or plan.snapshot_hash != code.snapshot_hash
                or plan.code_revision != code.package.code_revision or plan.content_hash != code.package.content_sha256
                or digest({'blueprint': plan.blueprint.model_dump(mode='json'),
                           'products': [p.model_dump(mode='json') for p in plan.products]}) != plan.content_hash
                or normalize_snapshot(snapshot.model_dump(mode='json'), snapshot.project_id, 'staging') != snapshot):
            raise ValueError('Invalid source/staging binding')
        verify_coding_artifact(code)
        if 'shipping_rules' in plan.blueprint.required_settings:
            from muse.commerce.store_configuration import shipping_effect
            state = snapshot.settings.get('shipping_configuration')
            shipping_effect(state, state, plan.project_id, plan.blueprint.required_settings['shipping_rules'])
        expected_hashes = {item['path']: item['sha256'] for item in code.package.files_manifest}
        theme = snapshot.theme_identity
        if (theme.get('stylesheet') != 'muse-storefront' or theme.get('files_sha256') != expected_hashes
                ):
            raise ValueError('Staged theme source differs')
        with zipfile.ZipFile(io.BytesIO(code.archive)) as archive:
            files = {name: archive.read('muse-storefront/' + name).decode() for name in ALLOWED_FILES if name.endswith('.html')}
        templates = theme.get('effective_templates', [])
        header = _navigation_header(plan, snapshot, connection, files['parts/header.html'])
        for path, content in files.items():
            slug = path.rsplit('/', 1)[-1].removesuffix('.html')
            kind = 'wp_template_part' if path.startswith('parts/') else 'wp_template'
            expected_source = 'theme'
            if path == 'parts/header.html' and header is not None:
                content, expected_source = header, 'custom'
            matches = [item for item in templates if item.get('slug') == slug and item.get('type') == kind]
            allowed_content = {content, _theme_attributes(content)}
            if path == 'parts/header.html':
                allowed_content.add(_woo_header(content))
                allowed_content = {_canonical_header(value) for value in allowed_content}
            actual = matches[0].get('content') if len(matches) == 1 else None
            if path == 'parts/header.html' and isinstance(actual, str):
                actual = _canonical_header(actual)
            if (len(matches) != 1 or matches[0].get('id') != 'muse-storefront//' + slug
                    or matches[0].get('source') != expected_source or actual not in allowed_content):
                raise ValueError('Effective template differs')
        settings = snapshot.settings
        language = plan.blueprint.required_settings.get('language')
        currency = plan.blueprint.required_settings.get('currency')
        if (settings.get('language') != language or settings.get('currency') != currency
                or settings.get('shipping_confirmed') is not True or settings.get('payment_confirmed') is not True):
            raise ValueError('Staging settings incomplete')
        page_ids = {}
        for page in plan.blueprint.pages:
            if page.kind == 'product':
                continue  # Product detail is Woo's single-product route, not another page.
            matches = [item for item in snapshot.pages if item.get('slug') == page.slug]
            if (len(matches) != 1 or matches[0].get('muse_project_id') != plan.project_id
                    or matches[0].get('status') != 'publish' or matches[0].get('title') != page.title
                    or matches[0].get('template') != PAGE_TEMPLATES[page.kind] or matches[0].get('content') != ''):
                raise ValueError('Staged page differs')
            page_ids[page.kind] = matches[0]['id']
        if any(settings.get(kind + '_page_id') != page_ids[kind] for kind in ('home', 'shop', 'cart', 'checkout')):
            raise ValueError('Storefront page association differs')
        media_ids = _approved_media(plan, images, media_proofs, connection)
        products = {}
        for product in plan.products:
            if len(set(product.media_refs)) != len(product.media_refs):
                raise ValueError('Duplicate approved product image')
            image_ids = [media_ids[ref] for ref in product.media_refs]
            matches = [item for item in snapshot.products if item.get('sku', '').strip().casefold() == product.sku.strip().casefold()]
            if (len(matches) != 1 or matches[0].get('muse_project_id') != plan.project_id
                    or matches[0].get('status') != 'publish' or matches[0].get('image_id', 0) != (image_ids[0] if image_ids else 0)
                    or matches[0].get('gallery_image_ids', []) != image_ids[1:]):
                raise ValueError('Staged product or media association differs')
            _approved_product_facts(product, matches[0])
            products[product.sku] = matches[0]['id']
        return {'passed': True, 'site_verified': False, 'source_digest': code.source_digest,
                'snapshot_hash': digest(snapshot), 'page_ids': page_ids, 'product_ids': products, 'media_ids': media_ids,
                'checks': ['theme_sources', 'pages', 'product_facts', 'media']}
    except CommerceFailure as error:
        if error.public.code == 'UNSUPPORTED_CAPABILITY':
            raise
        raise CommerceFailure('VERIFICATION_FAILED', 422) from None
    except (ValueError, TypeError, AttributeError, KeyError, OSError, zipfile.BadZipFile):
        raise CommerceFailure('VERIFICATION_FAILED', 422) from None
