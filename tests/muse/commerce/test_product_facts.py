from muse.commerce.models import ProductDraft
from muse.commerce.products import review_product_content


def source():
    return ProductDraft(sku='CUP1', title='Cup', price='19.99', currency='USD', stock=5,
                        description='Ceramic cup.', source_facts={'material': 'ceramic', 'description': 'Ceramic cup.'})


def test_new_claims_require_merchant_confirmation():
    original = source()
    assert review_product_content(original, original) == []
    for update in [{'description': 'Certified therapeutic cup.'}, {'source_facts': {'material': 'organic bamboo'}},
                   {'title': 'Certified cup'}, {'price': '9.99'}, {'stock': 500}]:
        candidate = ProductDraft.model_validate({**original.model_dump(), **update})
        issues = review_product_content(original, candidate)
        assert issues and all(issue.code == 'FACTS_INCOMPLETE' for issue in issues)
