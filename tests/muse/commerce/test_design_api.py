from tests.muse.commerce.test_project_api import request
pytest_plugins = ['tests.muse.commerce.test_project_api']


def setup(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    path = '/api/commerce/projects/' + project['id']
    return project, path


def test_initialize_once_from_existing_blueprint(client):
    project, path = setup(client)
    assert client.get(path + '/design').json() is None
    a = client.post(path+'/design', json={'expected_project_revision':1}).json()
    assert len(a['home_sections']) == 5
    assert client.post(path+'/design', json={'expected_project_revision':1}).json() == a
    assert len(client.get(path+'/plans').json()) == 1


def test_revision_idempotency_and_validation(client):
    project,path = setup(client)
    doc = client.post(path+'/design',json={'expected_project_revision':1}).json()
    doc['home_sections'][0]['props']['title'] = 'Pet Home'
    body={'expected_project_revision':1,'expected_revision':1,'client_request_id':'save-one','document':doc}
    saved=client.patch(path+'/design',json=body)
    assert saved.status_code == 200
    assert saved.json()['revision'] == 2
    assert client.patch(path+'/design',json=body).json() == saved.json()
    assert client.patch(path+'/design',json={**body,'client_request_id':'other'}).status_code == 409
    doc['revision'] = 2
    body.update(expected_revision=2,client_request_id='bad')
    doc['home_sections'][0]['props']['media_id'] = 'another-store-media'
    assert client.patch(path+'/design',json=body).status_code == 422
    doc['home_sections'][0]['props']['media_id'] = None
    doc['schema_version'] = 2
    assert client.patch(path+'/design',json=body).status_code == 422
    doc['schema_version'] = 1
    doc['home_sections'][0]['props']['link'] = 'javascript:alert(1)'
    assert client.patch(path+'/design',json=body).status_code == 422
    assert client.get(path+'/design').json()['home_sections'][0]['props']['title'] == 'Pet Home'


def test_rebind_preserves_content_and_invalidates_workflow(workflow):
    from muse.commerce.design_repository import DesignRepository
    service,runtime,team,worker = workflow
    repo=service.repo; project=repo.get_project(team.project_id)
    designs=DesignRepository(repo)
    doc=designs.get_or_create(project.id,project.revision)
    doc.home_sections[0].props.title='Keep me'
    doc=designs.save(project.id,project.revision,doc.revision,'edit',doc)
    assert repo.get_plan(team.id,project_id=project.id).state == 'STALE'
    project=repo.update_brief(project.id,project.brief.model_copy(update={'style':'new style'}),project.revision)
    rebound=designs.get_or_create(project.id,project.revision)
    assert rebound.home_sections[0].props.title == 'Keep me'
    assert rebound.project_revision == project.revision
    assert rebound.revision > doc.revision


def test_unknown_write_prevents_design_invalidation(workflow):
    import pytest
    from sqlalchemy import text
    from muse.commerce.design_repository import DesignRepository
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.repository import encode,digest
    service,runtime,team,worker=workflow
    repo=service.repo;project=repo.get_project(team.project_id)
    designs=DesignRepository(repo);doc=designs.get_or_create(project.id,project.revision)
    marker={'state':'UNKNOWN'}
    with repo.db.transaction() as conn:
        conn.execute(text("INSERT INTO commerce_artifacts VALUES('unknown-write',:project,NULL,'test_write',:digest,:data)"),{'project':project.id,'digest':digest(marker),'data':encode(marker)})
    doc.home_sections[0].props.title='Cannot apply while outcome unknown'
    with pytest.raises(CommerceFailure) as error: designs.save(project.id,project.revision,doc.revision,'blocked-save',doc)
    assert error.value.public.code=='PROJECT_BUSY'
    assert designs.get(project.id).revision==doc.revision


def test_initialization_during_unknown_write_does_not_create_blueprint(workflow):
    import pytest
    from sqlalchemy import text
    from muse.commerce.design_repository import DesignRepository
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.repository import encode,digest
    service,runtime,team,worker=workflow
    repo=service.repo;project=repo.get_project(team.project_id)
    marker={'state':'UNKNOWN'}
    with repo.db.transaction() as conn:
        before=conn.execute(text('SELECT COUNT(*) FROM commerce_plans WHERE project_id=:id'),{'id':project.id}).scalar()
        conn.execute(text("INSERT INTO commerce_artifacts VALUES('unknown-init',:project,NULL,'test_write',:digest,:data)"),{'project':project.id,'digest':digest(marker),'data':encode(marker)})
    with pytest.raises(CommerceFailure) as error:
        DesignRepository(repo).get_or_create(project.id,project.revision)
    assert error.value.public.code=='PROJECT_BUSY'
    assert DesignRepository(repo).get(project.id) is None
    with repo.db.transaction() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM commerce_plans WHERE project_id=:id'),{'id':project.id}).scalar()==before
