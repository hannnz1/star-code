import pytest
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import SiteBrief
from tests.muse.commerce.test_commerce_workflow import actor


def pending_content(workflow, changes=None):
    service, runtime, old, worker = workflow
    project = service.repo.get_project(old.project_id)
    batch = service.repo.import_products(project.id,
        'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,12.30,USD,4,Cups,Ceramic cup.,\n',
        'content-source', project.revision)
    plan = service.create_workflow(project.id, 'launch_products', 'Write product content', 'content-team',
        project.revision, import_id=batch.id)
    # The fixture's earlier queue item is unrelated to this team.
    task = runtime.get(old.steps[0].task_id)
    runtime.control(task.id, 'cancel', expected_revision=task.revision)
    manager = actor(runtime, worker)
    service.submit(manager, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'manager-output')
    service.dispatch_step(manager, next(s.id for s in plan.steps if s.role == 'product_content'))
    content = actor(runtime, worker, 'content')
    candidate = plan.products[0].model_dump(mode='json')
    candidate.update(changes or {'title': 'Ceramic Cup', 'description': 'A ceramic cup.'})
    with pytest.raises(CommerceFailure) as error:
        service.submit(content, 'products', {'candidate': [candidate]}, 'content-output')
    assert error.value.public.code == 'FACTS_INCOMPLETE'
    from muse.commerce.content_proposals import ContentProposalRepository
    proposals = ContentProposalRepository(service.repo)
    return proposals, service, runtime, plan, manager, content, candidate


def test_confirm_creates_real_csv_source_and_invalidates_old_team_without_publishing(workflow):
    proposals, service, runtime, plan, manager, _ctx, candidate = pending_content(workflow)
    current = service.repo.get_plan(plan.id, project_id=plan.project_id)
    view = proposals.latest(plan.project_id, plan.id)
    project = service.repo.get_project(plan.project_id)
    assert view.status == 'PENDING' and view.original[0] == plan.products[0]
    assert view.candidates[0].title == candidate['title']
    result = proposals.confirm(plan.project_id, plan.id, view.id, project.revision, current.revision, view.content_digest)
    assert result.project.revision == project.revision + 1
    assert result.batch.project_revision == result.project.revision
    assert result.batch.result.drafts[0].title == 'Ceramic Cup'
    assert result.batch.result.drafts[0].price == plan.products[0].price
    assert result.batch.result.drafts[0].source_facts['name'] == 'Ceramic Cup'
    assert service.repo.get_plan(plan.id, project_id=plan.project_id).state == 'STALE'
    assert runtime.get(manager.task_id).cancel_requested
    assert proposals.confirm(plan.project_id, plan.id, view.id, project.revision, current.revision, view.content_digest) == result
    assert len(service.repo.list_product_imports(plan.project_id)) == 2
    assert not runtime.db.rows("SELECT 1 FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")
    assert proposals.latest(plan.project_id, plan.id).status == 'CONFIRMED'


@pytest.mark.parametrize('changes', [ {'price': '1.00'}, {'stock': 99}, {'sku': 'OTHER'},
    {'category': 'Other'}, {'currency': 'CNY'}, {'media_refs': ['injected']}, {'source_facts': {'name': 'invented'}} ])
def test_non_content_mutations_never_offer_confirmation(workflow, changes):
    proposals, _service, _runtime, plan, *_ = pending_content(workflow, changes)
    with pytest.raises(CommerceFailure) as error:
        proposals.latest(plan.project_id, plan.id)
    assert error.value.public.code == 'NOT_FOUND'


def test_stale_cancelled_and_wrong_scope_confirmation_fail_atomically(workflow):
    proposals, service, runtime, plan, manager, *_ = pending_content(workflow)
    view = proposals.latest(plan.project_id, plan.id)
    project = service.repo.get_project(plan.project_id)
    current = service.repo.get_plan(plan.id, project_id=plan.project_id)
    other = service.repo.create_project(project.workspace_id, SiteBrief(brand_name='Other', language='en-US', currency='USD'), 'other-content')
    for args in [(other.id, plan.id, view.id, project.revision, current.revision, view.content_digest),
                 (project.id, plan.id, view.id, project.revision, current.revision - 1, view.content_digest),
                 (project.id, plan.id, view.id, project.revision, current.revision, '0' * 64)]:
        with pytest.raises(CommerceFailure):
            proposals.confirm(*args)
    task = runtime.get(manager.task_id)
    runtime.control(task.id, 'cancel', expected_revision=task.revision)
    with pytest.raises(CommerceFailure):
        proposals.confirm(project.id, plan.id, view.id, project.revision, current.revision, view.content_digest)
    assert service.repo.get_project(project.id).revision == project.revision
    assert len(service.repo.list_product_imports(project.id)) == 1


def test_replayed_submission_and_source_tampering_cannot_replace_pending_candidate(workflow):
    proposals, service, runtime, plan, _manager, ctx, candidate = pending_content(workflow)
    original = proposals.latest(plan.project_id, plan.id)
    with pytest.raises(CommerceFailure):
        service.submit(ctx, 'products', {'candidate': [candidate]}, 'content-output')
    assert proposals.latest(plan.project_id, plan.id) == original
    with pytest.raises(CommerceFailure):
        service.submit(ctx, 'products', {'candidate': [{**candidate, 'title': 'Replacement'}]}, 'content-output')
    assert proposals.latest(plan.project_id, plan.id) == original
    with runtime.db.transaction() as conn:
        conn.execute(text("UPDATE commerce_artifacts SET digest=:digest WHERE id=:id"), {'id': original.id, 'digest': '0' * 64})
    with pytest.raises(CommerceFailure):
        proposals.latest(plan.project_id, plan.id)


def test_other_role_finishing_requires_refresh_but_does_not_strand_frozen_wording(workflow):
    proposals, service, runtime, plan, manager, *_ = pending_content(workflow)
    before = proposals.latest(plan.project_id, plan.id)
    service.dispatch_step(manager, next(s.id for s in plan.steps if s.role == 'site_developer'))
    developer = actor(runtime, workflow[3], 'developer')
    service.submit(developer, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'developer-output')
    with pytest.raises(CommerceFailure):
        proposals.confirm(plan.project_id, plan.id, before.id, before.project_revision, before.plan_revision, before.content_digest)
    refreshed = proposals.latest(plan.project_id, plan.id)
    assert refreshed.plan_revision > before.plan_revision
    assert refreshed.content_digest == before.content_digest
    result = proposals.confirm(plan.project_id, plan.id, refreshed.id,
        refreshed.project_revision, refreshed.plan_revision, refreshed.content_digest)
    assert result.batch.result.drafts[0].title == 'Ceramic Cup'
