from tests.muse.commerce.test_project_api import request
from tests.muse.commerce.test_shipping_rules import rules

pytest_plugins = ['tests.muse.commerce.test_project_api']


def setup(client):
    project = client.post('/api/commerce/projects', json=request(client)).json()
    path = '/api/commerce/projects/' + project['id']
    plan = client.post(path+'/site-blueprint', json={'expected_revision': 1, 'client_request_id': 'shipping-source'}).json()
    return path, plan, {'expected_revision': 1, 'expected_plan_revision': plan['revision'],
                       'plan_id': plan['id'], 'client_request_id': 'save-shipping', 'rules': rules()}


def test_shipping_draft_save_replay_and_revision_conflict(client):
    path, plan, body = setup(client)
    saved = client.patch(path+'/shipping-rules', json=body)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert result['blueprint']['required_settings']['shipping_rules'] == rules()
    assert result['revision'] == plan['revision'] + 1
    assert client.get(path+'/shipping-rules').json() == result
    assert client.patch(path+'/shipping-rules', json=body).json() == result
    assert client.patch(path+'/shipping-rules', json={**body, 'client_request_id': 'stale'}).status_code == 409
    changed = {**body, 'rules': rules(currency='AUD')}
    assert client.patch(path+'/shipping-rules', json=changed).status_code == 409
    assert client.get('/api/tasks').json() == []
    assert result['state'] == 'NEEDS_INPUT'
    assert result['steps'] == []


def test_shipping_draft_rejects_currency_and_foreign_source(client):
    path, plan, body = setup(client)
    assert client.patch(path+'/shipping-rules', json={**body, 'rules': rules(currency='AUD')}).status_code == 422
    assert client.patch(path+'/shipping-rules', json={**body, 'plan_id': 'other-project-plan'}).status_code == 409
    assert client.get(path+'/shipping-rules').json() == plan


def test_build_source_freezes_shipping_and_old_plan_becomes_stale(workflow):
    from muse.commerce.shipping_drafts import ShippingDraftRepository
    from muse.commerce.shipping_rules import ShippingRules
    service, _, old, _ = workflow
    project = service.repo.get_project(old.project_id)
    source = service.repo.create_site_blueprint(project.id, 'shipping-source', project.revision)
    saved = ShippingDraftRepository(service.repo).save(project.id, project.revision, source.id,
                    source.revision, 'shipping-save', ShippingRules.model_validate(rules()))
    assert service.repo.get_plan(old.id, project_id=project.id).state == 'STALE'
    fresh = service.create_workflow(project.id, 'build_site', 'Build rules', 'shipping-workflow', project.revision)
    assert fresh.blueprint.required_settings['shipping_rules'] == rules()
    assert saved.blueprint.required_settings['shipping_rules'] == rules()


def test_shipping_save_rebases_design_without_changing_merchant_content(workflow):
    from muse.commerce.design_repository import DesignRepository
    from muse.commerce.shipping_drafts import ShippingDraftRepository
    from muse.commerce.shipping_rules import ShippingRules
    service,_,old,_=workflow; repo=service.repo; project=repo.get_project(old.project_id)
    designs=DesignRepository(repo); before=designs.get_or_create(project.id,project.revision)
    drafts=ShippingDraftRepository(repo); source=drafts.get(project.id)
    saved=drafts.save(project.id,project.revision,source.id,source.revision,'rebase-shipping',ShippingRules.model_validate(rules()))
    after=designs.get(project.id)
    assert after.revision==before.revision+1 and after.blueprint_revision==saved.revision
    assert after.home_sections==before.home_sections and after.theme_tokens==before.theme_tokens
    assert drafts.get(project.id)==saved


def test_unknown_remote_write_blocks_draft_and_design_rebase_atomically(workflow):
    import pytest
    from sqlalchemy import text
    from muse.commerce.design_repository import DesignRepository
    from muse.commerce.shipping_drafts import ShippingDraftRepository
    from muse.commerce.shipping_rules import ShippingRules
    from muse.commerce.repository import digest,encode
    from muse.commerce.errors import CommerceFailure
    service,_,old,_=workflow; repo=service.repo;project=repo.get_project(old.project_id)
    designs=DesignRepository(repo);before=designs.get_or_create(project.id,project.revision)
    drafts=ShippingDraftRepository(repo);source=drafts.get(project.id)
    with repo.db.transaction() as conn:
        data={'state':'UNKNOWN'}
        conn.execute(text("INSERT INTO commerce_artifacts(id,project_id,plan_id,kind,digest,data) VALUES('pending-shipping',:project,:plan,'test_remote_attempt',:digest,:data)"),
            {'project':project.id,'plan':old.id,'digest':digest(data),'data':encode(data)})
    with pytest.raises(CommerceFailure) as caught:
        drafts.save(project.id,project.revision,source.id,source.revision,'blocked-save',ShippingRules.model_validate(rules()))
    assert caught.value.public.code=='PROJECT_BUSY'
    assert drafts.get(project.id)==source and designs.get(project.id)==before
