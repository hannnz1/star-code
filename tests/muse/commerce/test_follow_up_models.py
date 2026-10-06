import json

import pytest

from muse.commerce.follow_up_models import ModelSuggestionInput, ModelSuggestionService
from muse.commerce.follow_ups import FollowUpService
from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider


def setup(workflow):
    service, tasks, plan, worker = workflow
    plan = service.repo.save_plan(plan.model_copy(update={'state': 'SUCCEEDED'}), plan.revision)
    project = service.repo.get_project(plan.project_id)
    suggestions = ModelSuggestionService(service.repo, worker.settings)
    request = ModelSuggestionInput(expected_plan_revision=plan.revision, expected_project_revision=project.revision,
                                   client_request_id='model-suggestions')
    return service, tasks, plan, worker, project, suggestions, request


async def test_model_suggestions_use_one_request_no_tools_and_bind_context(workflow):
    service, tasks, plan, worker, project, suggestions, request = setup(workflow)
    job = suggestions.enqueue(project.id, plan.id, request)
    assert suggestions.enqueue(project.id, plan.id, request) == job
    provider = ScriptedProvider([[ModelEvent(type='text', text=json.dumps({'suggestions': [
        {'title': 'Improve navigation', 'kind': 'build_site', 'prompt': 'Improve navigation, verify and review.'}]})),
        ModelEvent(type='usage', usage={'input_tokens': 50, 'output_tokens': 20})]])
    assert await suggestions.run_once(provider)
    assert not await suggestions.run_once(provider)
    assert len(provider.requests) == 1
    context = json.loads(provider.requests[0][1]['content'])
    assert context['brand_name'] == 'Cup Store' and context['plan_revision'] == plan.revision
    assert 'provider-secret' not in str(provider.requests) and 'archive_base64' not in str(provider.requests)
    result = suggestions.list(project.id, plan.id)[0]
    assert result.status == 'SUCCEEDED' and result.model_requests == 1 and result.usage['input_tokens'] == 50
    items = FollowUpService(service.repo, service).list(project.id, plan.id)
    assert items[-1].title == 'Improve navigation'
    assert '待审查' in items[-1].evidence[0] and len(tasks.list()) == 1
    service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'Minimal'}), project.revision)
    assert FollowUpService(service.repo, service).list(project.id, plan.id) == []


@pytest.mark.parametrize('events', [
    [ModelEvent(type='text', text='not json')],
    [ModelEvent(type='text', text='{"suggestions":[{"title":"bad","kind":"publish_live","prompt":"publish"}]}')],
    [ModelEvent(type='call', call=ToolCall(id='forbidden', name='run_command', arguments={'command': 'anything'}))],
])
async def test_invalid_model_output_never_creates_execution_tasks(workflow, events):
    service, tasks, plan, worker, project, suggestions, request = setup(workflow)
    suggestions.enqueue(project.id, plan.id, request)
    provider = ScriptedProvider([events])
    assert await suggestions.run_once(provider)
    result = suggestions.list(project.id, plan.id)[0]
    assert result.status == 'FAILED' and result.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.model_requests == 1 and result.suggestions == []
    assert len(tasks.list()) == 1


async def test_stale_input_and_interrupted_request_are_not_automatically_recharged(workflow):
    service, tasks, plan, worker, project, suggestions, request = setup(workflow)
    job = suggestions.enqueue(project.id, plan.id, request)
    with service.repo.db.transaction() as conn:
        suggestions._save(conn, job.model_copy(update={'status': 'RUNNING', 'model_requests': 1, 'lease_until': 0}))
    provider = ScriptedProvider([])
    assert not await suggestions.run_once(provider)
    assert suggestions.list(project.id, plan.id)[0].status == 'INTERRUPTED'
    assert provider.requests == []
    next_job = suggestions.enqueue(project.id, plan.id, request.model_copy(update={'client_request_id': 'stale-job'}))
    service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'Minimal'}), project.revision)
    assert await suggestions.run_once(provider)
    result = next(item for item in suggestions.list(project.id, plan.id) if item.id == next_job.id)
    assert result.status == 'FAILED' and result.model_requests == 0 and provider.requests == []


async def test_model_receives_only_bounded_trusted_theme_diff_and_metadata(workflow):
    from tests.muse.commerce.test_code_integration import seal
    service, tasks, plan, worker = workflow
    plan = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    project = service.repo.get_project(plan.project_id)
    suggestions = ModelSuggestionService(service.repo, worker.settings)
    request = ModelSuggestionInput(expected_plan_revision=plan.revision, expected_project_revision=project.revision,
                                  client_request_id='diff-suggestion')
    suggestions.enqueue(project.id, plan.id, request)
    provider = ScriptedProvider([[ModelEvent(type='text', text=json.dumps({'suggestions': [
        {'title': 'Review CSS', 'kind': 'build_site', 'prompt': 'Review the changed CSS and verify.'}]}))]])
    await suggestions.run_once(provider)
    context = json.loads(provider.requests[0][1]['content'])
    assert '+body { color: #111; }' in context['theme_diff']
    assert len(context['theme_diff']) <= 8000 and context['theme_diff_untrusted']
    assert 'provider-secret' not in str(provider.requests) and 'archive_base64' not in str(provider.requests)
