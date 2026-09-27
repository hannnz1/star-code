import importlib.util
import asyncio

import pytest

from test_task_lifecycle import make_repo, create


def context(tmp_path):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    claim = repo.claim_next("worker", ttl=120)  # Direct tool tests have no Worker's heartbeat.
    assert importlib.util.find_spec("muse.tools") is not None, "Workspace tools are missing"
    from muse.config import load_settings
    from muse.tools.context import ExecutionContext
    from muse.tools.registry import ToolRegistry
    settings = load_settings(data_dir=tmp_path / "data", require_provider=False)
    ctx = ExecutionContext(settings, repo, claim, "worker")
    return repo, ctx, ToolRegistry(ctx)


async def test_write_read_edit_and_conflict_safe_rewind(tmp_path):
    from muse.contracts import ToolCall
    repo, ctx, tools = context(tmp_path)
    written = await tools.execute(ToolCall(id="w", name="write_file", arguments={"path": "hello.txt", "content": "first"}))
    assert written.status == "success"
    assert (ctx.workspace / "hello.txt").read_text(encoding="utf-8") == "first"
    read = await tools.execute(ToolCall(id="r", name="read_file", arguments={"path": "hello.txt"}))
    assert "first" in read.content
    edit = await tools.execute(ToolCall(id="e", name="edit_file", arguments={"path": "hello.txt", "old_text": "first", "new_text": "second"}))
    assert edit.status == "success"
    (ctx.workspace / "hello.txt").write_text("external change", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        tools.files.rewind(ctx.task_id, "e")
    assert (ctx.workspace / "hello.txt").read_text(encoding="utf-8") == "external change"


async def test_repeated_completed_write_returns_saved_result(tmp_path):
    from muse.contracts import ToolCall
    repo, ctx, tools = context(tmp_path)
    call = ToolCall(id="w", name="write_file", arguments={"path": "hello.txt", "content": "first"})
    await tools.execute(call)
    (ctx.workspace / "hello.txt").write_text("manual", encoding="utf-8")
    again = await tools.execute(call)
    assert again.status == "success"
    assert (ctx.workspace / "hello.txt").read_text(encoding="utf-8") == "manual"
    assert len([e for e in repo.events(ctx.task_id) if e["type"] == "tool_started"]) == 1


async def test_denied_path_never_changes_outside_file(tmp_path):
    from muse.contracts import ToolCall
    repo, ctx, tools = context(tmp_path)
    external = tmp_path / "outside.txt"
    external.write_text("sentinel", encoding="utf-8")
    result = await tools.execute(ToolCall(id="bad", name="write_file", arguments={"path": str(external), "content": "overwrite"}))
    assert result.status == "denied"
    assert external.read_text(encoding="utf-8") == "sentinel"


async def test_approval_is_bound_to_digest_and_cannot_execute_twice(tmp_path):
    from muse.contracts import ToolCall
    repo, ctx, tools = context(tmp_path)
    from muse.tools.context import ApprovalRequired, ExecutionContext
    from muse.tools.registry import ToolRegistry
    call = ToolCall(id="shell", name="run_command", arguments={"command": "echo hello", "timeout_seconds": 10})
    with pytest.raises(ApprovalRequired):
        await tools.execute(call)
    approval = repo.approvals(ctx.task_id)[0]
    with pytest.raises(ValueError, match="digest"):
        repo.decide_approval(approval["id"], True, "wrong")
    repo.decide_approval(approval["id"], True, approval["action_digest"])
    claim = repo.claim_next("worker")
    resumed = ExecutionContext(ctx.settings, repo, claim, "worker")
    registry = ToolRegistry(resumed)
    result = await registry.execute(call)
    assert result.status == "success" and "hello" in result.content
    assert (await registry.execute(call)).content == result.content
    assert len([e for e in repo.events(ctx.task_id) if e["type"] == "tool_started"]) == 1


async def test_refused_approval_does_not_dispatch_command(tmp_path):
    from muse.contracts import ToolCall
    repo, ctx, tools = context(tmp_path)
    from muse.tools.context import ApprovalRequired, ExecutionContext
    from muse.tools.registry import ToolRegistry
    call = ToolCall(id="shell", name="run_command", arguments={"command": "echo hello"})
    with pytest.raises(ApprovalRequired):
        await tools.execute(call)
    approval = repo.approvals(ctx.task_id)[0]
    repo.decide_approval(approval["id"], False, approval["action_digest"])
    claim = repo.claim_next("worker")
    result = await ToolRegistry(ExecutionContext(ctx.settings, repo, claim, "worker")).execute(call)
    assert result.status == "denied"
    assert not [e for e in repo.events(ctx.task_id) if e["type"] == "tool_started"]


async def test_unknown_tool_and_bad_schema_do_not_execute(tmp_path):
    from muse.contracts import ToolCall
    repo, ctx, tools = context(tmp_path)
    unknown = await tools.execute(ToolCall(id="u", name="not_a_tool"))
    bad = await tools.execute(ToolCall(id="b", name="write_file", arguments={"path": "x"}))
    assert unknown.status == "error" and bad.status == "error"
    assert not list(ctx.workspace.iterdir())


async def test_cancelled_task_cannot_start_next_tool(tmp_path):
    from muse.contracts import ToolCall
    repo, ctx, tools = context(tmp_path)
    from muse.tools.context import TaskControl
    task = repo.get(ctx.task_id)
    repo.control(task.id, "cancel", expected_revision=task.revision)
    with pytest.raises(TaskControl):
        await tools.execute(ToolCall(id="w", name="write_file", arguments={"path": "x", "content": "no"}))
    assert not (ctx.workspace / "x").exists()
async def test_recursive_glob_includes_files_at_workspace_root(tmp_path):
    import json
    from muse.tools.files import FileTools
    _, ctx, root = context(tmp_path)
    (ctx.workspace / "root.txt").write_text("root")
    files = FileTools(ctx)
    assert "root.txt" in json.loads(await files.list_files({"pattern": "**/*.txt"}, "list"))["paths"]
