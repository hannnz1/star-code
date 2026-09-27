import json

from muse.contracts import ToolCall, ToolDefinition, ToolResult
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry
from test_agent_loop import runtime, ScriptedProvider


async def test_nested_extension_results_are_redacted_before_persistence(tmp_path):
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    claimed = repo.claim_next('redaction')
    ctx = ExecutionContext(worker.settings, repo, claimed, 'redaction')
    registry = ToolRegistry(ctx)
    secret = worker.settings.access_token.get_secret_value()

    async def echo(args, call_id):
        return ToolResult(call_id=call_id, content='response ' + secret,
                          metadata={'nested': [{'description': secret, 'count': 7}]})

    registry.register(ToolDefinition(name='fixture', description='fixture', parameters={'type': 'object'}), echo)
    await registry.execute(ToolCall(id='fixture', name='fixture', arguments={}))
    result = repo.calls(task.id)[0]['result']
    assert secret not in json.dumps(result)
    assert result['metadata']['nested'][0]['count'] == 7
