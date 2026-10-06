from tests.muse.commerce.test_project_api import request
pytest_plugins = ['tests.muse.commerce.test_project_api']


def test_single_product_edit_creates_new_import_and_no_task(client):
    project=client.post('/api/commerce/projects',json=request(client)).json()
    path='/api/commerce/projects/'+project['id']
    body={'expected_project_revision':1,'client_request_id':'one','draft':{'sku':'PET-1','title':'Pet bowl','price':'19.95','currency':'USD','stock':4,'description':'Ceramic bowl','category':'Bowls'}}
    a=client.post(path+'/product-draft',json=body)
    assert a.status_code==201
    assert a.json()['result']['drafts'][0]['price']=='19.95'
    assert client.post(path+'/product-draft',json=body).json()['id']==a.json()['id']
    assert client.get('/api/tasks').json()==[]
    assert client.post(path+'/product-draft',json={**body,'client_request_id':'bad','draft':{**body['draft'],'currency':'AUD'}}).status_code==422
    body.update(client_request_id='edit',source_import_id=a.json()['id'])
    body['draft']['price']='25.00'
    b=client.post(path+'/product-draft',json=body)
    assert b.status_code==201
    assert b.json()['id']!=a.json()['id']
    assert client.get(path+'/product-imports').json()[0]['result']['drafts'][0]['price']=='19.95'
