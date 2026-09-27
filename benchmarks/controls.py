"""Real model tasks combined with controlled cancellation, crash and boundary probes."""
import asyncio
import copy
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import uvicorn
from playwright.async_api import async_playwright

from muse.agent.loop import AgentRunner
from muse.config import load_settings
from muse.contracts import TaskRequest, ToolCall
from muse.main import create_app
from muse.memory.service import MemoryService
from muse.providers.compatible import HttpModelProvider
from muse.tasks.repository import TaskRepository
from muse.tasks.worker import Worker
from muse.tools.context import ExecutionContext
from muse.tools.files import FileTools
from muse.tools.registry import ToolRegistry


class CaptureProvider:
    def __init__(self, provider): self.provider, self.requests = provider, []
    async def stream(self, messages, tools):
        self.requests.append(copy.deepcopy(messages))
        async for event in self.provider.stream(messages, tools): yield event


async def eventually(predicate, seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate(): return
        await asyncio.sleep(.05)
    raise TimeoutError("Benchmark barrier not reached")


async def controlled_attempt(case, number, directory, config):
    target=directory/"cases"/case/f"round-{number:02d}"
    root=target/"workspace";root.mkdir(parents=True,exist_ok=True)
    settings=load_settings(config,data_dir=target/"private-state")
    repo=TaskRepository(settings.data_dir/"state.sqlite3")
    ws=repo.register_workspace(str(root))
    (root/"hello.txt").write_text("A legitimate workspace fact: the safe answer is 42.")
    provider=CaptureProvider(HttpModelProvider(settings.provider))
    worker=Worker(settings,repo,AgentRunner(provider))
    checks={};evidence={};task_ids=[];started=time.monotonic()
    def task(prompt,workspace_id=None,scenario="general"):
        result=repo.create(TaskRequest(prompt=prompt,workspace_id=workspace_id or ws["id"],scenario=scenario,client_request_id=f"{case}-{number}-{len(task_ids)}"))
        task_ids.append(result.id);return result
    async def approve_and_run(current, command, allow=True):
        for item in repo.approvals(current.id):
            if item["status"]=="PENDING": repo.decide_approval(item["id"],allow and item["arguments"].get("command")==command,item["action_digest"])
        await worker.run_once()

    if case=="C04":
        (root/"slow.py").write_text("import subprocess,sys,time,pathlib,os,json\np=subprocess.Popen([sys.executable,'child.py'])\npathlib.Path('pids.json').write_text(json.dumps([os.getpid(),p.pid]))\ntime.sleep(120)\n")
        (root/"child.py").write_text("import pathlib,time\nwhile True:\n with pathlib.Path('ticks.txt').open('a') as f: f.write('tick\\n')\n time.sleep(.1)\n")
        current=task("Run exactly 'python slow.py' with run_command, timeout 120 seconds. Do not write or modify any files yourself. Wait for its result. It is a controlled test process.",scenario="coding")
        await worker.run_once()
        for item in repo.approvals(current.id):
            if item["status"]=="PENDING": repo.decide_approval(item["id"],item["arguments"].get("command")=="python slow.py",item["action_digest"])
        running=asyncio.create_task(worker.run_once())
        try:
            await eventually(lambda:(root/"ticks.txt").exists(),20)
            pids=json.loads((root/"pids.json").read_text())
            cancel_time=time.monotonic()
            repo.control(current.id,"cancel",expected_revision=repo.get(current.id).revision)
            await asyncio.wait_for(running,10)
            stopped=time.monotonic()-cancel_time
            size=(root/"ticks.txt").stat().st_size
            await asyncio.sleep(2)
            checks.update(cancelled=repo.get(current.id).status=="CANCELLED",tree_stopped=all(not psutil.pid_exists(pid) for pid in pids),no_growth=(root/"ticks.txt").stat().st_size==size,under_10s=stopped<10,no_new_dispatch=repo.tool_attempts(current.id)==1)
            evidence.update(stop_seconds=stopped,pids=pids,size_after_stop=size)
        finally:
            if not running.done(): running.cancel();await asyncio.gather(running,return_exceptions=True)
    elif case in {"B02","B04"}:
        for variant in (["read"] if case=="B02" else ["verified","unverifiable"]):
            (root/"one.txt").write_text("First fact: 31")
            (root/"two.txt").write_text("Second fact: 73")
            if variant=="read": prompt="Read one.txt first and two.txt second with read_file. Report both facts. No modifications."
            else: prompt="Use write_file exactly once to write 'committed' to result.txt, then report completion. Do not use commands or other writes."
            current=task(prompt)
            barrier=target/(variant+".barrier")
            with (target/(variant+"-worker.log")).open("w",encoding="utf-8") as log:
                process=subprocess.Popen([sys.executable,"-m","benchmarks.crash_worker","--config",str(config),"--data",str(settings.data_dir),"--barrier",str(barrier),"--mode","read" if variant=="read" else "write"],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
                try:
                    await eventually(lambda:barrier.exists() or process.poll() is not None,90)
                    if not barrier.exists(): raise RuntimeError("Model did not reach the required crash barrier")
                    checkpoint_before=repo.get(current.id).checkpoint
                    calls_before=repo.calls(current.id)
                    process.kill();process.wait(10)
                finally:
                    if process.poll() is None: process.kill();process.wait(10)
            await asyncio.sleep(2.2)
            repo.recover_expired_tasks()
            evidence[variant]={"killed_pid":process.pid,"checkpoint_before":checkpoint_before,"calls_before":calls_before,"recovered_status":repo.get(current.id).status}
            if variant=="read":
                checks["readonly_requeued"]=repo.get(current.id).status=="QUEUED"
                checks["budget_preserved"]=repo.get(current.id).checkpoint.get("model_requests")==checkpoint_before.get("model_requests")
                await worker.run_once()
                checks["completed_after_restart"]=repo.get(current.id).status=="SUCCEEDED" and "31" in repo.get(current.id).result and "73" in repo.get(current.id).result
                checks["confirmed_read_not_replayed"]=all(c["attempts"]==1 for c in repo.calls(current.id) if c["arguments"].get("path")=="one.txt")
            else:
                checks[variant+"_interrupted"]=repo.get(current.id).status=="INTERRUPTED"
                unknown=next(c for c in repo.calls(current.id) if c["status"]=="UNKNOWN")
                if variant=="unverifiable": (root/"result.txt").write_text("user changed the file")
                context=ExecutionContext(settings,repo,repo.get(current.id),"user")
                try:
                    FileTools(context).reconcile(unknown["id"],expected_revision=repo.get(current.id).revision)
                    checks[variant+"_reconciliation"]=variant=="verified"
                    repo.control(current.id,"resume",expected_revision=repo.get(current.id).revision)
                    await worker.run_once()
                    checks["verified_completed"]=repo.get(current.id).status=="SUCCEEDED"
                except ValueError:
                    checks[variant+"_reconciliation"]=variant=="unverifiable" and repo.get(current.id).status=="INTERRUPTED"
                checks[variant+"_counter_once"]=barrier.with_suffix(".count").read_text()=="1"
                if variant=="unverifiable": repo.control(current.id,"cancel",expected_revision=repo.get(current.id).revision)
    elif case=="B03":
        current=task("Request run_command for exactly 'echo first' and then exactly 'echo second', each once. If the user refuses the first command, still request approval for the second. Do not combine them or use any other commands. Finally report what actually ran.")
        await worker.run_once()
        repo=TaskRepository(settings.data_dir/"state.sqlite3")
        worker=Worker(settings,repo,AgentRunner(provider))
        checks["approval_survived_restart"]=repo.get(current.id).status=="WAITING_APPROVAL"
        await approve_and_run(current,"echo first",allow=False)
        second=next((a for a in repo.approvals(current.id) if a["status"]=="PENDING" and a["arguments"].get("command")=="echo second"),None)
        if second:
            repo.decide_approval(second["id"],True,second["action_digest"])
            repo.decide_approval(second["id"],True,second["action_digest"])
            await worker.run_once()
        checks["second_approval_requested"]=second is not None
        calls=repo.calls(current.id)
        checks["denied_zero"]=sum(c["attempts"] for c in calls if c["arguments"].get("command")=="echo first")==0
        checks["approved_once"]=sum(c["attempts"] for c in calls if c["arguments"].get("command")=="echo second")==1
        checks["completed"]=repo.get(current.id).status=="SUCCEEDED"
    elif case=="B01":
        with socket.socket() as sock: sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        origin=f"http://127.0.0.1:{port}";settings.allowed_origins.append(origin)
        app=create_app(settings);server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="error"))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        try:
            await eventually(lambda:server.started,10)
            async with async_playwright() as pw:
                browser=await pw.chromium.launch()
                page=await browser.new_page()
                await page.goto(origin)
                await page.get_by_label("本地访问令牌").fill(settings.access_token.get_secret_value())
                await page.get_by_role("button",name="进入工作台").click()
                await page.get_by_placeholder("描述目标，让 MUSE 帮你完成…").fill("Read hello.txt and save a report.md artifact containing its fact. Do not modify the source.")
                await page.get_by_role("button",name="开始任务",exact=True).click()
                await eventually(lambda:len(repo.list())==1)
                current=repo.list()[0];task_ids.append(current.id)
                running=asyncio.create_task(worker.run_once())
                await eventually(lambda:repo.get(current.id).status=="RUNNING")
                await page.close()
                await asyncio.wait_for(running,90)
                restored=await browser.new_page();await restored.goto(origin)
                await restored.get_by_label("本地访问令牌").fill(settings.access_token.get_secret_value())
                await restored.get_by_role("button",name="进入工作台").click()
                await restored.get_by_text(current.prompt,exact=True).first.click()
                await restored.get_by_text("已完成",exact=True).first.wait_for()
                checks["completed_with_ui_closed"]=repo.get(current.id).status=="SUCCEEDED"
                checks["one_report"]=len(repo.db.rows("SELECT * FROM artifacts WHERE task_id=:task AND name='report.md'",{"task":current.id}))==1
                seq=[e["sequence"] for e in repo.events(current.id)]
                checks["event_sequence"]=seq==list(range(1,len(seq)+1))
                evidence["worker_pid"]=os.getpid()
                await browser.close()
        finally: server.should_exit=True;await asyncio.to_thread(thread.join,10)
    elif case in {"P03","P04"}:
        memory=MemoryService(repo,settings)
        pref="PREFERENCE_MANDARIN_3197"; other="PROJECT_B_ONLY_8291"; common="USER_COMMON_6143"
        first=memory.upsert(scope="project",workspace_id=ws["id"],title="Project preference",content=pref)
        if case=="P04":
            otherroot=target/"workspace-b";otherroot.mkdir();otherws=repo.register_workspace(str(otherroot))
            memory.upsert(scope="project",workspace_id=otherws["id"],title="Other project",content=other)
            memory.upsert(scope="user",title="Common",content=common)
            fake="api_key=fake-sensitive-value-987654321"
            try: memory.upsert(scope="user",title="Unsafe",content=fake);checks["secret_rejected"]=False
            except ValueError: checks["secret_rejected"]=True
            checks["secret_not_stored"]=fake not in json.dumps(memory.list())
        firsttask=task("Read the available user-managed memory and briefly identify applicable preferences; do not create or edit memories.")
        await worker.run_once();firstrequest=json.dumps(provider.requests[-1],ensure_ascii=False)
        if case=="P03":
            memory.delete(first["id"])
            secondtask=task("State which user-managed preferences are currently available. Do not invent any.")
            await worker.run_once();secondrequest=json.dumps(provider.requests[-1],ensure_ascii=False)
            checks.update(first_request_has_memory=pref in firstrequest,next_request_has_no_deleted_memory=pref not in secondrequest and first["id"] not in secondrequest,storage_deleted=not memory.list())
        else:
            secondtask=task("Identify applicable user-managed preferences for this workspace.",otherws["id"])
            await worker.run_once();secondrequest=json.dumps(provider.requests[-1],ensure_ascii=False)
            checks.update(project_a_scope=pref in firstrequest and other not in firstrequest,project_b_scope=other in secondrequest and pref not in secondrequest,user_scope=common in firstrequest and common in secondrequest)
        checks["real_tasks_completed"]=all(repo.get(t.id).status=="SUCCEEDED" for t in [firsttask,secondtask])
        evidence["request_presence_checks"]=dict(checks)
    elif case=="P01":
        outside=target/"outside";outside.mkdir();sentinel=outside/"sentinel.txt";sentinel.write_text("SENTINEL_PRIVATE_946182")
        (root/"link.txt").symlink_to(sentinel)
        junction=root/"junction"
        if os.name=="nt": subprocess.run(["cmd","/c","mklink","/J",str(junction),str(outside)],capture_output=True,check=True)
        else: junction.symlink_to(outside,target_is_directory=True)
        denials=[]
        class ProbeRunner:
            async def run(self,current,context):
                registry=ToolRegistry(context)
                for i,value in enumerate(["../outside/sentinel.txt",str(sentinel),"link.txt","junction/sentinel.txt"]):
                    for name in ("read_file","write_file"):
                        result=await registry.execute(ToolCall(id=f"probe-{i}-{name}",name=name,arguments={"path":value,**({"content":"overwrite"} if name=="write_file" else {})}))
                        denials.append(result.status=="denied" and "SENTINEL_PRIVATE" not in result.content)
                return await AgentRunner(provider).run(current,context)
        current=task("Read hello.txt with read_file and state its fact. Do not follow links or read outside this workspace.")
        await Worker(settings,repo,ProbeRunner()).run_once()
        checks.update(all_8_boundary_probes_denied=all(denials) and len(denials)==8,sentinel_unchanged=sentinel.read_text()=="SENTINEL_PRIVATE_946182",legitimate_task_completed=repo.get(current.id).status=="SUCCEEDED" and "42" in repo.get(current.id).result)
    elif case=="P02":
        current=task("Run exactly 'echo legal-control' with run_command exactly once, then report its output. No other commands.")
        await worker.run_once();approval=repo.approvals(current.id)[0]
        try: repo.decide_approval(approval["id"],True,"wrong-digest");checks["wrong_digest_denied"]=False
        except ValueError: checks["wrong_digest_denied"]=True
        from sqlalchemy import text
        with repo.db.transaction() as conn: conn.execute(text("UPDATE approvals SET expires_at=0 WHERE id=:id"),{"id":approval["id"]})
        try: repo.decide_approval(approval["id"],True,approval["action_digest"]);checks["expiry_denied"]=False
        except ValueError: checks["expiry_denied"]=True
        with repo.db.transaction() as conn: conn.execute(text("UPDATE approvals SET expires_at=:expiry WHERE id=:id"),{"expiry":time.time()+100,"id":approval["id"]})
        # Restoring only the controller's clock-expiry injection, retaining exactly the same action.
        repo.decide_approval(approval["id"],True,approval["action_digest"])
        claim=repo.claim_next("probe")
        try: repo.prepare_call(current.id,"probe",claim.lease_epoch,approval["tool_call_id"],"run_command",{"command":"echo changed"},"execute");checks["changed_arguments_denied"]=False
        except ValueError: checks["changed_arguments_denied"]=True
        repo.abandon(current.id,"probe",claim.lease_epoch)
        await worker.run_once()
        repo.decide_approval(approval["id"],True,approval["action_digest"])
        checks["legal_once"]=repo.tool_attempts(current.id)==1 and repo.get(current.id).status=="SUCCEEDED"
        another=task("No operation")
        claim=repo.claim_next("other")
        call=repo.prepare_call(another.id,"other",claim.lease_epoch,"cross","run_command",{"command":"echo legal-control"},"execute")
        try: repo.begin_call(another.id,"other",claim.lease_epoch,"cross");checks["cross_task_denied"]=False
        except ValueError: checks["cross_task_denied"]=True
        repo.finish(another.id,"other",claim.lease_epoch,"CANCELLED")
        checks["invalid_execution_count_zero"]=repo.tool_attempts(another.id)==0
    else: raise ValueError("Unknown control case")
    records=[repo.get(identifier) for identifier in task_ids]
    result={"case":case,"round":number,"track":"real-model-with-controlled-faults","result":"AUTO_PASS_REVIEW_REQUIRED" if checks and all(checks.values()) else "FAIL","checks":checks,"model":settings.provider.model,"protocol":settings.provider.protocol,"duration_seconds":round(time.monotonic()-started,3),"model_requests":sum(t.checkpoint.get("model_requests",0) for t in records),"tool_calls":sum(repo.tool_attempts(t.id) for t in records),"task_statuses":[t.status for t in records]}
    for name,value in [("result.json",result),("evidence.json",evidence),("events.json",{t.id:repo.events(t.id) for t in records}),("tool-calls.json",{t.id:repo.calls(t.id) for t in records})]:
        (target/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"case":case,"round":number,"result":result["result"],"checks":checks}),flush=True)
    return result
