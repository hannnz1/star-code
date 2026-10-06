from copy import deepcopy

import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ProductDraft
from muse.commerce.release_steps import _approved_product_facts
from tests.muse.commerce.test_wordpress_context import raw


def approved():
    return ProductDraft(sku='SKU1', title='Cup', price='10.00', currency='USD', stock=4, category='Cups')


def entity():
    return {**raw()['products'][0], 'category_ids': [3], 'categories': [{'id': 3, 'name': 'Cups'}]}


@pytest.mark.parametrize('changes', [ {'categories': [{'id': 3, 'name': 'Other'}]},
    {'categories': []}, {'categories': [{'id': 4, 'name': 'Cups'}]},
    {'category_ids': [3, 4]}, {'categories': [{'id': 3, 'name': 'Cups'}, {'id': 3, 'name': 'Cups'}]} ])
def test_category_name_and_identity_are_both_approved_facts(changes):
    _approved_product_facts(approved(), entity())
    with pytest.raises(CommerceFailure):
        _approved_product_facts(approved(), {**entity(), **changes})


def test_category_rename_changes_snapshot_fingerprint_without_changing_id():
    value = raw()
    value['products'][0] = entity()
    before = normalize_snapshot(value, 'project', 'staging')
    changed = deepcopy(value)
    changed['products'][0]['categories'][0]['name'] = 'Other'
    after = normalize_snapshot(changed, 'project', 'staging')
    assert before.resource_fingerprints['product:2'] != after.resource_fingerprints['product:2']
    assert before.products[0]['categories'] == [{'id': 3, 'name': 'Cups'}]
