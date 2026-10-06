import copy
from types import SimpleNamespace
import pytest
from muse.commerce.store_configuration import shipping_effect, resolve_category
from tests.muse.commerce.test_shipping_rules import rules


def state():
    return {'project_id':'project','external_digest':'a'*64,'rules':rules(),'zones':[
        {'key':'au','id':1,'name':'Australia','countries':['AU'],'methods':[
            {'instance_id':1,'method_id':'flat_rate','enabled':True,'settings':
                {'title':'Shipping','tax_status':'none','cost':'6.00','type':'class','no_class_cost':''}},
            {'instance_id':2,'method_id':'free_shipping','enabled':True,'settings':
                {'title':'Free shipping','requires':'min_amount','min_amount':'50.00','ignore_discounts':'yes'}}]}]}


def test_owned_shipping_preserves_external_settings_and_existing_ids():
    before=state(); after=copy.deepcopy(before)
    assert shipping_effect(before,after,'project',rules())==after


@pytest.mark.parametrize('attack',['project','external','zone_id','rate','threshold','tax','disabled','extra_method','countries','method_id'])
def test_shipping_facts_reject_unsigned_remote_changes(attack):
    before=state(); after=copy.deepcopy(before); zone=after['zones'][0]
    if attack=='project': after['project_id']='foreign'
    elif attack=='external': after['external_digest']='b'*64
    elif attack=='zone_id': zone['id']=9
    elif attack=='rate': zone['methods'][0]['settings']['cost']='6+[qty]'
    elif attack=='threshold': zone['methods'][1]['settings']['min_amount']='49.99'
    elif attack=='tax': zone['methods'][0]['settings']['tax_status']='taxable'
    elif attack=='disabled': zone['methods'][0]['enabled']=False
    elif attack=='extra_method': zone['methods'].append(copy.deepcopy(zone['methods'][0]))
    elif attack=='countries': zone['countries']=['US']
    elif attack=='method_id': zone['methods'][0]['instance_id']=100
    with pytest.raises(ValueError): shipping_effect(before,after,'project',rules())


@pytest.mark.parametrize('url',['https://foreign.test/product-category/cups/','https://shop.test.evil/cups/','https://shop.test/cups/#section','https://user@shop.test/cups/'])
def test_category_permalink_cannot_escape_store(url):
    products=[{'categories':[{'id':1,'name':'Cups','slug':'cups','url':url}]}]
    with pytest.raises(ValueError): resolve_category(products,'Cups',SimpleNamespace(base_url='https://shop.test'))


def test_category_requires_platform_permalink_and_consistent_identity():
    category={'id':1,'name':'Cups','slug':'cups','url':'https://shop.test/product-category/cups/'}
    connection=SimpleNamespace(base_url='https://shop.test')
    assert resolve_category([{'categories':[category]}],'Cups',connection)==category
    with pytest.raises(ValueError): resolve_category([{'categories':[category,{**category,'id':2}]}],'Cups',connection)
    with pytest.raises(ValueError): resolve_category([{'categories':[{'id':1,'name':'Cups'}]}],'Cups',connection)
