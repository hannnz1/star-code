from muse.commerce.merchant_release import merchant_graph
from tests.muse.commerce.test_merchant_release import merchant_inputs,image_upload,site_release_inputs


def test_retained_preview_materializes_missing_taxonomy_with_private_hidden_seed(merchant_inputs):
    _,plan,_,_,code,_,images=merchant_inputs
    plan.products[0].category='New cups'
    plan.blueprint.required_settings.update(retain_existing_theme=True,
        category_navigation={'import_id':'original','items':[{'category':'Old cups','label':'Cups'}]})
    graph=merchant_graph('build_site',plan.blueprint,plan.products,code.package,images)
    seeds=[step.payload['product'] for step in graph if step.kind=='create_product_draft' and step.payload['product']['sku'].startswith('CREW-PREVIEW-CAT-')]
    assert len(seeds)==1 and seeds[0]['category']=='Old cups' and seeds[0]['stock']==0
    assert seeds[0]['source_facts']=={'crew_preview_seed':'category'}
    assert len(plan.products)==1 and plan.products[0].category=='New cups'
    launch=merchant_graph('launch_products',plan.blueprint,plan.products,code.package,images)
    assert not any(step.kind=='create_product_draft' and step.payload['product']['sku'].startswith('CREW-PREVIEW-CAT-') for step in launch)


def test_full_twenty_product_launch_keeps_private_preview_category_capacity(merchant_inputs):
    from muse.commerce.merchant_release import preview_category_products
    _,plan,_,_,code,_,images=merchant_inputs
    plan.blueprint.required_settings.update(retain_existing_theme=True,
        category_navigation={'import_id':'original','items':[{'category':'Old cups','label':'Cups'}]})
    products=[plan.products[0].model_copy(update={'sku':f'NEW-{i}','category':'New cups'}) for i in range(20)]
    assert len(preview_category_products('build_site',plan.blueprint,products))==1
    graph=merchant_graph('build_site',plan.blueprint,products,code.package,images)
    assert sum(step.kind=='create_product_draft' for step in graph)==21


def test_private_category_seed_requires_explicit_hidden_readback(merchant_inputs):
    import pytest
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.release_steps import _approved_product_facts
    _,plan,_,_,_,_,_=merchant_inputs
    product=plan.products[0].model_copy(update={'source_facts':{'crew_preview_seed':'category'}})
    entity={'sku':product.sku,'name':product.title,'price':product.price,
        'stock_quantity':product.stock,'description':product.description,
        'categories':[{'id':1,'name':product.category}],'category_ids':[1]}
    for visibility in [None,'visible']:
        candidate=dict(entity)
        if visibility is not None: candidate['catalog_visibility']=visibility
        with pytest.raises(CommerceFailure): _approved_product_facts(product,candidate)
    _approved_product_facts(product,{**entity,'catalog_visibility':'hidden'})
