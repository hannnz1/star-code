"""Opt-in real CMS tests against a disposable loopback station, never a merchant store."""
import base64
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.models import ApprovalGrant, ChangeOperation
from muse.commerce.repository import digest
from muse.commerce_connector.authorization import ExecutionAuthority
from muse.commerce_connector.wordpress import WordPressConnection, WordPressReader


class FixturePrivate(dict):
    def __repr__(self):
        return '<disposable fixture credentials hidden>'


@pytest.mark.asyncio
async def test_real_setup_requires_admin_confirmation_and_enabled_payment(local_store):
    connection, _ = local_store
    reader = WordPressReader(connection)
    old = fixture_action({'action': 'store_setup', 'confirmed': False})['old']
    try:
        before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        assert before.settings['shipping_confirmed'] is False
        assert before.settings['payment_confirmed'] is False
        fixture_action({'action': 'store_setup', 'confirmed': True})
        confirmed = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        assert confirmed.settings['shipping_confirmed'] is True
        assert confirmed.settings['payment_confirmed'] is True
        assert confirmed.resource_fingerprints['settings'] != before.resource_fingerprints['settings']
        fixture_action({'action': 'store_setup', 'confirmed': True, 'disable_payment': True})
        disabled = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        assert disabled.settings['payment_confirmed'] is False
        assert disabled.resource_fingerprints['settings'] != confirmed.resource_fingerprints['settings']
        async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password)) as client:
            response = await client.post(connection.base_url + '/wp-admin/admin-post.php',
                                         data={'action': 'muse_confirm_store_setup', 'payment_confirmed': 'yes'})
        assert response.status_code in (400, 403)
        assert (normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
                .settings['payment_confirmed']) is False
    finally:
        fixture_action({'action': 'store_setup', 'restore': old})


@pytest.mark.asyncio
async def test_real_two_product_release_uses_v2_receipts_and_symbolic_ids(local_store, tmp_path):
    from muse.commerce.models import (
        CommercePlan,
        EnvironmentRef,
        ProductDraft,
        SiteBrief,
        StoreProject,
    )
    from muse.commerce.release import prepare_product_release
    from muse.commerce.release_steps import CompletedProductStep
    from muse.commerce.site import build_site_blueprint
    from muse.commerce_connector.operation_ledger import OperationLedger
    from muse.commerce_connector.publisher import confirm_operation_receipt
    from muse.commerce_connector.release_authorization import (
        ProductReleaseAuthority,
        ProductReleaseGrant,
    )
    connection, private = local_store
    reader = WordPressReader(connection)
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    brief = SiteBrief(brand_name='Fixture', language='en-US', currency=snapshot.settings['currency'])
    target = EnvironmentRef(id='staging', project_id='project', environment='staging', connector_ref='connection',
                            public_url=connection.base_url)
    project = StoreProject(id='project', workspace_id='fixture', brief=brief, environment_refs=[target])
    suffix = uuid.uuid4().hex
    products = [ProductDraft(sku=f'release-{suffix}-{index}', title=f'Fixture release {index}', price='12.30',
                            stock=3, currency=brief.currency) for index in range(2)]
    blueprint = build_site_blueprint(brief, snapshot)
    plan = CommercePlan(id='fixture-plan', project_id='project', kind='launch_products', state='VERIFYING',
        products=products, blueprint=blueprint, snapshot_hash=digest(snapshot), code_revision='c' * 40,
        content_hash=digest({'blueprint': blueprint.model_dump(mode='json'),
                             'products': [p.model_dump(mode='json') for p in products]}))
    proofs = {}
    for product in products:
        proof = await reader.read_sku(product.sku, remaining_seconds=20)
        proofs[proof['resource_key']] = proof
    intent = prepare_product_release(project, plan, target, snapshot, proofs, connection=connection)
    now = time.time()
    grant = ProductReleaseGrant('fixture-root', intent.digest, 'project', 'connection', 'staging', connection.base_url,
                                 'e' * 64, now, now + 300, 'approved')
    authority = ProductReleaseAuthority(private['signing_secret'].encode())
    ledger = OperationLedger(tmp_path / 'operations.sqlite')
    ledger.bind_target('project', 'connection', 'staging', connection.base_url)
    history = []
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password), timeout=20) as client:
        for index in range(4):
            token = authority.issue(grant, intent, connection, index, history, snapshot, proofs)
            projected = authority.verify(token, grant, intent, connection, index, history, snapshot, proofs)
            operation = projected.operation
            ledger.prepare('project', 'connection', 'staging', operation)
            local = ledger.begin('project', 'connection', 'staging', operation.operation_id)
            response = await client.post(connection.base_url + '/wp-json/muse/v1/operations',
                json={'operation': operation.model_dump(mode='json'), 'execution_authorization': token})
            assert response.status_code == 200
            receipt = confirm_operation_receipt(ledger, local, response.content)
            assert receipt.state == 'SUCCEEDED'
            repeated = await client.post(connection.base_url + '/wp-json/muse/v1/operations',
                json={'operation': operation.model_dump(mode='json'), 'execution_authorization': token})
            assert repeated.status_code == 200 and repeated.json() == response.json()
            snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
            for product in products:
                proof = await reader.read_sku(product.sku, remaining_seconds=20)
                proofs[proof['resource_key']] = proof
            history.append(CompletedProductStep(operation, receipt, snapshot,
                           proofs[intent.steps[index].resource_ref]))
    actual = [p for p in snapshot.products if p['sku'] in {product.sku for product in products}]
    assert len(actual) == 2
    assert all(p['status'] == 'publish' and p['price'] == '12.30' and p['stock_quantity'] == 3 for p in actual)


@pytest.mark.asyncio
async def test_real_price_source_inventory_and_category_edit_invalidates_old_publish(local_store):
    connection, _ = local_store
    sku = 'version-' + uuid.uuid4().hex
    identity = fixture_action({'action': 'product_version_probe', 'sku': sku})['id']
    reader = WordPressReader(connection)
    before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    proof = await reader.read_sku(sku, remaining_seconds=20)
    fixture_action({'action': 'product_version_probe', 'id': identity})
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    original = next(p for p in before.products if p['id'] == identity)
    changed = next(p for p in after.products if p['id'] == identity)
    assert original['price'] == changed['price']
    assert original['regular_price'] != changed['regular_price']
    assert original['manage_stock'] is True and changed['manage_stock'] is False
    assert changed['category_ids']
    assert changed['categories'][0]['id'] == changed['category_ids'][0]
    renamed = 'Fixture renamed ' + sku
    fixture_action({'action': 'rename_category', 'id': changed['category_ids'][0], 'name': renamed})
    renamed_snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    renamed_product = next(p for p in renamed_snapshot.products if p['id'] == identity)
    assert renamed_product['category_ids'] == changed['category_ids']
    assert renamed_product['categories'][0]['name'] == renamed
    assert renamed_snapshot.resource_fingerprints[f'product:{identity}'] != after.resource_fingerprints[f'product:{identity}']
    assert after.resource_fingerprints[f'product:{identity}'] != before.resource_fingerprints[f'product:{identity}']
    assert (await reader.read_sku(sku, remaining_seconds=20))['fingerprint'] != proof['fingerprint']
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='publish_product',
        resource_key=f'product:{identity}', expected_fingerprint=before.resource_fingerprints[f'product:{identity}'],
        payload={'product_id': identity})
    result = await signed_operation(local_store, operation)
    assert result.status_code == 200 and result.json()['state'] == 'FAILED'


@pytest.fixture(scope='module')
def local_store():
    filename = os.environ.get('MUSE_DISPOSABLE_WP_FIXTURE')
    if not filename:
        pytest.skip('Explicit disposable WordPress fixture required')
    private = FixturePrivate(json.loads(Path(filename).read_text(encoding='utf-8')))
    connection = WordPressConnection('connection', 'project', 'staging', private['target_url'],
                                    private.get('service_username', 'fixture_admin'), private['application_password'], approved_development_http=True)
    if not private['target_url'].startswith('http://127.0.0.1:'):
        raise ValueError('This test suite only accepts an explicit disposable loopback fixture')
    return connection, private


def fixture_action(action):
    root = Path(__file__).resolve().parents[3]
    php = root / 'work/tools/php-8.4.26/php.exe'
    args = [str(php), '-n', '-d', 'extension_dir=' + str(php.parent / 'ext'), '-d', 'memory_limit=512M',
            '-d', 'display_errors=stderr']
    for extension in ['mysqli', 'mbstring', 'openssl', 'curl', 'fileinfo', 'zip']:
        args += ['-d', 'extension=' + extension]
    result = subprocess.run(args + [str(root / 'tests/fixtures/commerce/wp-functional.php'),
                                   str(root / 'work/tools/wordpress/wordpress')],
                            input=json.dumps(action), text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


async def signed_operation(local_store, operation, dependencies=None, headers=None):
    connection, private = local_store
    grant = ApprovalGrant(id='fixture-grant', project_id='project', environment='staging',
                          changeset_digest='c' * 64, resource_preconditions={operation.resource_key: operation.expected_fingerprint, **(dependencies or {})},
                          verification_hash='e' * 64, expires_at=time.time() + 300)
    token = ExecutionAuthority(private['signing_secret'].encode()).issue(grant, connection, operation)
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password), timeout=20) as client:
        return await client.post(connection.base_url + '/wp-json/muse/v1/operations', headers=headers,
                                 json={'operation': operation.model_dump(mode='json'), 'execution_authorization': token})


@pytest.mark.asyncio
async def test_real_owned_page_write_repeats_as_identical_receipt(local_store):
    connection, _ = local_store
    page_id = fixture_action({'action': 'create_page', 'owned': True})['id']
    reader = WordPressReader(connection)
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='update_owned_page',
                                resource_key=f'page:{page_id}', expected_fingerprint=snapshot.resource_fingerprints[f'page:{page_id}'],
                                payload={'page_id': page_id, 'title': '商家标题😀', 'content': 'Approved merchant text'})
    first = await signed_operation(local_store, operation)
    assert first.status_code == 200, first.text
    assert first.json()['state'] == 'SUCCEEDED'
    second = await signed_operation(local_store, operation)
    assert second.status_code == 200 and second.json() == first.json()
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password)) as client:
        receipt = await client.get(connection.base_url + '/wp-json/muse/v1/receipts/' + operation.operation_id)
    assert receipt.status_code == 200 and receipt.json() == first.json()
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    assert next(page for page in after.pages if page['id'] == page_id)['content'] == operation.payload['content']
    assert after.resource_fingerprints[f'page:{page_id}'] == first.json()['fingerprint']


@pytest.mark.asyncio
@pytest.mark.parametrize('conflict', ['unowned', 'manual_edit'])
async def test_real_page_conflict_does_not_overwrite_merchant_content(local_store, conflict):
    connection, _ = local_store
    page_id = fixture_action({'action': 'create_page', 'owned': conflict != 'unowned'})['id']
    reader = WordPressReader(connection)
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    if conflict == 'manual_edit':
        fixture_action({'action': 'edit_page', 'id': page_id, 'content': 'Merchant edited'})
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='update_owned_page',
                                resource_key=f'page:{page_id}', expected_fingerprint=snapshot.resource_fingerprints[f'page:{page_id}'],
                                payload={'page_id': page_id, 'title': 'Must not write', 'content': 'Must not write'})
    response = await signed_operation(local_store, operation)
    assert response.status_code == 200, response.text
    assert response.json()['state'] == 'FAILED'
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    page = next(page for page in after.pages if page['id'] == page_id)
    assert page['content'] == ('Merchant edited' if conflict == 'manual_edit' else 'Before')


@pytest.mark.asyncio
async def test_real_product_draft_has_exact_facts_and_duplicate_receipt(local_store):
    connection, _ = local_store
    sku = 'MUSE-FIXTURE-' + uuid.uuid4().hex
    expected = digest({'sku': sku.casefold(), 'exists': False})
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='create_product_draft',
                                resource_key='sku:' + hashlib.sha256(sku.casefold().encode()).hexdigest(),
                                expected_fingerprint=expected,
                                payload={'product': {'sku': sku, 'title': 'Fixture cup', 'price': '19.99', 'currency': 'USD',
                                    'stock': 3, 'description': 'Merchant supplied description', 'category': '',
                                    'source_facts': {}, 'media_refs': []}})
    first = await signed_operation(local_store, operation)
    assert first.status_code == 200 and first.json()['state'] == 'SUCCEEDED', first.text
    second = await signed_operation(local_store, operation)
    assert second.status_code == 200 and second.json() == first.json()
    snapshot = normalize_snapshot(await WordPressReader(connection).read('snapshot', remaining_seconds=20), 'project', 'staging')
    products = [product for product in snapshot.products if product['sku'] == sku]
    assert len(products) == 1
    assert products[0]['status'] == 'draft'
    assert products[0]['price'] == '19.99' and products[0]['stock_quantity'] == 3
    publish = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='publish_product',
                              resource_key=f"product:{products[0]['id']}",
                              expected_fingerprint=snapshot.resource_fingerprints[f"product:{products[0]['id']}"],
                              payload={'product_id': products[0]['id']})
    response = await signed_operation(local_store, publish)
    assert response.status_code == 200 and response.json()['state'] == 'SUCCEEDED', response.text
    after = normalize_snapshot(await WordPressReader(connection).read('snapshot', remaining_seconds=20), 'project', 'staging')
    assert next(product for product in after.products if product['sku'] == sku)['status'] == 'publish'
    collision = operation.model_copy(update={'operation_id': 'fixture-' + uuid.uuid4().hex})
    response = await signed_operation(local_store, collision)
    assert response.status_code == 200 and response.json()['state'] == 'FAILED', response.text


@pytest.mark.asyncio
async def test_real_theme_fingerprint_detects_merchant_css_edit(local_store):
    connection, _ = local_store
    reader = WordPressReader(connection)
    before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    previous = fixture_action({'action': 'edit_css'})['old']
    try:
        after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        assert before.resource_fingerprints['theme'] != after.resource_fingerprints['theme']
    finally:
        fixture_action({'action': 'edit_css', 'content': previous})


@pytest.mark.asyncio
async def test_real_theme_install_preserves_fixed_code_and_returns_durable_receipt(local_store):
    from muse.commerce.models import SiteBrief, StoreSnapshot
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.theme import build_site_archive
    connection, _ = local_store
    reader = WordPressReader(connection)
    before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    blueprint = build_site_blueprint(SiteBrief(brand_name='Installed Merchant Store', language='en-US', currency='USD'),
                                     StoreSnapshot(project_id='project', environment='staging'))
    metadata, data = build_site_archive(blueprint, [], code_revision='a' * 40)
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='install_theme_package',
                                resource_key='theme:muse-storefront', expected_fingerprint=before.resource_fingerprints['theme'],
                                payload={'package': metadata.model_dump(mode='json'), 'archive_base64': base64.b64encode(data).decode()})
    response = await signed_operation(local_store, operation)
    assert response.status_code == 200 and response.json()['state'] == 'SUCCEEDED', response.text
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    assert after.resource_fingerprints['theme'] == response.json()['fingerprint']
    assert after.theme_identity['files_sha256']['functions.php'] == metadata.immutable_code_sha256
    assert after.theme_identity['files_sha256']['templates/front-page.html'] == next(
        entry['sha256'] for entry in metadata.files_manifest if entry['path'] == 'templates/front-page.html')
    repeated = await signed_operation(local_store, operation)
    assert repeated.status_code == 200 and repeated.json() == response.json()


@pytest.mark.asyncio
async def test_real_owned_navigation_binds_page_ids_and_preserves_unowned_templates(local_store):
    connection, _ = local_store
    page_id = fixture_action({'action': 'create_page', 'owned': True})['id']
    reader = WordPressReader(connection)
    before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    key = 'navigation:muse-storefront'
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='set_owned_navigation',
                                resource_key=key, expected_fingerprint=before.resource_fingerprints[key],
                                payload={'items': [{'page_id': page_id, 'label': 'Merchant About'}]})
    dependencies = {'theme:muse-storefront': before.resource_fingerprints['theme'],
                    f'page:{page_id}': before.resource_fingerprints[f'page:{page_id}']}
    response = await signed_operation(local_store, operation, dependencies)
    assert response.status_code == 200 and response.json()['state'] == 'SUCCEEDED', response.text
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    assert after.resource_fingerprints[key] == response.json()['fingerprint']
    owned = after.theme_identity['owned_navigation']['items']
    assert len(owned) == 1 and 'Merchant About' in owned[0]['content']
    repeated = await signed_operation(local_store, operation, dependencies)
    assert repeated.status_code == 200 and repeated.json() == response.json()


@pytest.mark.asyncio
async def test_storefront_options_require_approved_versions_for_every_referenced_page(local_store):
    connection, _ = local_store
    ids = [fixture_action({'action': 'create_page', 'owned': True})['id'] for _ in range(4)]
    reader = WordPressReader(connection)
    before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='set_storefront_options', resource_key='settings',
        expected_fingerprint=before.resource_fingerprints['settings'],
        payload=dict(zip(['home_page_id', 'shop_page_id', 'cart_page_id', 'checkout_page_id'], ids, strict=True)))
    response = await signed_operation(local_store, operation)
    assert response.json()['state'] == 'FAILED'
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    assert after.resource_fingerprints['settings'] == before.resource_fingerprints['settings']


@pytest.mark.asyncio
async def test_real_abrupt_exit_leaves_receipt_unknown_and_fences_the_resource(local_store):
    connection, _ = local_store
    page_id = fixture_action({'action': 'create_page', 'owned': True})['id']
    reader = WordPressReader(connection)
    before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='update_owned_page',
                                resource_key=f'page:{page_id}', expected_fingerprint=before.resource_fingerprints[f'page:{page_id}'],
                                payload={'page_id': page_id, 'title': 'Crash probe', 'content': 'Unknown outcome'})
    response = await signed_operation(local_store, operation, headers={'X-MUSE-TEST-FAULT': 'exit-after-page'})
    assert not response.content  # An empty HTTP success must never stand in for a receipt.
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password)) as client:
        lookup = await client.get(connection.base_url + '/wp-json/muse/v1/receipts/' + operation.operation_id)
    assert lookup.status_code == 200 and lookup.json()['state'] == 'NEEDS_RECONCILIATION'
    repeated = await signed_operation(local_store, operation)
    assert repeated.status_code == 200 and repeated.json() == lookup.json()
    next_operation = operation.model_copy(update={'operation_id': 'fixture-' + uuid.uuid4().hex})
    blocked = await signed_operation(local_store, next_operation)
    assert blocked.status_code == 409
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    assert next(page for page in after.pages if page['id'] == page_id)['content'] == 'Before'


@pytest.mark.asyncio
async def test_real_operation_identity_cannot_be_reused_with_a_new_payload(local_store):
    connection, _ = local_store
    page_id = fixture_action({'action': 'create_page', 'owned': True})['id']
    before = normalize_snapshot(await WordPressReader(connection).read('snapshot', remaining_seconds=20), 'project', 'staging')
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='update_owned_page',
                                resource_key=f'page:{page_id}', expected_fingerprint=before.resource_fingerprints[f'page:{page_id}'],
                                payload={'page_id': page_id, 'title': 'Accepted', 'content': 'Accepted'})
    assert (await signed_operation(local_store, operation)).json()['state'] == 'SUCCEEDED'
    changed = operation.model_copy(update={'payload': dict(operation.payload, title='Rejected')})
    response = await signed_operation(local_store, changed)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_real_owned_page_creation_has_explicit_absence_proof_and_no_duplicate(local_store):
    connection, _ = local_store
    slug = 'muse-fixture-' + uuid.uuid4().hex
    proof = await WordPressReader(connection).read_page_slug(slug, remaining_seconds=20)
    assert proof['state'] == {'slug': slug, 'exists': False}
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='create_owned_page',
                                resource_key=proof['resource_key'], expected_fingerprint=proof['fingerprint'],
                                payload={'slug': slug, 'title': 'Merchant Cart', 'content': '', 'template': 'page-cart'})
    response = await signed_operation(local_store, operation)
    assert response.status_code == 200 and response.json()['state'] == 'SUCCEEDED', response.text
    repeated = await signed_operation(local_store, operation)
    assert repeated.status_code == 200 and repeated.json() == response.json()
    after = await WordPressReader(connection).read_page_slug(slug, remaining_seconds=20)
    assert after['state']['exists'] is True and type(after['state']['page_id']) is int
    snapshot = normalize_snapshot(await WordPressReader(connection).read('snapshot', remaining_seconds=20), 'project', 'staging')
    page = next(page for page in snapshot.pages if page['slug'] == slug)
    assert page['status'] == 'draft' and page['muse_project_id'] == 'project' and page['title'] == 'Merchant Cart'
    another = operation.model_copy(update={'operation_id': 'fixture-' + uuid.uuid4().hex})
    collision = await signed_operation(local_store, another)
    assert collision.status_code == 200 and collision.json()['state'] == 'FAILED'


@pytest.mark.asyncio
async def test_created_page_proof_binds_content_for_later_symbolic_operations(local_store):
    from muse.commerce.release_resources import resolve_created_resource
    from muse.commerce_connector.operation_ledger import OperationRecord
    connection, _ = local_store
    reader = WordPressReader(connection)
    slug = 'proof-' + uuid.uuid4().hex[:16]
    absence = await reader.read_page_slug(slug, remaining_seconds=20)
    operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='create_owned_page',
        resource_key=absence['resource_key'], expected_fingerprint=absence['fingerprint'],
        payload={'slug': slug, 'title': 'Approved', 'content': 'Approved', 'template': 'page'})
    response = await signed_operation(local_store, operation)
    assert response.json()['state'] == 'SUCCEEDED'
    created = await reader.read_page_slug(slug, remaining_seconds=20)
    assert created['fingerprint'] == response.json()['fingerprint']
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    receipt = OperationRecord.model_validate(response.json())
    bound = resolve_created_resource(connection, operation, receipt, created, snapshot)
    assert bound.entity_id == created['state']['page_id']
    fixture_action({'action': 'edit_page', 'id': created['state']['page_id'], 'content': 'Manual edit'})
    edited = await reader.read_page_slug(slug, remaining_seconds=20)
    assert edited['fingerprint'] != created['fingerprint']
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    assert edited['state']['entity_fingerprint'] == snapshot.resource_fingerprints[f"page:{created['state']['page_id']}"]
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        resolve_created_resource(connection, operation, receipt, edited, snapshot)


@pytest.mark.asyncio
async def test_disposable_station_renders_cart_checkout_and_accepts_offline_test_order(local_store, monkeypatch):
    from playwright.async_api import async_playwright
    connection, _ = local_store
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers'))
    fixture_action({'action': 'offline_checkout'})
    reader = WordPressReader(connection)
    pages = {}
    for kind in ['home', 'shop', 'cart', 'checkout', 'about', 'contact']:
        slug = 'probe-' + kind + '-' + uuid.uuid4().hex[:12]
        proof = await reader.read_page_slug(slug, remaining_seconds=20)
        template = 'page-' + kind if kind in {'cart', 'checkout', 'about', 'contact'} else 'page'
        create = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='create_owned_page',
            resource_key=proof['resource_key'], expected_fingerprint=proof['fingerprint'],
            payload={'slug': slug, 'title': kind.title(), 'content': 'Merchant supplied ' + kind, 'template': template})
        assert (await signed_operation(local_store, create)).json()['state'] == 'SUCCEEDED'
        created = await reader.read_page_slug(slug, remaining_seconds=20)
        page_id = created['state']['page_id']
        snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        publish = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='publish_owned_page',
            resource_key=f'page:{page_id}', expected_fingerprint=snapshot.resource_fingerprints[f'page:{page_id}'], payload={'page_id': page_id})
        assert (await signed_operation(local_store, publish)).json()['state'] == 'SUCCEEDED'
        pages[kind] = page_id
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    options = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='set_storefront_options', resource_key='settings',
        expected_fingerprint=snapshot.resource_fingerprints['settings'], payload={kind + '_page_id': pages[kind] for kind in ['home', 'shop', 'cart', 'checkout']})
    dependencies = {f'page:{pages[kind]}': snapshot.resource_fingerprints[f'page:{pages[kind]}']
                    for kind in ['home', 'shop', 'cart', 'checkout']}
    assert (await signed_operation(local_store, options, dependencies)).json()['state'] == 'SUCCEEDED'
    sku = 'BUYER-' + uuid.uuid4().hex
    proof = await reader.read_sku(sku, remaining_seconds=20)
    create = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='create_product_draft',
        resource_key=proof['resource_key'], expected_fingerprint=proof['fingerprint'], payload={'product': {
            'sku': sku, 'title': 'Disposable buyer cup', 'price': '19.99', 'currency': 'USD', 'stock': 5,
            'description': 'Test fixture only', 'category': '', 'source_facts': {}, 'media_refs': []}})
    assert (await signed_operation(local_store, create)).json()['state'] == 'SUCCEEDED'
    created = await reader.read_sku(sku, remaining_seconds=20)
    product_id = created['state']['product_id']
    publish = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='publish_product',
        resource_key=f'product:{product_id}', expected_fingerprint=created['state']['entity_fingerprint'], payload={'product_id': product_id})
    assert (await signed_operation(local_store, publish)).json()['state'] == 'SUCCEEDED'
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={'width': 390, 'height': 900})
        page = await context.new_page()
        try:
            await page.goto(connection.base_url + '/?page_id=' + str(pages['cart']))
            await page.locator('.wp-block-woocommerce-cart').wait_for(timeout=15000)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            buyer = context.request
            cart = await buyer.get(connection.base_url + '/wp-json/wc/store/v1/cart')
            assert cart.status == 200
            nonce = cart.headers['nonce']
            added = await buyer.post(connection.base_url + '/wp-json/wc/store/v1/cart/add-item',
                                     headers={'Nonce': nonce}, data={'id': product_id, 'quantity': 1})
            assert added.status == 201, await added.text()
            await page.goto(connection.base_url + '/?page_id=' + str(pages['checkout']))
            await page.locator('.wp-block-woocommerce-checkout').wait_for(timeout=15000)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            address = {'first_name': 'Disposable', 'last_name': 'Buyer', 'address_1': '1 Fixture Street', 'address_2': '',
                       'city': 'Beverly Hills', 'state': 'CA', 'postcode': '90210', 'country': 'US'}
            order = await buyer.post(connection.base_url + '/wp-json/wc/store/v1/checkout',
                headers={'Nonce': added.headers.get('nonce', nonce)}, data={'billing_address': dict(address, email='buyer@example.invalid', phone='5555550100'),
                    'shipping_address': address, 'payment_method': 'cod', 'payment_data': [], 'customer_note': 'Disposable test only'})
            assert order.status == 200, await order.text()
            assert (await order.json())['order_id'] > 0
        finally:
            await context.close(); await browser.close()


@pytest.mark.asyncio
async def test_real_wordpress_requires_authentication(local_store):
    connection, _ = local_store
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.get(connection.base_url + '/wp-json/muse/v1/snapshot')
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_service_identity_cannot_bypass_muse_through_native_cms_writes(local_store):
    connection, _ = local_store
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password)) as client:
        context = await client.get(connection.base_url + '/wp-json/muse/v1/snapshot')
        assert context.status_code == 200
        write = await client.post(connection.base_url + '/wp-json/wp/v2/pages',
                                  json={'title': 'Forbidden native write', 'status': 'draft'})
        assert write.status_code == 403, write.text
        users = await client.get(connection.base_url + '/wp-json/wp/v2/users?context=edit')
        assert users.status_code == 403, users.text


@pytest.mark.asyncio
async def test_real_wordpress_versions_and_normalized_snapshot(local_store):
    connection, _ = local_store
    reader = WordPressReader(connection)
    capabilities = await reader.read('capabilities', remaining_seconds=20)
    assert capabilities['wordpress_version'] == '7.1.2'
    assert capabilities['woocommerce_version'] == '11.1.2'
    assert capabilities['theme_id'] == 'muse-storefront'
    raw = await reader.read('snapshot', remaining_seconds=20)
    snapshot = normalize_snapshot(raw, 'project', 'staging')
    assert snapshot.theme_identity['effective_templates']
    assert set(snapshot.resource_fingerprints) >= {'settings', 'theme'}
    assert 'orders' not in raw and 'customers' not in raw


@pytest.mark.asyncio
async def test_real_staging_fact_checker_matches_installed_source_pages_products_and_navigation(local_store, tmp_path, monkeypatch):
    from muse.commerce.coding import SourceStore
    from muse.commerce.models import CommercePlan, ProductDraft, SiteBrief
    from muse.commerce.preview import capture_staging_preview
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.theme import render_site_files
    from muse.commerce.verification import verify_staging_facts
    from tests.muse.commerce.test_coding_artifact import archive as source_tar
    connection, _ = local_store
    reader = WordPressReader(connection)
    fixture_action({'action': 'offline_checkout'})
    old = fixture_action({'action': 'store_setup', 'confirmed': True})['old']
    try:
        before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        blueprint = build_site_blueprint(SiteBrief(brand_name='Disposable verification', currency='USD', language='en-US'), before)
        suffix = uuid.uuid4().hex[:10]
        renamed = {}
        for page in blueprint.pages:
            renamed[page.slug] = 'check-' + page.kind + '-' + suffix
            page.slug = renamed[page.slug]
        for item in blueprint.navigation:
            item.slug = renamed[item.slug]
        product = ProductDraft(sku='CHECK-' + suffix, title='Verifier cup', price='12.30', currency='USD', stock=3)
        content_hash = digest({'blueprint': blueprint.model_dump(mode='json'), 'products': [product.model_dump(mode='json')]})
        code = SourceStore(tmp_path / 'trusted-code').seal(source_tar(render_site_files(blueprint, [product])),
            project_id='project', plan_id='verify-' + suffix, snapshot_hash=digest(before), content_hash=content_hash)
        plan = CommercePlan(id=code.plan_id, project_id='project', kind='launch_products', state='VERIFYING', blueprint=blueprint,
                            products=[product], snapshot_hash=digest(before), content_hash=content_hash, code_revision=code.package.code_revision)
        async def snap():
            return normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        install = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='install_theme_package',
            resource_key='theme:muse-storefront', expected_fingerprint=before.resource_fingerprints['theme'],
            payload={'package': code.package.model_dump(mode='json'), 'archive_base64': base64.b64encode(code.archive).decode()})
        assert (await signed_operation(local_store, install)).json()['state'] == 'SUCCEEDED'
        pages = {}
        for page in blueprint.pages:
            if page.kind == 'product':
                continue
            proof = await reader.read_page_slug(page.slug, remaining_seconds=20)
            create = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='create_owned_page',
                resource_key=proof['resource_key'], expected_fingerprint=proof['fingerprint'], payload={
                    'slug': page.slug, 'title': page.title, 'content': '',
                    'template': 'page-' + page.kind if page.kind in {'cart', 'checkout', 'about', 'contact'} else 'page'})
            assert (await signed_operation(local_store, create)).json()['state'] == 'SUCCEEDED'
            proof = await reader.read_page_slug(page.slug, remaining_seconds=20)
            identity = proof['state']['page_id']; pages[page.kind] = identity
            publish = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='publish_owned_page',
                resource_key='page:' + str(identity), expected_fingerprint=proof['state']['entity_fingerprint'], payload={'page_id': identity})
            assert (await signed_operation(local_store, publish)).json()['state'] == 'SUCCEEDED'
        current = await snap()
        options = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='set_storefront_options', resource_key='settings',
            expected_fingerprint=current.resource_fingerprints['settings'], payload={kind + '_page_id': pages[kind]
                for kind in ['home', 'shop', 'cart', 'checkout']})
        dependencies = {'page:' + str(pages[kind]): current.resource_fingerprints['page:' + str(pages[kind])]
                        for kind in ['home', 'shop', 'cart', 'checkout']}
        assert (await signed_operation(local_store, options, dependencies)).json()['state'] == 'SUCCEEDED'
        proof = await reader.read_sku(product.sku, remaining_seconds=20)
        create = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='create_product_draft', resource_key=proof['resource_key'],
            expected_fingerprint=proof['fingerprint'], payload={'product': product.model_dump(mode='json')})
        assert (await signed_operation(local_store, create)).json()['state'] == 'SUCCEEDED'
        proof = await reader.read_sku(product.sku, remaining_seconds=20)
        identity = proof['state']['product_id']
        publish = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='publish_product', resource_key='product:' + str(identity),
            expected_fingerprint=proof['state']['entity_fingerprint'], payload={'product_id': identity})
        assert (await signed_operation(local_store, publish)).json()['state'] == 'SUCCEEDED'
        current = await snap()
        by_slug = {p.slug: pages[p.kind] for p in blueprint.pages if p.kind != 'product'}
        operation = ChangeOperation(operation_id='fixture-' + uuid.uuid4().hex, kind='set_owned_navigation', resource_key='navigation:muse-storefront',
            expected_fingerprint=current.resource_fingerprints['navigation:muse-storefront'],
            payload={'items': [{'page_id': by_slug[item.slug], 'label': item.label} for item in blueprint.navigation]})
        dependencies = {'theme:muse-storefront': current.resource_fingerprints['theme'],
                        **{'page:' + str(identity): current.resource_fingerprints['page:' + str(identity)] for identity in by_slug.values()}}
        assert (await signed_operation(local_store, operation, dependencies)).json()['state'] == 'SUCCEEDED'
        result = verify_staging_facts(plan, code, await snap(), connection=connection)
        assert result['passed'] is True and result['site_verified'] is False
        assert result['product_ids'][product.sku] == identity
        monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(Path.cwd() / 'work/browsers'))
        capture = await capture_staging_preview(plan, code, await snap(), connection)
        for frame in capture.frames:
            (tmp_path / (frame.kind + '-' + str(frame.width) + '.png')).write_bytes(frame.content)
        assert capture.passed, (capture.checks, capture.diagnostics)
        assert capture.site_verified is False and len(capture.frames) == 21
    finally:
        fixture_action({'action': 'store_setup', 'restore': old})


def test_real_wordpress_navigation_materializer_preserves_header_code_and_rejects_ambiguous_navigation(local_store):
    raw = ('<!-- wp:group {"layout":{"type":"flex"}} --><div class="wp-block-group">'
           '<!-- wp:paragraph --><p>Merchant approved welcome</p><!-- /wp:paragraph -->'
           '<!-- wp:navigation {"overlayMenu":"never","className":"merchant-menu"} -->'
           '<!-- wp:navigation-link {"label":"Old","url":"/old/"} /--><!-- /wp:navigation -->'
           '</div><!-- /wp:group -->')
    value = fixture_action({'action': 'materialize_header', 'content': raw, 'navigation_id': 301})['content']
    assert 'Merchant approved welcome' in value and 'merchant-menu' in value
    assert '"overlayMenu":"never"' in value and '"ref":301' in value and '/old/' not in value
    for ambiguous in ('<!-- wp:paragraph --><p>No navigation</p><!-- /wp:paragraph -->',
                      raw + '<!-- wp:navigation /-->'):
        with pytest.raises(AssertionError, match='Exactly one header navigation'):
            fixture_action({'action': 'materialize_header', 'content': ambiguous, 'navigation_id': 301})


@pytest.mark.asyncio
async def test_real_installed_theme_effect_projects_only_source_bound_next_page(local_store, tmp_path):
    from muse.commerce.coding import SourceStore
    from muse.commerce.models import (
        CommercePlan,
        EnvironmentRef,
        SiteBrief,
        StoreProject,
    )
    from muse.commerce.repository import digest
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.site_release import prepare_site_release
    from muse.commerce.site_steps import (
        CompletedSiteStep,
        project_site_step,
        validate_site_completion,
    )
    from muse.commerce.theme import render_site_files
    from muse.commerce_connector.operation_ledger import OperationRecord
    from tests.muse.commerce.test_coding_artifact import archive
    connection, _ = local_store
    reader = WordPressReader(connection)
    before = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    brief = SiteBrief(brand_name='Website projection probe', language=before.settings['language'], currency=before.settings['currency'])
    target = EnvironmentRef(id='stage', project_id='project', environment='staging', connector_ref=connection.connection_id,
                            public_url=connection.base_url)
    project = StoreProject(id='project', workspace_id='fixture', brief=brief, environment_refs=[target])
    blueprint = build_site_blueprint(brief, before)
    suffix = '-' + uuid.uuid4().hex[:10]
    for page in blueprint.pages:
        if page.kind != 'product': page.slug += suffix
    for item in blueprint.navigation: item.slug += suffix
    plan = CommercePlan(id='plan-' + uuid.uuid4().hex, project_id='project', kind='build_site', state='VERIFYING',
        blueprint=blueprint, products=[], snapshot_hash=digest(before),
        content_hash=digest({'blueprint': blueprint.model_dump(mode='json'), 'products': []}))
    code = SourceStore(tmp_path / 'source').seal(archive(render_site_files(blueprint, [])), project_id='project',
        plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    proofs = {}
    for page in blueprint.pages:
        if page.kind != 'product':
            proof = await reader.read_page_slug(page.slug, remaining_seconds=20)
            proofs[proof['resource_key']] = proof
    intent = prepare_site_release(project, plan, target, before, code, proofs, connection=connection)
    first = project_site_step(intent, connection, code, 0, [], before, proofs)
    # Functional probe uses the existing test-only v1 authority; this is not a
    # v3 merchant approval or complete website publication test.
    response = await signed_operation(local_store, first.operation)
    assert response.json()['state'] == 'SUCCEEDED'
    after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    done = CompletedSiteStep(first.operation, OperationRecord.model_validate(response.json()), after, {})
    second = project_site_step(intent, connection, code, 1, [done], after, proofs)
    assert second.operation.kind == 'create_owned_page'
    assert second.operation.payload['slug'] == blueprint.pages[0].slug
    assert second.preconditions['theme:muse-storefront'] == after.resource_fingerprints['theme']
    from muse.commerce_connector.site_authorization import (
        SiteReleaseAuthority,
        SiteReleaseGrant,
    )
    private = local_store[1]
    now = time.time()
    # Explicit test grant is not persisted merchant approval or Linux evidence.
    grant = SiteReleaseGrant('fixture-site-grant', intent.digest, intent.project_id, connection.connection_id,
        connection.environment, connection.base_url, 'e' * 64, now, now + 600, 'approved')
    authority = SiteReleaseAuthority(private['signing_secret'].encode())
    history = [done]
    for index in range(1, len(intent.steps)):
        for page in blueprint.pages:
            if page.kind != 'product':
                proof = await reader.read_page_slug(page.slug, remaining_seconds=20)
                proofs[proof['resource_key']] = proof
        projected = project_site_step(intent, connection, code, index, history, after, proofs)
        token = authority.issue(grant, intent, connection, code, index, history, after, proofs)
        async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password), timeout=30) as client:
            result = await client.post(connection.base_url + '/wp-json/muse/v1/operations',
                json={'operation': projected.operation.model_dump(mode='json'), 'execution_authorization': token})
        assert result.status_code == 200 and result.json()['state'] == 'SUCCEEDED'
        after = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
        proof = await reader.read_page_slug(projected.operation.payload['slug'], remaining_seconds=20) if projected.operation.kind == 'create_owned_page' else {}
        history.append(CompletedSiteStep(projected.operation, OperationRecord.model_validate(result.json()), after, proof))
    for page in blueprint.pages:
        if page.kind != 'product':
            proof = await reader.read_page_slug(page.slug, remaining_seconds=20)
            proofs[proof['resource_key']] = proof
    final = validate_site_completion(intent, connection, code, history, after, proofs)
    assert final['navigation:muse-storefront'] == after.resource_fingerprints['navigation:muse-storefront']


def media_operation(content, width, height, proof):
    sha = hashlib.sha256(content).hexdigest()
    return ChangeOperation(operation_id='media-' + uuid.uuid4().hex, kind='create_owned_media',
        resource_key='media-sha256:' + sha, expected_fingerprint=proof['fingerprint'], payload={
            'media_ref': digest(['project', 'image', sha]), 'image': {'sha256': sha, 'mime_type': 'image/png',
                'byte_size': len(content), 'width': width, 'height': height}, 'content_base64': base64.b64encode(content).decode()})


def disposable_image():
    import io

    from PIL import Image
    output = io.BytesIO()
    Image.frombytes('RGB', (12, 12), os.urandom(12 * 12 * 3)).save(output, format='PNG')
    return output.getvalue()


@pytest.mark.asyncio
async def test_real_media_upload_binds_owned_image_and_repeats_exact_receipt(local_store):
    connection, _ = local_store
    content = disposable_image()
    sha = hashlib.sha256(content).hexdigest()
    reader = WordPressReader(connection)
    proof = await reader.read_media_sha256(sha, remaining_seconds=20)
    assert proof['state'] == {'sha256': sha, 'exists': False}
    operation = media_operation(content, 12, 12, proof)
    first = await signed_operation(local_store, operation)
    assert first.status_code == 200 and first.json()['state'] == 'SUCCEEDED'
    uploaded = await reader.read_media_sha256(sha, remaining_seconds=20)
    assert uploaded['fingerprint'] == first.json()['fingerprint']
    attachment = uploaded['state']['attachment']
    assert attachment['muse_project_id'] == 'project' and attachment['width'] == 12 and attachment['height'] == 12
    assert attachment['mime_type'] == 'image/png' and attachment['byte_size'] == len(content)
    assert attachment['media_ref'] == operation.payload['media_ref']
    second = await signed_operation(local_store, operation)
    assert second.json() == first.json()
    async with httpx.AsyncClient(trust_env=False) as client:
        image = await client.get(connection.base_url + '/wp-content/uploads/muse-owned/project/' + sha + '.png')
    assert image.status_code == 200 and image.content == content
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password)) as client:
        native = await client.post(connection.base_url + '/wp-json/wp/v2/media', content=content,
            headers={'Content-Type': 'image/png', 'Content-Disposition': 'attachment; filename="bypass.png"'})
    assert native.status_code == 403


@pytest.mark.asyncio
async def test_real_media_file_crash_stays_unknown_and_never_overwrites_or_resends(local_store):
    connection, _ = local_store
    content = disposable_image()
    sha = hashlib.sha256(content).hexdigest()
    reader = WordPressReader(connection)
    proof = await reader.read_media_sha256(sha, remaining_seconds=20)
    operation = media_operation(content, 12, 12, proof)
    first = await signed_operation(local_store, operation, headers={'X-MUSE-Test-Fault': 'exit-after-media'})
    assert first.content == b''
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password)) as client:
        receipt = await client.get(connection.base_url + '/wp-json/muse/v1/receipts/' + operation.operation_id)
    assert receipt.json()['state'] == 'NEEDS_RECONCILIATION'
    repeated = await signed_operation(local_store, operation)
    assert repeated.json() == receipt.json()
    other = operation.model_copy(update={'operation_id': 'media-' + uuid.uuid4().hex})
    blocked = await signed_operation(local_store, other)
    assert blocked.status_code == 409
    assert (await reader.read_media_sha256(sha, remaining_seconds=20))['state']['exists'] is False
    async with httpx.AsyncClient(trust_env=False) as client:
        orphan = await client.get(connection.base_url + '/wp-content/uploads/muse-owned/project/' + sha + '.png')
    assert orphan.status_code == 200 and orphan.content == content  # Known nontransactional effect.


@pytest.mark.asyncio
async def test_real_product_images_use_exact_uploaded_primary_and_gallery(local_store):
    from muse.commerce_connector.media import resolve_created_media
    from muse.commerce_connector.operation_ledger import OperationRecord
    connection, _ = local_store
    reader = WordPressReader(connection)
    bindings, dependencies = [], {}
    for _index in range(2):
        content = disposable_image()
        proof = await reader.read_media_sha256(hashlib.sha256(content).hexdigest(), remaining_seconds=20)
        image_operation = media_operation(content, 12, 12, proof)
        response = await signed_operation(local_store, image_operation)
        assert response.json()['state'] == 'SUCCEEDED'
        proof = await reader.read_media_sha256(hashlib.sha256(content).hexdigest(), remaining_seconds=20)
        binding = resolve_created_media(connection, image_operation, OperationRecord.model_validate(response.json()), proof)
        bindings.append(binding.model_dump(mode='json'))
        dependencies[proof['resource_key']] = proof['fingerprint']
    sku = 'images-' + uuid.uuid4().hex
    proof = await reader.read_sku(sku, remaining_seconds=20)
    operation = ChangeOperation(operation_id='images-' + uuid.uuid4().hex, kind='create_product_draft',
        resource_key=proof['resource_key'], expected_fingerprint=proof['fingerprint'], payload={
            'product': {'sku': sku, 'title': 'Fixture gallery product', 'price': '12.30', 'currency': 'USD',
                'stock': 4, 'description': '', 'category': '', 'source_facts': {},
                'media_refs': [item['media_ref'] for item in bindings]}, 'media_bindings': bindings})
    result = await signed_operation(local_store, operation, dependencies)
    assert result.status_code == 200 and result.json()['state'] == 'SUCCEEDED'
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    product = next(item for item in snapshot.products if item['sku'] == sku)
    assert product['image_id'] == bindings[0]['id'] and product['gallery_image_ids'] == [bindings[1]['id']]
    repeated = await signed_operation(local_store, operation, dependencies)
    assert repeated.json() == result.json()
    # A fresh operation without signed image versions cannot copy arbitrary IDs.
    replacement = operation.model_copy(deep=True)
    replacement.operation_id = 'unbound-' + uuid.uuid4().hex
    replacement.payload['product']['sku'] = 'unbound-' + uuid.uuid4().hex
    absent = await reader.read_sku(replacement.payload['product']['sku'], remaining_seconds=20)
    replacement.resource_key, replacement.expected_fingerprint = absent['resource_key'], absent['fingerprint']
    denied = await signed_operation(local_store, replacement)
    assert denied.json()['state'] == 'FAILED'


@pytest.mark.asyncio
@pytest.mark.parametrize('permit_version', [4, 5])
async def test_real_v4_launch_binds_image_source_and_all_four_step_receipts(local_store, tmp_path, permit_version):
    from muse.commerce.coding import SourceStore
    from muse.commerce.merchant_release import prepare_merchant_release
    from muse.commerce.merchant_steps import (
        project_merchant_step,
        validate_merchant_completion,
    )
    from muse.commerce.models import (
        CommercePlan,
        EnvironmentRef,
        ProductDraft,
        SiteBrief,
        StoreProject,
    )
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.site_steps import CompletedSiteStep
    from muse.commerce.theme import render_site_files
    from muse.commerce_connector.media import MediaPayload
    from muse.commerce_connector.merchant_authorization import (
        MerchantReleaseAuthority,
        MerchantReleaseGrant,
    )
    from muse.commerce_connector.operation_ledger import OperationRecord
    from muse.commerce_connector.staging_authorization import (
        StagingReleaseAuthority,
        StagingReleaseGrant,
    )
    from tests.muse.commerce.test_coding_artifact import archive
    connection, private = local_store
    reader = WordPressReader(connection)
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
    brief = SiteBrief(brand_name='Fixture', language='en-US', currency=snapshot.settings['currency'])
    target = EnvironmentRef(id='staging', project_id='project', environment='staging', connector_ref='connection', public_url=connection.base_url)
    project = StoreProject(id='project', workspace_id='fixture', brief=brief, environment_refs=[target])
    content = disposable_image(); sha = hashlib.sha256(content).hexdigest()
    proof = await reader.read_media_sha256(sha, remaining_seconds=20)
    image = MediaPayload.model_validate(media_operation(content, 12, 12, proof).payload)
    product = ProductDraft(sku='v4-' + uuid.uuid4().hex, title='Source bound image product', price='13.20',
        currency=brief.currency, stock=5, media_refs=[image.media_ref])
    blueprint = build_site_blueprint(brief, snapshot)
    plan = CommercePlan(id='v4-plan', project_id='project', kind='launch_products', state='VERIFYING',
        blueprint=blueprint, products=[product], snapshot_hash=digest(snapshot), content_hash=digest({
            'blueprint': blueprint.model_dump(mode='json'), 'products': [product.model_dump(mode='json')]}))
    code = SourceStore(tmp_path / 'source').seal(archive(render_site_files(blueprint, [product])), project_id='project',
        plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
    plan.code_revision = code.package.code_revision
    sku_proof = await reader.read_sku(product.sku, remaining_seconds=20)
    proofs = {proof['resource_key']: proof, sku_proof['resource_key']: sku_proof}
    intent = prepare_merchant_release(project, plan, target, snapshot, code, proofs, [image], connection=connection)
    now = time.time()
    # This functional fixture grant is not persisted merchant approval/Linux evidence.
    grant_type = StagingReleaseGrant if permit_version == 5 else MerchantReleaseGrant
    authority_type = StagingReleaseAuthority if permit_version == 5 else MerchantReleaseAuthority
    grant = grant_type('fixture-v' + str(permit_version), intent.digest, 'project', 'connection', 'staging', connection.base_url,
        'e' * 64, now, now + 600, 'approved')
    authority = authority_type(private['signing_secret'].encode())
    history = []
    async with httpx.AsyncClient(trust_env=False, auth=(connection.username, connection.application_password), timeout=30) as client:
        for index in range(len(intent.steps)):
            projected = project_merchant_step(intent, connection, code, index, history, snapshot, proofs)
            token = authority.issue(grant, intent, connection, code, index, history, snapshot, proofs)
            response = await client.post(connection.base_url + '/wp-json/muse/v1/operations', json={
                'operation': projected.operation.model_dump(mode='json'), 'execution_authorization': token})
            assert response.status_code == 200 and response.json()['state'] == 'SUCCEEDED'
            snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), 'project', 'staging')
            image_proof = await reader.read_media_sha256(sha, remaining_seconds=20)
            sku_proof = await reader.read_sku(product.sku, remaining_seconds=20)
            proofs = {image_proof['resource_key']: image_proof, sku_proof['resource_key']: sku_proof}
            current_proof = proofs.get(projected.operation.resource_key, {})
            history.append(CompletedSiteStep(projected.operation, OperationRecord.model_validate(response.json()), snapshot, current_proof))
    versions = validate_merchant_completion(intent, connection, code, history, snapshot, proofs)
    created = next(item for item in snapshot.products if item['sku'] == product.sku)
    assert created['status'] == 'publish' and created['image_id'] == image_proof['state']['attachment']['id']
    assert versions[image_proof['resource_key']] == image_proof['fingerprint']
