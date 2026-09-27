import asyncio
import json
import time

import psutil
import pytest

from muse.artifacts.service import ArtifactService
from muse.contracts import ModelEvent, TaskRequest, ToolCall
from muse.tools.context import ExecutionContext
from test_agent_loop import ScriptedProvider, runtime
from test_workspace_tools import context


async def test_crash_after_durable_write_result_cannot_bypass_verification(tmp_path, monkeypatch):
    provider=ScriptedProvider([[ModelEvent(type="call",call=ToolCall(id="write",name="write_file",arguments={"path":"hello.txt","content":"changed"}))],[ModelEvent(type="text",text="done")]])
    repo,task,worker=runtime(tmp_path,provider)
    original=ExecutionContext.save
    def fail_after_done(ctx):
        if any(c["status"]=="DONE" for c in ctx.repo.calls(ctx.task_id)): raise asyncio.CancelledError()
        original(ctx)
    with monkeypatch.context() as patch:
        patch.setattr(ExecutionContext,"save",fail_after_done)
        with pytest.raises(asyncio.CancelledError): await worker.run_once()
    await worker.run_once()
    assert repo.get(task.id).status=="FAILED"
    assert "verification" in repo.get(task.id).error.lower()
    assert repo.tool_attempts(task.id)==1


async def test_crash_before_waiting_input_transition_preserves_question(tmp_path, monkeypatch):
    provider=ScriptedProvider([[ModelEvent(type="call",call=ToolCall(id="ask",name="ask_user",arguments={"question":"Which folder?"}))],[ModelEvent(type="text",text="Wrongly continued")]])
    repo,task,worker=runtime(tmp_path,provider)
    original=repo.finish
    def crash(*args,**kwargs): raise asyncio.CancelledError()
    with monkeypatch.context() as patch:
        patch.setattr(repo,"finish",crash)
        with pytest.raises(asyncio.CancelledError): await worker.run_once()
    await worker.run_once()
    assert repo.get(task.id).status=="WAITING_INPUT"
    assert repo.get(task.id).result=="Which folder?"
    assert len(provider.requests)==1


async def test_shell_mutation_invalidates_earlier_verification(tmp_path):
    provider=ScriptedProvider([
        [ModelEvent(type="call",call=ToolCall(id="verify",name="verify_command",arguments={"command":"echo checked"}))],
        [ModelEvent(type="call",call=ToolCall(id="write",name="run_command",arguments={"command":"Set-Content hello.txt changed"}))],
        [ModelEvent(type="text",text="done")],
    ])
    repo,task,worker=runtime(tmp_path,provider)
    for _ in range(3):
        await worker.run_once()
        for approval in repo.approvals(task.id):
            if approval["status"]=="PENDING":repo.decide_approval(approval["id"],True,approval["action_digest"])
    assert repo.get(task.id).status=="FAILED"
    assert "verification" in repo.get(task.id).error.lower()


async def test_parent_exit_does_not_leave_orphan_holding_output_pipe(tmp_path):
    provider=ScriptedProvider([[ModelEvent(type="call",call=ToolCall(id="run",name="run_command",arguments={"command":"python parent.py","timeout_seconds":3}))],[ModelEvent(type="text",text="done")]])
    repo,task,worker=runtime(tmp_path,provider)
    root=tmp_path/"project"
    (root/"parent.py").write_text("import subprocess,sys,pathlib\np=subprocess.Popen([sys.executable,'child.py'])\npathlib.Path('child.pid').write_text(str(p.pid))\n")
    (root/"child.py").write_text("import time\ntime.sleep(6)\n")
    await worker.run_once();approval=repo.approvals(task.id)[0];repo.decide_approval(approval["id"],True,approval["action_digest"])
    start=time.monotonic();await worker.run_once();elapsed=time.monotonic()-start
    child=int((root/"child.pid").read_text())
    assert elapsed<5, f"orphan held pipe for {elapsed:.2f}s"
    assert not psutil.pid_exists(child)


def test_source_title_and_url_are_redacted_before_storage(tmp_path):
    repo,ctx,_=context(tmp_path)
    fake="sk-proj-syntheticsecret1234567890"
    ArtifactService(ctx).source("https://example.com/?api_key="+fake,fake,"normal body")
    assert fake not in json.dumps(repo.db.rows("SELECT * FROM sources"))
    assert fake not in json.dumps(repo.events(ctx.task_id))


async def test_navigation_pins_validated_address_and_avoids_proxy_dns():
    from muse.tools.browser import URLPolicy, BrowserTool
    async def resolver(host):return ["1.1.1.1"]
    policy=URLPolicy(resolver=resolver)
    plan=await policy.connection_plan("https://public.example/path")
    assert plan["hostname"]=="public.example" and plan["address"]=="1.1.1.1"
    options=BrowserTool.launch_options(plan)
    assert "proxy" not in options
    assert any("MAP public.example 1.1.1.1" in arg for arg in options["args"])


async def test_split_stream_secret_is_not_reconstructed_from_events(tmp_path):
    provider=ScriptedProvider([])
    repo,task,worker=runtime(tmp_path,provider)
    secret=worker.settings.access_token.get_secret_value()
    provider.turns=iter([[ModelEvent(type="text",text="word "*19+secret[:5]),ModelEvent(type="text",text=secret[5:]+" suffix")]])
    await worker.run_once()
    streamed="".join(e["payload"]["text"] for e in repo.events(task.id) if e["type"]=="text_delta")
    assert secret not in streamed


async def test_crash_after_artifact_result_recovers_deliverable(tmp_path, monkeypatch):
    provider=ScriptedProvider([
        [ModelEvent(type="call",call=ToolCall(id="artifact",name="save_artifact",arguments={"name":"report.md","content":"Durable report"}))],
        [ModelEvent(type="text",text="saved")],
    ])
    repo,task,worker=runtime(tmp_path,provider)
    original=ExecutionContext.save
    def crash(ctx):
        if any(c["status"]=="DONE" for c in ctx.repo.calls(ctx.task_id)):raise asyncio.CancelledError()
        original(ctx)
    with monkeypatch.context() as patch:
        patch.setattr(ExecutionContext,"save",crash)
        with pytest.raises(asyncio.CancelledError):await worker.run_once()
    await worker.run_once()
    assert repo.get(task.id).checkpoint["artifact_ids"]
    assert repo.tool_attempts(task.id)==1


async def test_absent_provider_usage_is_marked_incomplete(tmp_path):
    provider=ScriptedProvider([[ModelEvent(type="text",text="done")]])
    repo,task,worker=runtime(tmp_path,provider)
    await worker.run_once()
    assert repo.get(task.id).checkpoint["usage"]["complete"] is False


async def test_dns_rebinding_between_validation_and_pinning_is_rejected():
    from muse.tools.browser import URLPolicy
    answers=iter([["1.1.1.1"],["127.0.0.1"]])
    async def resolver(host):return next(answers)
    with pytest.raises(PermissionError):
        await URLPolicy(resolver=resolver).connection_plan("https://public.example/")
