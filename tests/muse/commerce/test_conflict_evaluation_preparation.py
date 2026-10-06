import json

from muse.contracts import ToolCall
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry
from scripts.commerce.evaluate_conflict_repair import prepare_case
from scripts.commerce.verify_linux_workflow import prepare_roles


async def test_conflict_eval_freezes_three_inputs_and_exposes_exact_user_choice(workflow, tmp_path):
    service, tasks, plan, worker = workflow
    prepare_roles(service, tasks, worker.settings, plan)
    root = tmp_path / 'explicit-choice'
    settings = worker.settings.model_copy(update={'data_dir': root / 'state'})
    prepared, repo, _, _manager, _repair, developer_id, expected = prepare_case(
        settings, worker.settings.data_dir / 'state.sqlite3', root, ambiguous=False)
    child = prepared.claim_next('offline-inspector')
    assert child.id == developer_id
    ctx = ExecutionContext(settings, prepared, child, 'offline-inspector', enforce_budgets=True)
    registry = ToolRegistry(ctx)
    context = json.loads((await registry.execute(ToolCall(id='context', name='read_commerce_context'))).content)
    assert 'current color #111' in context['task_goal'] and 'candidate padding 16px' in context['task_goal']
    inputs = json.loads((await registry.execute(ToolCall(id='conflict', name='read_conflict_file', arguments={'name': 'style.css'}))).content)
    assert 'padding: 8px' in inputs['current'] and 'color: #222' in inputs['candidate']
    assert '.benchmark-choice' not in inputs['base']
    assert 'color: #111; padding: 16px' in expected
    assert not repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'")


