"""Atomic SQLite-only receipts, never permission to retry a WordPress write."""
import json

from sqlalchemy import text

from muse.commerce.models import CommercePlan
from muse.commerce.repository import digest, encode
from muse.commerce.roles import ROLE_TOOLS
from muse.contracts import ToolResult

MANAGED_TOOLS = {'submit_blueprint', 'submit_product_drafts', 'dispatch_commerce_step', 'request_commerce_review',
                 'write_theme_file', 'seal_theme_code'}


def save_managed_receipt(conn, ctx, call_id, *, error_code=None):
    call = conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task AND id=:call AND status='EXECUTING'"),
                        {'task': ctx.task_id, 'call': call_id}).mappings().first()
    if not call or call['name'] not in MANAGED_TOOLS:
        return  # Service-level proposal tests have no runtime call to acknowledge.
    binding = ctx.cp['commerce']
    value = {'task_id': ctx.task_id, 'call_id': call_id, 'plan_id': binding['plan_id'], 'step_id': binding['step_id'],
             'action_digest': call['digest'], 'arguments_hash': digest(json.loads(call['arguments'])),
             'error_code': error_code}
    conn.execute(text("INSERT OR IGNORE INTO commerce_artifacts VALUES(:id,:project,:plan,'managed_call_receipt',:digest,:data)"),
                 {'id': digest([ctx.task_id, 'managed-call', call_id]), 'project': binding['project_id'],
                  'plan': binding['plan_id'], 'digest': digest(value), 'data': encode(value)})


def reconcile_managed_calls(runtime, conn, task_id, now):
    task = runtime._task(conn, task_id)
    binding = json.loads(task['checkpoint']).get('commerce', {})
    row = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
                       {'id': binding.get('plan_id'), 'project': binding.get('project_id')}).scalar()
    if not row:
        return
    plan = CommercePlan.model_validate_json(row)
    step = next((step for step in plan.steps if step.id == binding.get('step_id') and step.task_id == task_id), None)
    if step is None:
        return
    calls = conn.execute(text("SELECT * FROM tool_calls WHERE task_id=:task AND status='EXECUTING'"), {'task': task_id}).mappings().all()
    for call in calls:
        if call['name'] not in MANAGED_TOOLS or call['name'] not in ROLE_TOOLS[step.role]:
            continue
        record = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='managed_call_receipt'"),
            {'id': digest([task_id, 'managed-call', call['id']]), 'project': plan.project_id, 'plan': plan.id}).mappings().first()
        values = {'task': task_id, 'call': call['id'], 'now': now}
        if record is None:
            # Every managed handler commits its effect AND receipt in one transaction.
            # No receipt means that transaction never committed. Ordinary/external tools
            # are deliberately excluded and keep the existing UNKNOWN safety boundary.
            conn.execute(text("UPDATE tool_calls SET status='PREPARED',updated_at=:now WHERE task_id=:task AND id=:call"), values)
            continue
        try:
            receipt = json.loads(record['data'])
            if (digest(receipt) != record['digest'] or receipt['task_id'] != task_id or receipt['call_id'] != call['id']
                    or receipt['plan_id'] != plan.id or receipt['step_id'] != step.id
                    or receipt['action_digest'] != call['digest'] or receipt['arguments_hash'] != digest(json.loads(call['arguments']))):
                continue
            result = ToolResult(call_id=call['id'], status='error' if receipt['error_code'] else 'success',
                error_code=receipt['error_code'], content='Recovered atomic Commerce database receipt.',
                metadata={'reconciled': True, 'receipt_hash': record['digest'], 'site_verified': False, 'published': False}).model_dump()
        except (KeyError, TypeError, ValueError):
            continue  # Corrupt evidence remains UNKNOWN; never infer success.
        conn.execute(text('UPDATE tool_calls SET status=:status,result=:result,updated_at=:now WHERE task_id=:task AND id=:call'),
                     {**values, 'status': 'FAILED' if receipt['error_code'] else 'DONE', 'result': encode(result)})
        runtime._event(conn, task_id, 'tool_result', {'call_id': call['id'], **result}, now)
