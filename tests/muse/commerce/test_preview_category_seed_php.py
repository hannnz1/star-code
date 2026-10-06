import copy,hashlib
import pytest
from tests.muse.commerce.test_php_protocol import php,run


def fixture():
    return {'mode':'category_seed','claims':{'v':8,'environment':'staging','purpose':'staging-preview'},
        'product':{'sku':'CREW-PREVIEW-CAT-'+hashlib.sha256(b'Old cups').hexdigest()[:20],
            'title':'Crew preview category fixture','price':'0.00','stock':0,'category':'Old cups',
            'description':'','media_refs':[],'source_facts':{'crew_preview_seed':'category'}}}


def test_private_taxonomy_fixture_is_only_accepted_by_isolated_preview(php):
    assert run(php,fixture())=={'accepted':True}


@pytest.mark.parametrize('attack',['v1','v4','v5','v6','v7','live','purpose','sku','stock','price','title','facts','media'])
def test_seed_cannot_be_reused_as_a_merchant_product_write(php,attack):
    value=copy.deepcopy(fixture());p=value['product'];c=value['claims']
    if attack.startswith('v'): c['v']=int(attack[1:])
    elif attack=='live': c['environment']='live'
    elif attack=='purpose': c['purpose']='merchant'
    elif attack=='sku': p['sku']='REAL-SKU'
    elif attack=='stock': p['stock']=1
    elif attack=='price': p['price']='10.00'
    elif attack=='title': p['title']='Sale product'
    elif attack=='facts': p['source_facts']['extra']='x'
    else: p['media_refs']=['image']
    assert run(php,value)=={'accepted':False}
