import copy
import io
import zipfile

import pytest

from muse.commerce.code_bridge import load_captured_code
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_release_approval import product_review  # noqa: F401


@pytest.fixture
def stage(product_review):  # noqa: F811 - registered pytest fixture
    repo, project, plan, _intent, _verification, _connection, _clock = product_review
    code = load_captured_code(repo, plan)
    with zipfile.ZipFile(io.BytesIO(code.archive)) as archive:
        files = {item['path']: archive.read('muse-storefront/' + item['path']) for item in code.package.files_manifest}
    pages = [{'id': 100 + i, 'slug': p.slug, 'title': p.title, 'content': '', 'status': 'publish',
              'template': 'page-' + p.kind if p.kind in {'cart', 'checkout', 'about', 'contact'} else 'default',
              'muse_project_id': project.id} for i, p in enumerate(plan.blueprint.pages) if p.kind != 'product']
    templates = [{'id': 'muse-storefront//' + name.rsplit('/', 1)[-1].removesuffix('.html'),
                  'slug': name.rsplit('/', 1)[-1].removesuffix('.html'),
                  'type': 'wp_template_part' if name.startswith('parts/') else 'wp_template',
                  'source': 'theme', 'content': content.decode()}
                 for name, content in files.items() if name.endswith('.html')]
    wire = {'pages': pages, 'products': [{'id': 201, 'sku': 'CUP', 'name': 'Cup', 'price': '10.00',
             'regular_price': '10.00', 'sale_price': '', 'manage_stock': True, 'stock_quantity': 3,
             'backorders': 'no', 'description': '', 'status': 'publish', 'type': 'simple', 'muse_project_id': project.id,
             'image_id': 0, 'gallery_image_ids': []}],
            'settings': {'currency': project.brief.currency, 'language': project.brief.language,
                         'shipping_confirmed': True, 'payment_confirmed': True,
                         **{p.kind + '_page_id': next(item['id'] for item in pages if item['slug'] == p.slug)
                            for p in plan.blueprint.pages if p.kind in {'home', 'shop', 'cart', 'checkout'}}},
            'theme_identity': {'stylesheet': 'muse-storefront', 'files_sha256': {item['path']: item['sha256'] for item in code.package.files_manifest},
                               'effective_templates': templates, 'global_styles': {'styles': {}}, 'owned_navigation': {'items': []}}}
    return plan, code, normalize_snapshot(wire, project.id, 'staging')


def test_staging_facts_verify_real_code_binding_pages_and_exact_product(stage):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot = stage
    result = verify_staging_facts(plan, code, snapshot)
    assert result['passed'] is True
    assert result['snapshot_hash'] and result['source_digest'] == code.source_digest
    assert set(result['checks']) == {'theme_sources', 'pages', 'product_facts', 'media'}
    assert result['site_verified'] is False  # No browser, buyer or OS probe ran here.


@pytest.mark.parametrize('attack', ['price', 'stock', 'description', 'image', 'page_owner', 'page_title', 'page_missing',
    'page_template', 'settings_page', 'currency', 'language', 'shipping', 'payment', 'theme_file', 'template_override',
    'template_missing', 'source', 'wrong_project', 'live', 'duplicate_sku'])
def test_staging_facts_reject_each_unapproved_or_missing_effect(stage, attack):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot = stage
    wire = copy.deepcopy(snapshot.model_dump(mode='json'))
    if attack in {'price', 'stock', 'description', 'image'}:
        field, value = {'price': ('price', '20.00'), 'stock': ('stock_quantity', 0),
                        'description': ('description', 'Unsupported claim'), 'image': ('image_id', 999)}[attack]
        wire['products'][0][field] = value
    elif attack == 'page_owner': wire['pages'][0]['muse_project_id'] = 'another-project'
    elif attack == 'page_title': wire['pages'][0]['title'] = 'Unreviewed title'
    elif attack == 'page_missing': wire['pages'].pop()
    elif attack == 'page_template': wire['pages'][0]['template'] = 'external-theme'
    elif attack == 'settings_page': wire['settings']['home_page_id'] = 999
    elif attack == 'currency': wire['settings']['currency'] = 'EUR'
    elif attack == 'language': wire['settings']['language'] = 'de-DE'
    elif attack in {'shipping', 'payment'}: wire['settings'][attack + '_confirmed'] = False
    elif attack == 'theme_file': wire['theme_identity']['files_sha256']['style.css'] = 'f' * 64
    elif attack == 'template_override': wire['theme_identity']['effective_templates'][0]['content'] += 'unexpected text'
    elif attack == 'template_missing': wire['theme_identity']['effective_templates'].pop()
    elif attack == 'source': plan.content_hash = 'f' * 64
    elif attack == 'wrong_project': wire['project_id'] = 'another-project'
    elif attack == 'live': wire['environment'] = 'live'
    else:
        wire['products'].append({**wire['products'][0], 'id': 202})
    changed = normalize_snapshot(wire, wire['project_id'], wire['environment'])
    with pytest.raises(CommerceFailure):
        verify_staging_facts(plan, code, changed)


def navigation_stage(stage):
    import json

    from muse.commerce_connector.wordpress import WordPressConnection
    plan, code, snapshot = stage
    connection = WordPressConnection('stage', plan.project_id, 'staging', 'https://shop.test', 'scope', 'not-used')
    pages = {item['slug']: item['id'] for item in snapshot.pages}
    content = ''.join('<!-- wp:navigation-link ' + json.dumps({'label': item.label, 'type': 'page',
        'id': pages[item.slug], 'kind': 'post-type', 'url': connection.base_url + '/?page_id=' + str(pages[item.slug])},
        ensure_ascii=False, separators=(',', ':')) + ' /-->' for item in plan.blueprint.navigation)
    snapshot.theme_identity['owned_navigation'] = {'items': [{'id': 301, 'content': content, 'status': 'publish',
                                                             'muse_project_id': plan.project_id}]}
    header = next(item for item in snapshot.theme_identity['effective_templates'] if item['slug'] == 'header')
    header['source'] = 'custom'
    header['content'] = ('<!-- wp:group {"layout":{"type":"flex","justifyContent":"space-between"}} --><div class="wp-block-group">'
                         '<!-- wp:site-title /--><!-- wp:navigation {"ref":301,"overlayMenu":"mobile"} /--></div><!-- /wp:group -->')
    return plan, code, normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging'), connection


def test_staging_accepts_only_exact_owned_navigation_header_effect(stage):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot, connection = navigation_stage(stage)
    assert verify_staging_facts(plan, code, snapshot, connection=connection)['passed'] is True


def test_navigation_must_not_hide_loss_of_developer_header_content(stage, tmp_path):
    from muse.commerce.coding import SourceStore
    from muse.commerce.theme import render_site_files
    from muse.commerce.verification import verify_staging_facts
    from tests.muse.commerce.test_coding_artifact import archive
    plan, _code, snapshot, connection = navigation_stage(stage)
    files = render_site_files(plan.blueprint, plan.products)
    files['parts/header.html'] = files['parts/header.html'].replace(b'<!-- wp:site-title /-->',
        b'<!-- wp:site-title /--><!-- wp:paragraph --><p>Merchant approved welcome</p><!-- /wp:paragraph -->')
    code = SourceStore(tmp_path / 'custom-header').seal(archive(files), project_id=plan.project_id, plan_id=plan.id,
        snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    snapshot.theme_identity['files_sha256'] = {item['path']: item['sha256'] for item in code.package.files_manifest}
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging')
    with pytest.raises(CommerceFailure):
        verify_staging_facts(plan, code, snapshot, connection=connection)


@pytest.mark.parametrize('attack', ['label', 'foreign_link', 'id_bool', 'page_id', 'order', 'owner', 'header_ref', 'extra', 'scope'])
def test_staging_rejects_edited_navigation_and_indirect_template_effect(stage, attack):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot, connection = navigation_stage(stage)
    item = snapshot.theme_identity['owned_navigation']['items'][0]
    if attack == 'label': item['content'] = item['content'].replace('Home', 'Unreviewed')
    elif attack == 'foreign_link': item['content'] = item['content'].replace('https://shop.test', 'https://foreign.test')
    elif attack == 'id_bool': item['content'] = item['content'].replace('"id":100', '"id":true')
    elif attack == 'page_id': item['content'] = item['content'].replace('"id":100', '"id":999')
    elif attack == 'order': item['content'] = item['content'].replace('Home', 'Shop', 1)
    elif attack == 'owner': item['muse_project_id'] = 'other'
    elif attack == 'header_ref':
        header = next(t for t in snapshot.theme_identity['effective_templates'] if t['slug'] == 'header')
        header['content'] = header['content'].replace('301', '302')
    elif attack == 'extra': item['content'] += '<p>Unsigned navigation content</p>'
    else:
        from muse.commerce_connector.wordpress import WordPressConnection
        connection = WordPressConnection('other', 'other', 'staging', 'https://shop.test', 'scope', 'not-used')
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging')
    with pytest.raises(CommerceFailure):
        verify_staging_facts(plan, code, snapshot, connection=connection)


def test_staging_accepts_exact_wordpress_theme_attribute_and_fixed_woo_header_hooks(stage):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot, connection = navigation_stage(stage)
    for item in snapshot.theme_identity['effective_templates']:
        if item['type'] == 'wp_template':
            item['content'] = item['content'].replace('"tagName":"header"}', '"tagName":"header","theme":"muse-storefront"}')
            item['content'] = item['content'].replace('"tagName":"footer"}', '"tagName":"footer","theme":"muse-storefront"}')
        if item['slug'] == 'header':
            item['content'] = item['content'].replace('"overlayMenu":"mobile"}',
                '"overlayMenu":"mobile","metadata":{"ignoredHookedBlocks":["woocommerce/customer-account"]}}')
            item['content'] = item['content'].replace('</div>',
                '<!-- wp:woocommerce/customer-account {"displayStyle":"icon_only","iconStyle":"line","iconClass":"wc-block-customer-account__account-icon"} /-->'
                '<!-- wp:woocommerce/mini-cart /--></div>')
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging')
    assert verify_staging_facts(plan, code, snapshot, connection=connection)['passed'] is True
    header = next(item for item in snapshot.theme_identity['effective_templates'] if item['slug'] == 'header')
    header['content'] = header['content'].replace('icon_only', 'unapproved')
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging')
    with pytest.raises(CommerceFailure):
        verify_staging_facts(plan, code, snapshot, connection=connection)


def test_staging_front_page_navigation_uses_actual_home_permalink(stage):
    from muse.commerce.verification import verify_staging_facts
    plan, code, snapshot, connection = navigation_stage(stage)
    snapshot.settings.update({'permalink_structure': '/%year%/%monthnum%/%day%/%postname%/', 'show_on_front': 'page'})
    item = snapshot.theme_identity['owned_navigation']['items'][0]
    for page in snapshot.pages:
        previous = connection.base_url + '/?page_id=' + str(page['id'])
        actual = connection.base_url + ('/' if page['id'] == snapshot.settings['home_page_id'] else '/' + page['slug'] + '/')
        item['content'] = item['content'].replace(previous, actual)
    snapshot = normalize_snapshot(snapshot.model_dump(mode='json'), plan.project_id, 'staging')
    assert verify_staging_facts(plan, code, snapshot, connection=connection)['passed'] is True
