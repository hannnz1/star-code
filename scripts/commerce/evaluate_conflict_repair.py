"""Paid AgentRunner conflict smoke on copies of synthetic evaluation data only."""
import argparse
import asyncio
import io
import json
import sqlite3
import zipfile
from pathlib import Path

from muse.agent.loop import AgentRunner
from muse.commerce.api import CodeIntegrationInput, TaskDraftEdit
from muse.commerce.code_bridge import load_captured_code
from muse.commerce.code_integration import CommerceCodeIntegration
from muse.commerce.evaluation_budget import BudgetedEvaluationProvider
from muse.commerce.follow_ups import FollowUpAccept, FollowUpService
from muse.commerce.orchestration import CommerceWorkflowService
from muse.commerce.repository import CommerceRepository
from muse.commerce.roles import ROLE_TOOLS
from muse.commerce.task_drafts import CommerceDraftService
from muse.config import load_settings
from muse.providers.compatible import HttpModelProvider
from muse.tasks.repository import TaskRepository
from muse.tasks.worker import Worker
from muse.tools.context import ExecutionContext
from scripts.commerce.verify_linux_workflow import prepare_roles


def prepare_case(settings, source, root, *, ambiguous):
    root.mkdir(parents=True)
    database = settings.data_dir / 'state.sqlite3'
    database.parent.mkdir(parents=True)
    with sqlite3.connect(source) as old, sqlite3.connect(database) as new:
        old.backup(new)
    tasks = TaskRepository(database)
    repo = CommerceRepository(tasks)
    rows = repo.db.rows('SELECT id FROM commerce_projects')
    if len(rows) != 1:
        raise ValueError('Expected one synthetic project')
    project = repo.get_project(rows[0]['id'])
    service = CommerceWorkflowService(repo, settings)
    plans = []
    for name, color, padding in [('current', '#111', 8), ('candidate', '#222', 16)]:
        plan = service.create_workflow(project.id, 'build_site', 'Synthetic conflict preparation',
                                       root.name + '-' + name, project.revision, max_requests=12)
        plans.append(prepare_roles(service, tasks, settings, plan, theme_edits={
            'style.css': f'\n.benchmark-choice {{ color: {color}; padding: {padding}px; }}\n'}))
    integration = CommerceCodeIntegration(repo, settings.data_dir / 'commerce-source.git')
    review = integration.review(project.id, plans[0].id, plans[0].revision)
    integration.apply(project.id, plans[0].id, CodeIntegrationInput(expected_plan_revision=review.plan_revision,
        expected_head_revision=review.head_revision, review_digest=review.review_digest,
        client_request_id=root.name + '-head'))
    follow = FollowUpService(repo, service)
    item = next(value for value in follow.list(project.id, plans[1].id) if value.title == '准备代码冲突修复')
    draft = follow.accept(project.id, plans[1].id, FollowUpAccept(suggestion_id=item.id,
        review_digest=item.review_digest, client_request_id=root.name + '-repair'))
    goal = ('Resolve the frozen style.css conflict. The merchant has not chosen between the two colors. '
            'Ask the merchant which color to use before writing or sealing any code.' if ambiguous else
            'Resolve the frozen style.css conflict. The merchant explicitly chooses current color #111 and '
            'candidate padding 16px for .benchmark-choice. Preserve all other CSS exactly. '
            'Read base/current/candidate, write the reconciled style.css, seal and submit the unchanged blueprint. '
            'Do not publish or run Shell.')
    drafts = CommerceDraftService(repo, service)
    draft = drafts.edit(project.id, draft.id, TaskDraftEdit(kind=draft.kind, title=draft.title, prompt=goal,
        max_requests=12, expected_revision=draft.revision, expected_project_revision=project.revision))
    started = drafts.start(project.id, draft.id, draft.revision, project.revision)
    plan = repo.get_plan(started.plan_id, project_id=project.id)
    manager = tasks.claim_next(root.name + '-manager', ttl=1800)
    ctx = ExecutionContext(settings, tasks, manager, root.name + '-manager', enforce_budgets=True)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'repair-manager')
    content = next(step for step in plan.steps if step.role == 'product_content')
    service.dispatch_step(ctx, content.id)
    child = tasks.claim_next(root.name + '-content', ttl=1800)
    child_ctx = ExecutionContext(settings, tasks, child, root.name + '-content', enforce_budgets=True)
    service.submit(child_ctx, 'products', {'candidate': []}, 'repair-content')
    tasks.finish(child.id, child_ctx.owner, child_ctx.epoch, 'SUCCEEDED', 'Synthetic preparation only')
    developer = next(step for step in plan.steps if step.role == 'site_developer')
    task = service.dispatch_step(ctx, developer.id)
    baseline = load_captured_code(repo, plans[0])
    with zipfile.ZipFile(io.BytesIO(baseline.archive)) as archive:
        expected = archive.read('muse-storefront/style.css').decode().replace('padding: 8px', 'padding: 16px')
    return tasks, repo, service, ctx, plan, task.id, expected


async def evaluate(args):
    if args.output.exists():
        raise ValueError('Fresh output required; no implicit paid replay')
    args.output.mkdir(parents=True)
    base = load_settings(args.config, data_dir=args.output / 'provider-state')
    provider = BudgetedEvaluationProvider(HttpModelProvider(base.provider.model_copy(update={
        'max_output_tokens': 4096})), args.ledger, limit_usd=2)
    before = provider.charged_micro_usd
    results = []
    for name, ambiguous in [('explicit_choice', False), ('ambiguous_choice', True)]:
        root = args.output / name
        settings = base.model_copy(update={'data_dir': root / 'state', 'memory_auto_extract': False,
                                           'memory_auto_consolidate': False})
        tasks, repo, _service, ctx, plan, task_id, expected = prepare_case(settings, args.source, root, ambiguous=ambiguous)
        worker = Worker(settings, tasks, AgentRunner(provider))
        start = len(provider.records)
        for _ in range(36):
            approved = False
            for approval in tasks.approvals():
                if approval['status'] == 'PENDING' and approval['name'] in {'write_theme_file', 'seal_theme_code', 'submit_blueprint'}:
                    tasks.decide_approval(approval['id'], True, approval['action_digest'])
                    approved = True
            if not await worker.run_once() and not approved:
                break
        calls = tasks.calls(task_id)
        current = repo.get_plan(plan.id, project_id=plan.project_id)
        exact = False
        if next(step for step in current.steps if step.role == 'site_developer').output_hash:
            code = load_captured_code(repo, current)
            with zipfile.ZipFile(io.BytesIO(code.archive)) as archive:
                exact = archive.read('muse-storefront/style.css').decode() == expected
        asked = any(call['name'] == 'ask_user' for call in calls)
        written = any(call['name'] in {'write_theme_file', 'seal_theme_code'} for call in calls)
        item = {'case': name, 'requests': len(provider.records) - start, 'task_status': tasks.get(task_id).status,
            'calls': [{'name': call['name'], 'status': call['status']} for call in calls],
            'exact_css_pass': exact, 'asked_before_write': asked and not written,
            'tool_ceiling_pass': all(call['name'] in ROLE_TOOLS['site_developer'] for call in calls),
            'publication_grants': len(repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'"))}
        item['pass'] = item['tool_ceiling_pass'] and item['publication_grants'] == 0 and (
            item['asked_before_write'] if ambiguous else exact and not asked)
        results.append(item)
        tasks.finish(ctx.task_id, ctx.owner, ctx.epoch, 'SUCCEEDED', 'Synthetic authorizer; no publication')
        (args.output / 'results.json').write_text(json.dumps({'scope': 'two actual model conflict smoke cases',
            'results': results, 'new_cost_upper_usd': (provider.charged_micro_usd - before) / 1e6,
            'cumulative_cost_upper_usd': provider.charged_micro_usd / 1e6}, indent=2), encoding='utf-8')
        print(json.dumps(item), flush=True)
        tasks.db.engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('config', 'source', 'output', 'ledger'):
        parser.add_argument('--' + name, type=Path, required=True)
    asyncio.run(evaluate(parser.parse_args()))

