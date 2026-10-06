import base64, copy, hmac, json
import pytest
from muse.commerce.repository import digest
from tests.muse.commerce.test_php_protocol import php, run
from tests.muse.commerce.test_release_php import encoded


def wire(kind='set_owned_shipping', *, preview=False):
    shipping = kind == 'set_owned_shipping'
    index = 16 if shipping else 17
    operation = {'operation_id':'merchant-'+'a'*64+'-'+str(index), 'kind':kind,
        'resource_key':'shipping:muse-storefront' if shipping else 'navigation:muse-storefront',
        'expected_fingerprint':'b'*64, 'payload':{}}
    conditions = {key:'b'*64 for key in ['settings','theme:muse-storefront','navigation:muse-storefront','shipping:muse-storefront',
        *['page:'+str(i) for i in range(1,7)],'product:7','category:8']}
    claims = {'v':8 if preview else 7,'grant_id':'grant','project_id':'project','connection_id':'connection',
        'target_url':'https://shop.test','environment':'staging','audience':'muse-wp-store-preview-v8' if preview else 'muse-wp-store-step-v7',
        'changeset_digest':'a'*64,'verification_hash':'c'*64,'preconditions':conditions,'operation_digest':digest(operation),
        'issued_at':1000,'expires_at':2000,'step_index':index,'step_key':'set-shipping' if shipping else 'set-store-navigation',
        'identities':{},'workflow':'build_site','image_count':0,'product_count':1,'shipping_enabled':True,'category_count':1}
    if preview: claims['purpose']='staging-preview'
    return pack(operation,claims)


def pack(operation, claims):
    claims['operation_digest']=digest(operation)
    raw=json.dumps(claims,sort_keys=True,separators=(',',':')).encode()
    return {'mode':'verify_dispatch','operation':operation,'token':encoded(raw)+'.'+encoded(hmac.digest(b'x'*32,raw,'sha256')),
        'secret':base64.b64encode(b'x'*32).decode(),'now':1000,
        'scope':{key:claims[key] for key in ['project_id','connection_id','environment','target_url']}}


@pytest.mark.parametrize('kind', ['set_owned_shipping','set_owned_store_navigation'])
@pytest.mark.parametrize('preview', [False,True])
def test_store_protocol_accepts_separate_shipping_and_taxonomy_members(php,kind,preview):
    assert run(php,wire(kind,preview=preview))=={'accepted':True,'grant_id':'grant'}


@pytest.mark.parametrize('preview',[False,True])
def test_only_private_preview_keeps_capacity_for_twenty_products_and_ten_hidden_categories(php,preview):
    value=wire(preview=preview)
    claims=json.loads(base64.urlsafe_b64decode(value['token'].split('.')[0]+'=='))
    claims.update(product_count=30,step_index=73,step_key='publish-product-30')
    claims['preconditions'].update({'product:'+str(i):'b'*64 for i in range(7,37)})
    operation=value['operation'];operation.update(kind='publish_product',resource_key='product:36',operation_id='merchant-'+'a'*64+'-73')
    result=run(php,pack(operation,claims))
    assert result==({'accepted':True,'grant_id':'grant'} if preview else {'accepted':False})


@pytest.mark.parametrize('attack', ['old_version','wrong_index','wrong_key','flag','workflow','category_count','extra','missing_shipping','preview_live'])
def test_store_protocol_rejects_signed_invalid_graph(php,attack):
    value=wire(preview=attack=='preview_live')
    claims=json.loads(base64.urlsafe_b64decode(value['token'].split('.')[0]+'=='))
    if attack=='old_version': claims.update(v=4,audience='muse-wp-merchant-step-v4')
    elif attack=='wrong_index': claims['step_index']=15
    elif attack=='wrong_key': claims['step_key']='set-store-navigation'
    elif attack=='flag': claims['shipping_enabled']=1
    elif attack=='workflow': claims['workflow']='launch_products'
    elif attack=='category_count': claims['category_count']=11
    elif attack=='extra': claims['admin']=True
    elif attack=='missing_shipping': del claims['preconditions']['shipping:muse-storefront']
    else: claims['environment']='live'
    assert run(php,pack(value['operation'],claims))=={'accepted':False}
