import pytest
from pydantic import ValidationError

from muse.commerce.models import SiteBlueprint, SiteBrief, StoreSnapshot
from muse.commerce.site import build_site_blueprint


def brief(**updates):
    return SiteBrief(brand_name='Green Cups', language='zh-CN', currency='USD', **updates)


def test_seven_native_page_kinds_and_valid_navigation():
    result = build_site_blueprint(brief(), StoreSnapshot(project_id='p', environment='staging'))
    assert {page.kind for page in result.pages} == {'home', 'shop', 'product', 'cart', 'checkout', 'about', 'contact'}
    assert result.required_settings['missing_fields']
    assert result.required_settings['buyer_flow_verified'] is False
    assert result.required_settings['commerce_blocks'] == {'cart': 'woocommerce/cart', 'checkout': 'woocommerce/checkout'}
    slugs = {page.slug for page in result.pages}
    assert all(item.slug in slugs for item in result.navigation)
    assert result.pages[0].title == '首页'


def test_missing_policies_and_shipping_or_payment_are_never_invented():
    result = build_site_blueprint(brief(), StoreSnapshot(project_id='p', environment='staging'))
    assert 'merchant_supplied_policies.returns' in result.required_settings['missing_fields']
    assert 'shipping_confirmed' in result.required_settings['missing_fields']
    assert 'payment_confirmed' in result.required_settings['missing_fields']
    policies = {'shipping': 'Merchant supplied shipping policy', 'returns': 'Merchant supplied return policy', 'privacy': 'Merchant supplied privacy policy'}
    snapshot = StoreSnapshot(project_id='p', environment='staging', settings={'currency': 'USD', 'shipping_confirmed': True, 'payment_confirmed': True},
                             theme_identity={'stylesheet': 'muse-storefront'})
    ready = build_site_blueprint(brief(merchant_supplied_policies=policies), snapshot)
    assert ready.required_settings['missing_fields'] == []
    assert ready.required_settings['buyer_flow_verified'] is False


def test_duplicate_or_unknown_page_kinds_are_rejected():
    blueprint = build_site_blueprint(brief(), StoreSnapshot(project_id='p', environment='staging')).model_dump()
    blueprint['pages'][0]['kind'] = 'custom-payment'
    with pytest.raises(ValidationError):
        SiteBlueprint.model_validate(blueprint)
    blueprint = build_site_blueprint(brief(), StoreSnapshot(project_id='p', environment='staging')).model_dump()
    blueprint['pages'][1]['kind'] = 'home'
    with pytest.raises(ValidationError):
        SiteBlueprint.model_validate(blueprint)
