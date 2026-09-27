import hashlib

import pytest

from muse.contracts import ToolCall
from muse.tools.files import FileTools
from test_workspace_tools import context


async def test_written_file_can_be_verified_after_crash_without_repeating_write(tmp_path):
    repo, ctx, _ = context(tmp_path)
    files = FileTools(ctx)
    call = ToolCall(id="write", name="write_file", arguments={"path": "new.txt", "content": "committed"})
    repo.prepare_call(ctx.task_id,ctx.owner,ctx.epoch,call.id,call.name,call.arguments,"write")
    repo.begin_call(ctx.task_id,ctx.owner,ctx.epoch,call.id)
    await files.write_file(call.arguments,call.id)
    repo.abandon(ctx.task_id,ctx.owner,ctx.epoch)
    assert repo.get(ctx.task_id).status == "INTERRUPTED"
    assert files.reconcile(call.id, expected_revision=repo.get(ctx.task_id).revision)["verified"] is True
    assert repo.calls(ctx.task_id)[0]["status"] == "DONE"
    assert repo.get(ctx.task_id).checkpoint["writes"] == 1
    assert (ctx.workspace / "new.txt").read_text() == "committed"


async def test_unverifiable_file_stays_interrupted(tmp_path):
    repo, ctx, _ = context(tmp_path)
    files = FileTools(ctx)
    repo.prepare_call(ctx.task_id,ctx.owner,ctx.epoch,"write","write_file",{"path":"new.txt","content":"planned"},"write")
    repo.begin_call(ctx.task_id,ctx.owner,ctx.epoch,"write")
    await files.write_file({"path":"new.txt","content":"planned"},"write")
    repo.abandon(ctx.task_id,ctx.owner,ctx.epoch)
    (ctx.workspace / "new.txt").write_text("changed by the user")
    with pytest.raises(ValueError, match="cannot be verified"):
        files.reconcile("write", expected_revision=repo.get(ctx.task_id).revision)
    assert repo.get(ctx.task_id).status == "INTERRUPTED"
    assert repo.calls(ctx.task_id)[0]["status"] == "UNKNOWN"
