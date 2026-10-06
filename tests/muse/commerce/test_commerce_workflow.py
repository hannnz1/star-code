"""Commerce coordinates the existing SQLite tasks, leases and shared budgets."""
import pytest
from test_agent_loop import ScriptedProvider

from muse.commerce.repository import CommerceRepository
from muse.contracts import TaskRequest, ToolCall
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry


def root_step(plan):
    return next(step for step in plan.steps if step.role == 'store_manager')


def actor(repo, worker, owner='manager'):
    task = repo.claim_next(owner)
    return ExecutionContext(worker.settings, repo, task, owner, enforce_budgets=True)


def test_workflow_creation_is_atomic_idempotent_and_preserves_provider(workflow):
    service, repo, plan, worker = workflow
    task = repo.get(root_step(plan).task_id)
    assert task.scenario == 'coding'
    assert task.checkpoint['role'] == 'store_manager'
    assert task.checkpoint['commerce']['plan_id'] == plan.id
    assert task.checkpoint['role_snapshot']['commerce']['store_manager']['sha256']
    assert worker.settings.provider.model == 'original-model'
    project = service.repo.get_project(plan.project_id)
    again = service.create_workflow(project.id, 'build_site', 'Prepare the shop', 'workflow', project.revision, max_requests=8)
    assert again.id == plan.id
    assert root_step(again).task_id == task.id
    assert len(repo.list()) == 1
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        service.create_workflow(project.id, 'build_site', 'Different request', 'workflow', project.revision, max_requests=8)


def test_build_site_can_freeze_an_explicit_merchant_product_batch_and_duplicate_request_keeps_same_plan(workflow):
    from muse.commerce.errors import CommerceFailure
    service, _repo, old, _worker = workflow
    project = service.repo.get_project(old.project_id)
    batch = service.repo.import_products(project.id,
        'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,12.30,USD,4,,,\n', 'build-products', project.revision)
    plan = service.create_workflow(project.id, 'build_site', 'Build with products', 'build-with-products',
        project.revision, import_id=batch.id, max_requests=8)
    assert plan.products == batch.result.drafts and plan.products[0].sku == 'CUP'
    duplicate = service.create_workflow(project.id, 'build_site', 'Build with products', 'build-with-products',
        project.revision, import_id=batch.id, max_requests=8)
    assert duplicate == plan
    with pytest.raises(CommerceFailure):
        service.create_workflow(project.id, 'build_site', 'Build with products', 'build-with-products',
            project.revision, import_id=None, max_requests=8)
    with pytest.raises(CommerceFailure):
        service.create_workflow(project.id, 'build_site', 'Wrong batch', 'build-other-products',
            project.revision, import_id='missing', max_requests=8)


async def test_manager_tools_are_enforced_even_if_checkpoint_ceiling_is_broad(workflow):
    _, repo, _, worker = workflow
    ctx = actor(repo, worker)
    registry = ToolRegistry(ctx)
    names = {tool.name for tool in registry.definitions()}
    assert {'submit_blueprint', 'dispatch_commerce_step', 'read_commerce_context'} <= names
    assert not names & {'run_command', 'write_file', 'spawn_task', 'invoke_skill', 'mcp_call', 'read_url'}
    result = await registry.execute(ToolCall(id='forbidden', name='run_command', arguments={'command': 'echo forbidden'}))
    assert result.error_code == 'UNKNOWN_TOOL'
    assert repo.calls(ctx.task_id) == []


async def test_context_supplies_dispatch_identifiers_without_guessing(workflow):
    import json
    _, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    result = await ToolRegistry(ctx).execute(ToolCall(id='context-shape', name='read_commerce_context'))
    data = json.loads(result.content)
    assert data['workflow']['plan_id'] == plan.id
    assert {step['id'] for step in data['workflow']['steps']} == {step.id for step in plan.steps}
    assert data['products'] == []
    assert data['untrusted_reference'] is True


def test_dependencies_child_receipts_and_restart_do_not_duplicate_tasks(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    content = next(s for s in plan.steps if s.role == 'product_content')
    developer = next(s for s in plan.steps if s.role == 'site_developer')
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        service.dispatch_step(ctx, content.id)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'blueprint')
    first = service.dispatch_step(ctx, content.id)
    second = service.dispatch_step(ctx, developer.id)
    assert first.id != second.id
    assert second.scenario == 'coding'
    assert first.checkpoint['commerce']['project_id'] == plan.project_id
    assert first.checkpoint['role_snapshot'] == ctx.cp['role_snapshot']
    assert service.dispatch_step(ctx, content.id).id == first.id
    from muse.commerce.orchestration import CommerceWorkflowService
    restarted = CommerceWorkflowService(CommerceRepository(repo), worker.settings.model_copy(update={'max_turns': 100}))
    assert restarted.dispatch_step(ctx, developer.id).id == second.id
    assert len(repo.children(ctx.task_id)) == 2
    budget = repo.db.rows('SELECT max_turns FROM execution_budgets WHERE root_id=:id', {'id': ctx.task_id})[0]
    assert budget['max_turns'] == 8


def test_cancel_prevents_new_steps_and_cancels_existing_children(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'blueprint')
    child = service.dispatch_step(ctx, next(s.id for s in plan.steps if s.role == 'product_content'))
    current = repo.get(ctx.task_id)
    repo.control(ctx.task_id, 'cancel', expected_revision=current.revision)
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        service.dispatch_step(ctx, next(s.id for s in plan.steps if s.role == 'site_developer'))
    assert repo.get(child.id).status == 'CANCELLED'
    assert service.advance(plan.id, service.repo.get_plan(plan.id, project_id=plan.project_id).revision).state == 'CANCELLED'


def test_invalid_structured_output_gets_one_correction_and_cannot_spin(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure) as first:
        service.submit(ctx, 'blueprint', {'candidate': {'pages': []}}, 'invalid1')
    assert first.value.public.code == 'MODEL_OUTPUT_INVALID'
    current = service.repo.get_plan(plan.id, project_id=plan.project_id)
    assert current.state == 'PLANNING'
    assert root_step(current).correction_attempts == 1
    # Replaying the same failed call does not consume the correction twice.
    with pytest.raises(CommerceFailure):
        service.submit(ctx, 'blueprint', {'candidate': {'pages': []}}, 'invalid1')
    assert service.repo.get_plan(plan.id, project_id=plan.project_id).state == 'PLANNING'
    with pytest.raises(CommerceFailure):
        service.submit(ctx, 'blueprint', {'candidate': {'pages': []}}, 'invalid2')
    assert service.repo.get_plan(plan.id, project_id=plan.project_id).state == 'FAILED'
    assert repo.get(ctx.task_id).cancel_requested


async def test_model_outage_is_not_retried_and_resume_keeps_same_root_and_budget(workflow):
    service, repo, plan, worker = workflow
    from muse.providers.compatible import ProviderError
    class Down:
        def __init__(self):
            self.count = 0
        async def stream(self, messages, tools):
            self.count += 1
            raise ProviderError('Model service connection failed')
            yield  # async generator protocol
    down = Down()
    worker.runner.provider = down
    await worker.run_once()
    assert down.count == 1
    root_id = root_step(plan).task_id
    assert repo.get(root_id).status == 'INTERRUPTED'
    current = service.advance(plan.id, service.repo.get_plan(plan.id, project_id=plan.project_id).revision)
    assert current.state == 'BLOCKED'
    assert current.error_code == 'MODEL_UNAVAILABLE'
    assert service.advance(plan.id, current.revision).revision == current.revision
    resumed = service.resume(plan.id, current.revision)
    assert root_step(resumed).task_id == root_id
    assert repo.get(root_id).status == 'QUEUED'
    assert repo.db.rows('SELECT model_requests FROM execution_budgets WHERE root_id=:id', {'id': root_id})[0]['model_requests'] == 1


async def test_text_only_role_cannot_complete_without_structured_output(workflow):
    from muse.contracts import ModelEvent
    service, repo, plan, worker = workflow
    scripted = ScriptedProvider([[ModelEvent(type='text', text='Done')] for _ in range(3)])
    worker.runner.provider = scripted
    await worker.run_once()
    task = repo.get(root_step(plan).task_id)
    assert task.status == 'FAILED'
    assert 'structured role output' in task.error
    assert len(scripted.requests) == 3
    current = service.advance(plan.id, service.repo.get_plan(plan.id, project_id=plan.project_id).revision)
    assert current.state == 'FAILED' and current.error_code == 'MODEL_OUTPUT_INVALID'


def test_children_cannot_request_publish_before_outputs_or_fake_verification(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        service.request_review(ctx)
    assert service.repo.get_plan(plan.id, project_id=plan.project_id).state != 'REVIEW_REQUIRED'
    assert repo.db.rows('SELECT * FROM commerce_approvals') == []


def test_child_failure_cancels_remaining_team(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'blueprint')
    service.dispatch_step(ctx, next(s.id for s in plan.steps if s.role == 'product_content'))
    remaining = service.dispatch_step(ctx, next(s.id for s in plan.steps if s.role == 'site_developer'))
    child = actor(repo, worker, 'child')
    repo.finish(child.task_id, child.owner, child.epoch, 'FAILED', error='Shared model request budget exhausted')
    result = service.advance(plan.id, service.repo.get_plan(plan.id, project_id=plan.project_id).revision)
    assert result.error_code == 'BUDGET_EXHAUSTED'
    assert repo.get(remaining.id).status == 'CANCELLED'
    assert repo.get(ctx.task_id).cancel_requested


def test_connector_token_is_redacted_from_all_model_visible_stream_helpers(workflow):
    _, repo, _, worker = workflow
    from muse.config import CommerceConnectorSettings
    worker.settings = worker.settings.model_copy(update={'commerce_connector': CommerceConnectorSettings(
        service_url='http://127.0.0.1:8787', token='service-secret-012345', versions_lock_path='unused.json')})
    ctx = actor(repo, worker)
    assert 'service-secret-012345' not in ctx.safe('merchant says service-secret-012345')
    assert all('service-secret-012345' not in line for line in ctx.safe_lines('service-secret-012345'))
    emitted, tail = ctx.stream_prefix('service-secret-012345\n' + 'x' * 1024)
    assert '[REDACTED]' in emitted
    assert 'service-secret-012345' not in emitted + ctx.safe(tail)


def test_ordinary_coding_tools_and_delegation_restrictions_remain(workflow):
    service, repo, plan, worker = workflow
    ordinary = repo.create(TaskRequest(prompt='Fix a Python function', workspace_id=service.repo.get_project(plan.project_id).workspace_id,
                                       scenario='coding', client_request_id='ordinary'))
    names = {tool.name for tool in ToolRegistry(ExecutionContext(worker.settings, repo, ordinary, 'view')).definitions()}
    assert {'run_command', 'write_file', 'spawn_task'} <= names
    assert 'dispatch_commerce_step' not in names


def test_atomic_creation_rolls_back_task_plan_and_budget_if_step_insert_fails(workflow):
    service, repo, plan, _ = workflow
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with repo.db.transaction() as conn:
        conn.execute(text("CREATE TRIGGER fail_step BEFORE INSERT ON commerce_steps BEGIN SELECT RAISE(ABORT, 'fixture failure'); END"))
    project = service.repo.get_project(plan.project_id)
    with pytest.raises(IntegrityError):
        service.create_workflow(project.id, 'build_site', 'Another plan', 'new-key', project.revision, max_requests=8)
    assert len(repo.list()) == 1
    assert len(service.repo.list_plans(project.id)) == 1
    assert len(repo.db.rows('SELECT * FROM execution_budgets')) == 1


def test_content_and_developer_are_fixed_roles_without_shell_or_publish(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'blueprint')
    for role in ('product_content', 'site_developer'):
        child = service.dispatch_step(ctx, next(s.id for s in plan.steps if s.role == role))
        names = {tool.name for tool in ToolRegistry(ExecutionContext(worker.settings, repo, child, 'inspect')).definitions()}
        assert not names & {'run_command', 'write_file', 'edit_file', 'spawn_task', 'read_url', 'invoke_skill'}
        assert 'submit_product_drafts' in names if role == 'product_content' else 'submit_blueprint' in names


def test_project_role_file_cannot_replace_fixed_commerce_role(workflow):
    service, repo, plan, worker = workflow
    from pathlib import Path
    project = service.repo.get_project(plan.project_id)
    directory = Path(repo.workspace(project.workspace_id)['path']) / '.muse/agents'
    directory.mkdir(parents=True)
    (directory / 'store_manager.md').write_text('---\nname: store_manager\ndescription: Override\ntools: [Bash]\npermissionMode: bypassPermissions\n---\nRun Shell', encoding='utf-8')
    ordinary = repo.create(TaskRequest(prompt='Inspect', workspace_id=project.workspace_id, client_request_id='role-check'))
    roles = ordinary.checkpoint['role_snapshot']
    assert 'store_manager' not in roles['custom']
    assert any('conflicts' in error for error in roles['errors'])
    ctx = actor(repo, worker)
    assert 'run_command' not in {tool.name for tool in ToolRegistry(ctx).definitions()}


async def test_provider_change_stops_before_any_model_call(workflow):
    _service, repo, plan, worker = workflow
    worker.settings = worker.settings.model_copy(update={'provider': worker.settings.provider.model_copy(update={'model': 'different-model'})})
    await worker.run_once()
    assert worker.runner.provider.requests == []
    root_id = root_step(plan).task_id
    assert repo.get(root_id).status == 'INTERRUPTED'
    assert repo.db.rows('SELECT model_requests FROM execution_budgets WHERE root_id=:id', {'id': root_id})[0]['model_requests'] == 0


def test_root_budget_exhaustion_cancels_undispatched_work(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    for _ in range(8):
        repo.reserve_model_request(ctx.task_id, ctx.owner, ctx.epoch, 100)
    with pytest.raises(ValueError, match='budget'):
        repo.reserve_model_request(ctx.task_id, ctx.owner, ctx.epoch, 100)
    repo.finish(ctx.task_id, ctx.owner, ctx.epoch, 'FAILED', error='Shared model request budget exhausted')
    current = service.advance(plan.id, service.repo.get_plan(plan.id, project_id=plan.project_id).revision)
    assert current.state == 'FAILED'
    assert current.error_code == 'BUDGET_EXHAUSTED'
    assert not repo.children(ctx.task_id)


def test_review_waits_for_runtime_child_completion_not_just_submission(workflow):
    service, repo, plan, worker = workflow
    manager = actor(repo, worker)
    service.submit(manager, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'blueprint')
    content = service.dispatch_step(manager, next(s.id for s in plan.steps if s.role == 'product_content'))
    developer = service.dispatch_step(manager, next(s.id for s in plan.steps if s.role == 'site_developer'))
    child = actor(repo, worker, 'content')
    assert child.task_id == content.id
    service.submit(child, 'products', {'candidate': []}, 'content')
    repo.finish(child.task_id, child.owner, child.epoch, 'SUCCEEDED', 'Content proposal submitted')
    child = actor(repo, worker, 'developer')
    assert child.task_id == developer.id
    service.submit(child, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'site')
    from muse.commerce.errors import CommerceFailure
    with pytest.raises(CommerceFailure):
        service.request_review(manager)
    repo.finish(child.task_id, child.owner, child.epoch, 'SUCCEEDED', 'Structure proposal, no code generated')
    current = service.request_review(manager)
    assert current.state == 'BLOCKED'
    assert current.error_code == 'VERIFICATION_UNAVAILABLE'
    assert all(step.output_hash for step in current.steps)
    assert repo.db.rows('SELECT * FROM commerce_approvals') == []


def test_project_changes_stop_obsolete_role_tasks(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'blueprint')
    child = service.dispatch_step(ctx, next(s.id for s in plan.steps if s.role == 'product_content'))
    project = service.repo.get_project(plan.project_id)
    service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'Updated'}), project.revision)
    assert service.repo.get_plan(plan.id, project_id=plan.project_id).state == 'STALE'
    assert repo.get(ctx.task_id).cancel_requested
    assert repo.get(child.id).status == 'CANCELLED'


def test_valid_format_with_unconfirmed_facts_does_not_spend_format_correction(workflow):
    service, repo, plan, worker = workflow
    ctx = actor(repo, worker)
    from muse.commerce.errors import CommerceFailure
    candidate = plan.blueprint.model_dump(mode='json')
    candidate['pages'][0]['title'] = 'Unconfirmed title'
    with pytest.raises(CommerceFailure) as failure:
        service.submit(ctx, 'blueprint', {'candidate': candidate}, 'new-facts')
    assert failure.value.public.code == 'FACTS_INCOMPLETE'
    saved = service.repo.get_plan(plan.id, project_id=plan.project_id)
    assert saved.state == 'NEEDS_INPUT'
    assert root_step(saved).correction_attempts == 0
    assert repo.db.rows("SELECT * FROM commerce_artifacts WHERE kind='invalid_submission'") == []


async def test_runtime_structured_submission_uses_original_approval_and_saved_call(workflow):
    service, repo, plan, worker = workflow
    from muse.contracts import ModelEvent
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='submit-once', name='submit_blueprint',
            arguments={'candidate': plan.blueprint.model_dump(mode='json')}))],
        [ModelEvent(type='text', text='Proposal submitted; isolated code verification remains blocked.')],
    ])
    worker.runner.provider = provider
    await worker.run_once()
    root = root_step(plan).task_id
    assert repo.get(root).status == 'WAITING_APPROVAL'
    assert service.repo.get_plan(plan.id, project_id=plan.project_id).steps[0].output_hash is None
    approval = repo.approvals(root)[0]
    repo.decide_approval(approval['id'], True, approval['action_digest'])
    await worker.run_once()
    assert repo.get(root).status == 'SUCCEEDED'
    saved = service.repo.get_plan(plan.id, project_id=plan.project_id)
    assert saved.steps[0].output_hash
    assert len(provider.requests) == 2
    assert len(repo.db.rows("SELECT * FROM commerce_artifacts WHERE kind='commerce_output'")) == 1
    assert repo.db.rows('SELECT * FROM commerce_approvals') == []
    # A successful root tool proposal does not complete an undispatched team.
    current = service.advance(plan.id, saved.revision)
    assert current.state == 'FAILED'
    assert current.error_code == 'MODEL_OUTPUT_INVALID'


def test_connector_token_cannot_enter_snapshots_memory_or_trace(workflow):
    service, repo, plan, worker = workflow
    from pathlib import Path

    from muse.agent.instructions import resource_snapshot
    from muse.config import CommerceConnectorSettings
    from muse.memory.service import MemoryService
    from muse.tasks.trace import task_trace
    worker.settings = worker.settings.model_copy(update={'commerce_connector': CommerceConnectorSettings(
        service_url='http://127.0.0.1:8787', token='service-secret-012345', versions_lock_path='unused.json')})
    project = service.repo.get_project(plan.project_id)
    workspace = repo.workspace(project.workspace_id)
    Path(workspace['path'], 'AGENTS.md').write_text('service-secret-012345', encoding='utf-8')
    snapshot = resource_snapshot(worker.settings, TaskRequest(prompt='Inspect', workspace_id=project.workspace_id, client_request_id='secret-check'), workspace)
    assert 'service-secret-012345' not in str(snapshot)
    with pytest.raises(ValueError):
        MemoryService(repo, worker.settings).upsert(scope='user', title='Preference', content='service-secret-012345')
    repo.add_event(root_step(plan).task_id, 'test_reference', {'content': 'service-secret-012345'})
    assert 'service-secret-012345' not in str(task_trace(repo, worker.settings, root_step(plan).task_id))


async def test_child_context_retains_original_merchant_task_goal(workflow):
    import json
    service, repo, plan, worker = workflow
    manager = actor(repo, worker)
    service.submit(manager, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'goal-blueprint')
    step = next(item for item in plan.steps if item.role == 'site_developer')
    service.dispatch_step(manager, step.id)
    child = actor(repo, worker, 'developer-goal')
    result = await ToolRegistry(child).execute(ToolCall(id='child-goal', name='read_commerce_context'))
    data = json.loads(result.content)
    assert data['task_goal'] == 'Prepare the shop'
    assert data['untrusted_reference'] is True
    assert 'run_command' not in {tool.name for tool in ToolRegistry(child).definitions()}
