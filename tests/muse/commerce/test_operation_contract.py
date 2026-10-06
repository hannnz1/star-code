import base64
import hashlib

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation, SiteBrief, StoreSnapshot
from muse.commerce.site import build_site_blueprint
from muse.commerce.theme import build_site_archive
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.commerce_connector.operations import operation_digest, validate_operation


def operation(kind):
    resource, payload = {
        'update_owned_page': ('page:12', {'page_id': 12, 'title': 'About', 'content': 'Text'}),
        'publish_owned_page': ('page:12', {'page_id': 12}),
        'publish_product': ('product:22', {'product_id': 22}),
        'set_owned_navigation': ('navigation:muse-storefront', {'items': [{'page_id': 12, 'label': 'Home'}]}),
        'set_storefront_options': ('settings', {'home_page_id': 12, 'shop_page_id': 13, 'cart_page_id': 14, 'checkout_page_id': 15}),
        'create_product_draft': ('sku:' + hashlib.sha256(b'sku-1').hexdigest(),
                                 {'product': {'sku': 'SKU-1', 'title': 'Item', 'price': '12.30', 'currency': 'USD', 'stock': 3}}),
    }.get(kind, ('theme:muse-storefront', {}))
    if kind == 'install_theme_package':
        blueprint = build_site_blueprint(SiteBrief(brand_name='Shop', language='en', currency='USD'),
                                         StoreSnapshot(project_id='project', environment='staging'))
        metadata, archive = build_site_archive(blueprint, [], code_revision='a' * 40)
        payload = {'package': metadata.model_dump(mode='json'), 'archive_base64': base64.b64encode(archive).decode()}
    return ChangeOperation(operation_id='op-1', kind=kind, resource_key=resource, expected_fingerprint='a' * 64, payload=payload)


@pytest.mark.parametrize('kind', ['update_owned_page', 'publish_owned_page', 'publish_product', 'set_owned_navigation',
                                  'set_storefront_options', 'create_product_draft', 'install_theme_package'])
def test_each_fixed_contract_has_ledger_compatible_digest_and_rejects_extra_fields(tmp_path, kind):
    value = operation(kind)
    validated = validate_operation(value)
    assert OperationLedger(tmp_path / 'ledger.sqlite').prepare('project', 'connection', 'staging', validated).operation_digest == operation_digest(value)
    invalid = value.model_copy(update={'payload': dict(value.payload, arbitrary_command='rm everything')})
    with pytest.raises(CommerceFailure):
        validate_operation(invalid)


@pytest.mark.parametrize('field,value', [('price', 12.3), ('stock', True), ('price', 'NaN'),
                                        ('media_refs', ['arbitrary-path']), ('description', '<img src="https://evil.example">')])
def test_draft_rejects_unsafe_facts_or_unimplemented_media(field, value):
    candidate = operation('create_product_draft')
    candidate.payload['product'][field] = value
    with pytest.raises(CommerceFailure):
        validate_operation(candidate)


def test_tampered_package_is_rejected_before_any_write():
    candidate = operation('install_theme_package')
    candidate.payload['archive_base64'] = base64.b64encode(b'not-a-zip').decode()
    with pytest.raises(CommerceFailure):
        validate_operation(candidate)

@pytest.mark.parametrize('price', ['+12.30', '1_2.30', ' 12.30 ', '1e100000', '1234567890123', '1.1234567'])
def test_draft_wire_price_matches_import_precision_and_format(price):
    candidate = operation('create_product_draft')
    candidate.payload['product']['price'] = price
    with pytest.raises(CommerceFailure):
        validate_operation(candidate)


def test_draft_wire_stock_matches_wordpress_integer_bound():
    candidate = operation('create_product_draft')
    candidate.payload['product']['stock'] = 2147483648
    with pytest.raises(CommerceFailure):
        validate_operation(candidate)

@pytest.mark.parametrize('price,stock', [('999999999999.999999', 2147483647), ('0.000001', 0)])
def test_draft_accepts_import_numeric_boundaries_without_rounding(price, stock):
    candidate = operation('create_product_draft')
    candidate.payload['product'].update(price=price, stock=stock)
    result = validate_operation(candidate)
    assert result.payload['product']['price'] == price
    assert result.payload['product']['stock'] == stock
