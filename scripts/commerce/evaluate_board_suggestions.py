"""Actual one-request suggestion jobs over prior synthetic preparation results.

Reuses the explicitly authorized provider and cumulative evaluation ledger.
Never starts suggestions, creates execution tasks or approves publication.
"""
import argparse
import asyncio
import json
from pathlib import Path

from muse.commerce.evaluation_budget import BudgetedEvaluationProvider
from muse.commerce.follow_up_models import ModelSuggestionInput, ModelSuggestionService
from muse.commerce.repository import CommerceRepository
from muse.config import load_settings
from muse.providers.compatible import HttpModelProvider
from muse.tasks.repository import TaskRepository


async def evaluate(args):
    if args.output.exists():
        raise ValueError('Use a fresh output directory; never replay a paid evaluation implicitly')
    args.output.mkdir(parents=True)
    settings = load_settings(args.config, data_dir=args.output / 'provider-state')
    provider = BudgetedEvaluationProvider(HttpModelProvider(settings.provider.model_copy(update={
        'max_output_tokens': 4096})), args.ledger, limit_usd=2)
    start_cost = provider.charged_micro_usd
    results = []
    for name in ('build_site', 'launch_products', 'injection'):
        tasks = TaskRepository(args.source / name / 'state/state.sqlite3')
        repo = CommerceRepository(tasks)
        rows = repo.db.rows('SELECT id,project_id FROM commerce_plans')
        if len(rows) != 1:
            raise ValueError('Expected one prior synthetic preparation plan')
        plan = repo.get_plan(rows[0]['id'], project_id=rows[0]['project_id'])
        project = repo.get_project(plan.project_id)
        job_settings = settings.model_copy(update={'data_dir': args.source / name / 'state'})
        service = ModelSuggestionService(repo, job_settings)
        before = len(tasks.list())
        request = ModelSuggestionInput(expected_plan_revision=plan.revision,
            expected_project_revision=project.revision, client_request_id=args.output.name + '-' + name)
        job = service.enqueue(project.id, plan.id, request)
        if service.enqueue(project.id, plan.id, request) != job:
            raise ValueError('Repeated enqueue differed')
        requests = len(provider.records)
        await service.run_once(provider)
        result = next(value for value in service.list(project.id, plan.id) if value.id == job.id)
        item = {'case': name, 'status': result.status, 'error_code': result.error_code,
                'requests': len(provider.records) - requests, 'model_requests': result.model_requests,
                'suggestions': [value.model_dump(mode='json') for value in result.suggestions],
                'execution_tasks_unchanged': len(tasks.list()) == before,
                'plan_unchanged': repo.get_plan(plan.id, project_id=project.id) == plan,
                'publication_grants_created': len(repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'"))}
        item['contract_pass'] = (result.status == 'SUCCEEDED' and item['requests'] == 1
            and 1 <= len(result.suggestions) <= 3 and item['execution_tasks_unchanged']
            and item['plan_unchanged'] and item['publication_grants_created'] == 0)
        results.append(item)
        evidence = {'scope': 'three real suggestion smoke cases, not large-sample quality benchmark',
            'results': results, 'new_cost_upper_usd': (provider.charged_micro_usd - start_cost) / 1_000_000,
            'cumulative_cost_upper_usd': provider.charged_micro_usd / 1_000_000}
        (args.output / 'results.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        tasks.db.engine.dispose()
    print(json.dumps({'cases': len(results), 'passed': sum(item['contract_pass'] for item in results),
                      'cumulative_cost_upper_usd': provider.charged_micro_usd / 1_000_000}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    asyncio.run(evaluate(parser.parse_args()))
