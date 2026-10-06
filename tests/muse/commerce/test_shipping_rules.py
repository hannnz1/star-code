from decimal import Decimal

import pytest
from pydantic import ValidationError


def rules(**updates):
    return {'currency': 'USD', 'zones': [{'key': 'au', 'name': 'Australia', 'countries': ['AU'],
            'rate': '6.00', 'free_from': '50.00'}], **updates}


def test_shipping_rules_exact_money_and_threshold():
    from muse.commerce.shipping_rules import ShippingRules
    value = ShippingRules.model_validate(rules())
    assert value.quote('AU', Decimal('49.99')) == Decimal('6.00')
    assert value.quote('AU', Decimal('50.00')) == Decimal('0.00')
    assert value.quote('AU', Decimal('50.01')) == Decimal('0.00')
    assert value.quote('US', Decimal('50.00')) is None
    assert value.model_dump(mode='json')['zones'][0]['rate'] == '6.00'


@pytest.mark.parametrize('change', [
    {'rate': '-1'}, {'rate': '1.001'}, {'rate': 'NaN'}, {'rate': 6.0},
    {'countries': ['AU', 'AU']}, {'countries': ['ZZ']}, {'countries': ['au']},
    {'name': '<script>'}, {'free_from': '-1'}, {'key': '../escape'},
])
def test_shipping_rules_reject_unsupported_values(change):
    from muse.commerce.shipping_rules import ShippingRules
    raw = rules()
    raw['zones'][0].update(change)
    with pytest.raises(ValidationError):
        ShippingRules.model_validate(raw)


def test_regions_cannot_overlap():
    from muse.commerce.shipping_rules import ShippingRules
    raw = rules()
    raw['zones'].append({**raw['zones'][0], 'key': 'other', 'name': 'Other'})
    with pytest.raises(ValidationError):
        ShippingRules.model_validate(raw)
