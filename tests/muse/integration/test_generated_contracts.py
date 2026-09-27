from pathlib import Path
from test_api_contract import api


def test_public_openapi_contracts_and_generated_types_are_current(api):
    client, app = api
    schema = app.openapi()
    response = schema['paths']['/api/tasks']['get']['responses']['200']['content']['application/json']['schema']
    assert response.get('items', {}).get('$ref') == '#/components/schemas/TaskView'
    from muse.openapi_types import render_types
    generated = render_types(schema)
    assert 'WAITING_INPUT' in generated
    assert 'checkpoint' not in schema['components']['schemas']['TaskView']['properties']
    assert Path('frontend/src/api.generated.ts').read_text(encoding='utf-8') == generated
    ws = client.get('/api/workspaces').json()[0]
    response = client.post('/api/tasks', json={'prompt':'contract check','workspace_id':ws['id'],'client_request_id':'contract'})
    assert response.status_code == 201
    assert response.json()['metrics']['usage'] is None


def test_sse_schema_matches_stream_transport(api):
    client,app=api
    schema=app.openapi()
    content=schema['paths']['/api/tasks/{task_id}/events']['get']['responses']['200']['content']
    assert set(content)=={'text/event-stream'}
    assert content['text/event-stream']['schema']['type']=='string'
    workspace=client.get('/api/workspaces').json()[0]
    task=client.post('/api/tasks',json={'prompt':'SSE contract','workspace_id':workspace['id'],'client_request_id':'sse'}).json()
    response=client.get('/api/tasks/'+task['id']+'/events?follow=false')
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.text.startswith('id: 1\ndata: ')
