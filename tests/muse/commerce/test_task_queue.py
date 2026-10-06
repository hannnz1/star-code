import pytest

from muse.commerce.api import DraftBatchInput, TaskDraftInput
from muse.commerce.errors import CommerceFailure
from muse.commerce.task_drafts import CommerceDraftService
from muse.commerce.task_queue import CommerceTaskQueue


def prepare(workflow, count=2, dependencies=()):
    service, tasks, plan, worker = workflow
    drafts = CommerceDraftService(service.repo, service)
    project = service.repo.get_project(plan.project_id)
    saved = [drafts.create(project.id, TaskDraftInput(kind='build_site', title=f'Draft {index}', prompt='Prepare site',
        expected_project_revision=project.revision, dependency_plan_ids=list(dependencies), client_request_id=f'queue-{index}'))
        for index in range(count)]
    return service, tasks, plan, worker, project, drafts, saved, CommerceTaskQueue(service.repo, service)


def body(project, drafts, action='start', key='batch'):
    return DraftBatchInput(items=[{'draft_id': draft.id, 'expected_revision': draft.revision} for draft in drafts],
        expected_project_revision=project.revision, action=action, client_request_id=key)


def test_batch_admission_waits_for_capacity_and_restarts_without_duplicate_tasks(workflow):
    service, tasks, plan, worker, project, drafts, saved, queue = prepare(workflow)
    result = queue.batch(project.id, body(project, saved))
    assert [item.status for item in result] == ['STARTED', 'QUEUED']
    assert result[1].queue_reason == 'capacity' and len(tasks.list()) == 2
    assert queue.capacity(project.id)['active'] == 2
    assert queue.batch(project.id, body(project, saved)) == result
    first_root = next(step.task_id for step in plan.steps if step.role == 'store_manager')
    tasks.control(first_root, 'cancel', expected_revision=tasks.get(first_root).revision)
    restarted = CommerceTaskQueue(service.repo, service)
    restarted.promote()
    promoted = drafts.list(project.id)[1]
    assert promoted.status == 'STARTED' and promoted.plan_id
    assert len(tasks.list()) == 3
    restarted.promote()
    assert len(tasks.list()) == 3


def test_dependency_wait_releases_only_after_success_and_failed_dependency_stays_queued(workflow):
    service, tasks, plan, worker = workflow
    service, tasks, plan, worker, project, drafts, saved, queue = prepare(workflow, dependencies=[plan.id])
    result = queue.batch(project.id, body(project, saved))
    assert all(item.status == 'QUEUED' and item.queue_reason == 'dependencies' for item in result)
    assert len(tasks.list()) == 1
    plan = service.repo.save_plan(plan.model_copy(update={'state': 'FAILED'}), plan.revision)
    queue.promote()
    assert all(item.queue_reason == 'dependency_failed' for item in drafts.list(project.id))
    assert len(tasks.list()) == 1
    service.repo.save_plan(plan.model_copy(update={'state': 'SUCCEEDED'}), plan.revision)
    root = tasks.claim_next('manager')
    tasks.finish(root.id, 'manager', root.lease_epoch, 'SUCCEEDED', 'controlled fixture')
    queue.promote()
    assert all(item.status == 'STARTED' for item in drafts.list(project.id))
    assert len(tasks.list()) == 3


def test_stale_batch_is_atomic_and_queue_can_be_cancelled_without_execution(workflow):
    service, tasks, plan, worker, project, drafts, saved, queue = prepare(workflow)
    renamed = drafts.rename(project.id, saved[1].id, 'Changed', saved[1].revision)
    with pytest.raises(CommerceFailure):
        queue.batch(project.id, body(project, saved))
    assert len(tasks.list()) == 1 and all(item.status == 'DRAFT' for item in drafts.list(project.id))
    request = body(project, [saved[0], renamed])
    result = queue.batch(project.id, request)
    queued = next(item for item in result if item.status == 'QUEUED')
    cancelled = queue.batch(project.id, body(project, [queued], 'cancel', 'cancel-one'))[0]
    assert cancelled.status == 'ARCHIVED'
    queue.promote()
    assert len(tasks.list()) == 2
    with pytest.raises(CommerceFailure):
        queue.batch(project.id, body(project, [saved[0]], 'archive', 'batch'))


def test_duplicate_dependencies_and_stale_project_block_without_partial_mutations(workflow):
    service, tasks, plan, worker, project, drafts, saved, queue = prepare(workflow, count=1)
    with pytest.raises(CommerceFailure):
        drafts.create(project.id, TaskDraftInput(kind='build_site', title='Bad', prompt='Prepare',
            expected_project_revision=project.revision, dependency_plan_ids=[plan.id, plan.id], client_request_id='bad-dependency'))
    with pytest.raises(CommerceFailure):
        drafts.create(project.id, TaskDraftInput(kind='build_site', title='Bad', prompt='Prepare',
            expected_project_revision=project.revision, dependency_plan_ids=['foreign-plan'], client_request_id='missing-dependency'))
    service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'Minimal'}), project.revision)
    with pytest.raises(CommerceFailure):
        queue.batch(project.id, body(project, saved))
    assert len(tasks.list()) == 1


def test_worker_claim_limit_keeps_existing_plan_children_running(workflow):
    from muse.tools.context import ExecutionContext
    service, tasks, plan, worker = workflow
    project = service.repo.get_project(plan.project_id)
    second = service.create_workflow(project.id, 'build_site', 'Second', 'worker-limit', project.revision)
    root = tasks.claim_next('manager', commerce_limit=1)
    assert root.checkpoint['commerce']['plan_id'] == plan.id
    assert tasks.claim_next('other', commerce_limit=1) is None
    ctx = ExecutionContext(worker.settings, tasks, root, 'manager', enforce_budgets=True)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'limited-blueprint')
    service.dispatch_step(ctx, next(step.id for step in plan.steps if step.role == 'site_developer'))
    child = tasks.claim_next('child', commerce_limit=1)
    assert child.checkpoint['commerce']['plan_id'] == plan.id
    tasks.finish(child.id, 'child', child.lease_epoch, 'SUCCEEDED', 'controlled capacity fixture')
    tasks.finish(root.id, 'manager', root.lease_epoch, 'SUCCEEDED', 'controlled capacity fixture')
    admitted = tasks.claim_next('other', commerce_limit=1)
    assert admitted.checkpoint['commerce']['plan_id'] == second.id


def test_draft_one_shot_auto_apply_is_transferred_only_to_its_started_plan(workflow):
    service, tasks, plan, worker, project, drafts, saved, queue = prepare(workflow, count=1)
    request = body(project, saved).model_copy(update={'auto_apply_local': True})
    result = queue.batch(project.id, request)[0]
    assert result.status == 'STARTED' and result.auto_apply_local
    from muse.commerce.task_automation import LocalApplyService
    automation = LocalApplyService(service.repo, worker.settings.data_dir / 'commerce-source.git')
    assert automation.get(project.id, result.plan_id).status == 'ARMED'
    assert automation.get(project.id, plan.id) is None
