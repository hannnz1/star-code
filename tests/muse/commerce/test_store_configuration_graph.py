import pytest
from muse.commerce.merchant_release import merchant_graph
from tests.muse.commerce.test_merchant_release import merchant_inputs, image_upload, site_release_inputs
from tests.muse.commerce.test_shipping_rules import rules


def test_extended_build_places_category_navigation_after_product_creation(merchant_inputs):
    _, plan, _, _, code, _, images = merchant_inputs
    category = 'Pet toys'
    plan.products[0].category = category
    plan.blueprint.required_settings['category_navigation'] = {'import_id': 'batch', 'items': [{'category': category, 'label': 'Shop category'}]}
    plan.blueprint.required_settings['shipping_rules'] = rules()
    graph = merchant_graph('build_site', plan.blueprint, plan.products, code.package, images)
    assert graph[-1].kind == 'set_owned_store_navigation'
    assert graph[-2].kind == 'set_owned_shipping'
    assert graph[-1].payload['items'][-1] == {'category_name': category, 'label': 'Shop category'}
    assert graph[-3].kind == 'publish_product'
    assert all(graph[i].depends_on == [graph[i-1].key] for i in range(1, len(graph)))


def test_extended_build_rejects_missing_category_target(merchant_inputs):
    _, plan, _, _, code, _, images = merchant_inputs
    plan.blueprint.required_settings['category_navigation'] = {'import_id': 'batch', 'items': [{'category': 'Missing', 'label': 'Missing'}]}
    with pytest.raises(ValueError):
        merchant_graph('build_site', plan.blueprint, plan.products, code.package, images)


def test_product_launch_does_not_reapply_shipping_or_navigation(merchant_inputs):
    _, plan, _, _, code, _, images = merchant_inputs
    plan.blueprint.required_settings['shipping_rules'] = rules()
    graph = merchant_graph('launch_products', plan.blueprint, plan.products, code.package, images)
    assert not any(step.kind in {'set_owned_shipping', 'set_owned_store_navigation'} for step in graph)


def test_retained_launch_keeps_navigation_categories_from_existing_store(merchant_inputs):
    from muse.commerce.store_configuration import category_targets
    _, plan, _, _, _, _, _ = merchant_inputs
    plan.blueprint.required_settings.update(retain_existing_theme=True,
        category_navigation={'import_id':'original-batch','items':[{'category':'Existing cups','label':'Cups'}]})
    assert category_targets(plan.blueprint, plan.products)[0].category == 'Existing cups'


@pytest.mark.parametrize('setting',['shipping_rules','category_navigation'])
def test_legacy_site_authority_cannot_ignore_advanced_configuration(site_release_inputs, setting):
    from muse.commerce.site_release import validate_site_release, prepare_site_release, _hash
    from muse.commerce.errors import CommerceFailure
    intent=prepare_site_release(*site_release_inputs)
    intent.blueprint.required_settings[setting] = rules() if setting=='shipping_rules' else {'import_id':'batch','items':[]}
    intent.digest=_hash(intent)
    with pytest.raises(CommerceFailure): validate_site_release(intent)
