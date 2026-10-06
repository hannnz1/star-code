
import json

import httpx
import pytest

from muse.commerce.models import SiteBrief
from muse.contracts import TaskRequest, ToolCall
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry


def approved_call(repo, worker, name, arguments, risk='write'):
    task = repo.claim_next('manager')
    repo.prepare_call(task.id, 'manager', task.lease_epoch, 'crash-call', name, arguments, risk)
    approval = repo.request_approval(task.id, 'manager', task.lease_epoch, 'crash-call')
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    task = repo.claim_next('manager')
    repo.begin_call(task.id, 'manager', task.lease_epoch, 'crash-call')
    return ExecutionContext(worker.settings, repo, task, 'manager', enforce_budgets=True)


@pytest.mark.parametrize('committed', [True, False])
def test_crash_recovers_db_only_submission_without_unknown_or_duplicate(workflow, committed):
    service, repo, plan, worker = workflow
    ctx = approved_call(repo, worker, 'submit_blueprint', {'candidate': plan.blueprint.model_dump(mode='json')})
    if committed:
        service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'crash-call')
    repo.recover_expired_tasks(now=repo.get(ctx.task_id).lease_until + 1)
    assert repo.get(ctx.task_id).status == 'QUEUED'
    assert repo.calls(ctx.task_id)[0]['status'] == ('DONE' if committed else 'PREPARED')
    assert len(repo.db.rows("SELECT * FROM commerce_artifacts WHERE kind='commerce_output'")) == int(committed)
    assert repo.db.rows('SELECT model_requests FROM execution_budgets')[0]['model_requests'] == 0


def test_crash_recovers_team_dispatch_from_business_receipt(workflow):
    service, repo, plan, worker = workflow
    step = next(s for s in plan.steps if s.role == 'product_content')
    ctx = approved_call(repo, worker, 'dispatch_commerce_step', {'step_id': step.id}, 'execute')
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'manager-output')
    child = service.dispatch_step(ctx, step.id, call_id='crash-call')
    repo.recover_expired_tasks(now=repo.get(ctx.task_id).lease_until + 1)
    assert repo.calls(ctx.task_id)[0]['status'] == 'DONE'
    assert repo.get(ctx.task_id).status == 'QUEUED'
    assert [task.id for task in repo.children(ctx.task_id)] == [child.id]


def test_frozen_role_reload_is_explicitly_rejected_without_losing_snapshot(workflow):
    _, repo, plan, _ = workflow
    task_id = plan.steps[0].task_id
    task = repo.get(task_id)
    with pytest.raises(ValueError, match='frozen'):
        repo.control(task_id, 'reload', expected_revision=task.revision)
    assert repo.get(task_id).checkpoint['role_snapshot']['commerce'] == task.checkpoint['role_snapshot']['commerce']


async def test_large_business_context_has_task_scoped_paginated_read(workflow):
    service, repo, plan, worker = workflow
    project = service.repo.get_project(plan.project_id)
    brief = project.brief.model_copy(update={'audience': 'Facts ' * 500})
    project = service.repo.update_brief(project.id, brief, project.revision)
    context = service.repo.get_context(project.id, 'staging')
    snapshot = context.snapshot.model_copy(update={'pages': [{'id': 1, 'content': 'existing content ' * 2000}]})
    service.repo.save_context(project.id, 'stage', snapshot, context.capabilities, project.revision)
    project = service.repo.get_project(project.id)
    plan = service.create_workflow(project.id, 'build_site', 'Prepare', 'large-team', project.revision)
    task = repo.claim_next('manager')
    ctx = ExecutionContext(worker.settings, repo, task, 'manager', enforce_budgets=True)
    registry = ToolRegistry(ctx)
    result = await registry.execute(ToolCall(id='context', name='read_commerce_context', arguments={}))
    assert result.metadata['truncated']
    assert 'read_offload' in {definition.name for definition in registry.definitions()}
    tail = await registry.execute(ToolCall(id='tail', name='read_offload', arguments={'artifact_id': result.metadata['offload_id'], 'offset': 12000}))
    assert tail.status == 'success'
    assert 'existing content' in tail.content
    other = repo.create(TaskRequest(
        prompt='Another task', workspace_id=project.workspace_id, client_request_id='other'))
    other = repo.claim_next('inspect')
    other_ctx = ExecutionContext(worker.settings, repo, other, 'inspect')
    refused = await ToolRegistry(other_ctx).execute(ToolCall(id='foreign', name='read_offload', arguments={'artifact_id': result.metadata['offload_id']}))
    assert refused.status == 'denied'
    assert 'existing content' not in refused.content


def test_missing_merchant_facts_do_not_queue_paid_model_tasks(workflow):
    service, repo, plan, _ = workflow
    project = service.repo.get_project(plan.project_id)
    other = service.repo.create_project(project.workspace_id, SiteBrief(brand_name='Incomplete', language='en-US', currency='USD'), 'incomplete')
    from muse.commerce.models import EnvironmentRef
    other = service.repo.attach_connection(other.id, EnvironmentRef(id='other-stage', project_id=other.id, connector_ref='other-stage',
        environment='staging', public_url='https://shop.test'), 'other-bind', other.revision)
    context = service.repo.get_context(project.id, 'staging')
    service.repo.save_context(other.id, 'other-stage', context.snapshot.model_copy(update={'project_id': other.id}), context.capabilities, other.revision)
    other = service.repo.get_project(other.id)
    incomplete = service.create_workflow(other.id, 'build_site', 'Prepare', 'incomplete-team', other.revision)
    assert incomplete.state == 'NEEDS_INPUT'
    assert incomplete.error_code == 'FACTS_INCOMPLETE'
    assert all(step.task_id is None for step in incomplete.steps)
    assert len(repo.list()) == 1
    assert service.advance(incomplete.id, incomplete.revision) == incomplete


@pytest.mark.parametrize('status,code', [(401, 'AUTH_REQUIRED'), (403, 'PERMISSION_DENIED')])
async def test_main_adapter_keeps_allowlisted_connector_error_codes(workflow, status, code):
    _, _, plan, _ = workflow
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.platforms.wordpress import WordPressPlatform
    from muse.commerce_connector.api import create_connector_app
    from muse.commerce_connector.wordpress import WordPressConnection
    from muse.config import CommerceConnectorSettings
    def remote(request):
        return httpx.Response(status, content='private-password')
    app = create_connector_app({'stage': WordPressConnection('stage', plan.project_id, 'staging', 'https://shop.test', 'user', 'private-password')},
        token='service-token-012345', transport=httpx.MockTransport(remote))
    adapter = WordPressPlatform(CommerceConnectorSettings(service_url='http://127.0.0.1:8787', token='service-token-012345', versions_lock_path='none'),
        lock={}, transport=httpx.ASGITransport(app=app))
    with pytest.raises(CommerceFailure) as failure:
        await adapter.snapshot(plan.project_id, 'stage', 'staging')
    assert failure.value.public.code == code
    assert 'private-password' not in failure.value.public.model_dump_json()


@pytest.mark.parametrize('kind', ['invalid', 'corrupt', 'external'])
def test_recovery_keeps_error_receipts_and_unknown_external_boundary(workflow, kind):
    from sqlalchemy import text

    from muse.commerce.errors import CommerceFailure
    service, repo, plan, worker = workflow
    args = {'candidate': {'pages': []}} if kind == 'invalid' else {'candidate': plan.blueprint.model_dump(mode='json')}
    name = 'run_command' if kind == 'external' else 'submit_blueprint'
    ctx = approved_call(repo, worker, name, args, 'execute' if kind == 'external' else 'write')
    if kind == 'invalid':
        with pytest.raises(CommerceFailure):
            service.submit(ctx, 'blueprint', args, 'crash-call')
    elif kind == 'corrupt':
        service.submit(ctx, 'blueprint', args, 'crash-call')
        with repo.db.transaction() as conn:
            conn.execute(text("UPDATE commerce_artifacts SET digest=:digest WHERE kind='managed_call_receipt'"), {'digest': '0' * 64})
    repo.recover_expired_tasks(now=repo.get(ctx.task_id).lease_until + 1)
    call = repo.calls(ctx.task_id)[0]
    if kind == 'invalid':
        assert call['status'] == 'FAILED'
        assert call['result']['error_code'] == 'MODEL_OUTPUT_INVALID'
        assert service.repo.get_plan(plan.id, project_id=plan.project_id).steps[0].correction_attempts == 1
    else:
        assert call['status'] == 'UNKNOWN'
        assert repo.get(ctx.task_id).status == 'INTERRUPTED'


async def test_long_imported_product_facts_remain_readable_to_content_role(workflow):
    service, repo, plan, worker = workflow
    project = service.repo.get_project(plan.project_id)
    description = 'Ceramic cup. ' * 1300 + 'Final source marker.'
    imported = service.repo.import_products(project.id,
        'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,12.50,USD,5,Cups,' + description + ',\n', 'long-product', project.revision)
    business = service.create_workflow(project.id, 'launch_products', 'Prepare the product', 'long-product-team', project.revision, import_id=imported.id)
    repo.control(plan.steps[0].task_id, 'cancel', expected_revision=repo.get(plan.steps[0].task_id).revision)
    manager = repo.claim_next('manager')
    ctx = ExecutionContext(worker.settings, repo, manager, 'manager', enforce_budgets=True)
    service.submit(ctx, 'blueprint', {'candidate': business.blueprint.model_dump(mode='json')}, 'blueprint')
    child = service.dispatch_step(ctx, next(s.id for s in business.steps if s.role == 'product_content'))
    claimed = repo.claim_next('content')
    assert claimed.id == child.id
    registry = ToolRegistry(ExecutionContext(worker.settings, repo, claimed, 'content', enforce_budgets=True))
    result = await registry.execute(ToolCall(id='read-products', name='read_commerce_context', arguments={}))
    assert result.metadata['truncated']
    value, offset = result.content[:12000], 12000
    while offset is not None:
        part = await registry.execute(ToolCall(id='part-' + str(offset), name='read_offload', arguments={'artifact_id': result.metadata['offload_id'], 'offset': offset}))
        assert part.status == 'success'
        decoded = json.loads(part.content)
        value += decoded['text']
        offset = decoded['next_offset']
    assert json.loads(value)['products'][0]['description'] == description
    assert 'Final source marker.' in value
