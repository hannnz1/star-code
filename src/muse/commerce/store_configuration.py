"""Independent semantic checks for owned shipping and taxonomy navigation."""
from urllib.parse import urlsplit
from muse.commerce.shipping_rules import ShippingRules


def category_targets(blueprint, products):
    from muse.commerce.category_navigation import CategoryNavigation
    raw = blueprint.required_settings.get('category_navigation')
    if raw is None:
        return []
    items = CategoryNavigation.model_validate(raw).items
    # A retained launch never writes navigation. Its existing taxonomy links
    # are independently checked against the complete frozen/live snapshot.
    if not blueprint.required_settings.get('retain_existing_theme') and any(item.category not in {product.category for product in products} for item in items):
        raise ValueError('Category is absent from the approved build products')
    return items


def resolve_category(products, name, connection):
    matches = [category for product in products for category in product.get('categories', []) if category['name'] == name]
    if not matches or any(category != matches[0] for category in matches):
        raise ValueError('Category binding is missing or contradictory')
    result = matches[0]
    if set(result) != {'id','name','slug','url'} or type(result['id']) is not int or result['id'] <= 0:
        raise ValueError('Category permalink readback is required')
    url, base = urlsplit(result['url']), urlsplit(connection.base_url)
    if (url.scheme != base.scheme or url.netloc != base.netloc or url.fragment or url.username or url.password
        or not result['url'].startswith(connection.base_url+'/') or not result['slug']):
        raise ValueError('Foreign or invalid category permalink')
    return result


def shipping_effect(before, after, project_id, raw_rules):
    rules = ShippingRules.model_validate(raw_rules)
    if (not isinstance(before, dict) or not isinstance(after, dict)
        or set(after) != {'project_id','rules','zones','external_digest'}
        or before.get('project_id') != project_id or after['project_id'] != project_id
        or before.get('external_digest') != after['external_digest']
        or after['rules'] != rules.model_dump(mode='json') or len(after['zones']) != len(rules.zones)):
        raise ValueError('Shipping scope, merchant settings or approved rules changed')
    previous = {zone['key']:zone for zone in before.get('zones',[])}
    ids, instances = set(), set()
    for zone, source in zip(after['zones'], rules.zones, strict=True):
        if (set(zone) != {'key','id','name','countries','methods'} or zone['key'] != source.key
            or type(zone['id']) is not int or zone['id'] <= 0 or zone['id'] in ids
            or zone['name'] != source.name or zone['countries'] != source.countries
            or (source.key in previous and zone['id'] != previous[source.key]['id'])):
            raise ValueError('Owned shipping zone differs')
        ids.add(zone['id'])
        methods = [('flat_rate', {'title':'Shipping','tax_status':'none','cost':source.rate,'type':'class','no_class_cost':''})]
        if source.free_from is not None:
            methods.append(('free_shipping', {'title':'Free shipping','requires':'min_amount','min_amount':source.free_from,'ignore_discounts':'yes'}))
        if len(zone['methods']) != len(methods):
            raise ValueError('Unsigned shipping methods')
        existing_methods = {method['method_id']:method['instance_id'] for method in previous.get(source.key, {}).get('methods', [])}
        for method, (kind, settings) in zip(zone['methods'], methods, strict=True):
            if (set(method) != {'instance_id','method_id','enabled','settings'} or type(method['instance_id']) is not int
                or method['instance_id'] <= 0 or method['instance_id'] in instances or method['method_id'] != kind
                or method['enabled'] is not True or method['settings'] != settings
                or kind in existing_methods and method['instance_id'] != existing_methods[kind]):
                raise ValueError('Shipping method facts differ')
            instances.add(method['instance_id'])
    return after
