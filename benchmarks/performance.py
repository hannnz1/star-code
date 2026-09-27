"""Local engineering measurements; no model calls and no capability score."""
import asyncio
import json
import math
import os
import socket
import threading
import time
from pathlib import Path

import psutil
import uvicorn
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from muse.config import load_settings
from muse.contracts import AgentResult, TaskRequest, ToolCall
from muse.main import create_app
from muse.tasks.repository import TaskRepository
from muse.tasks.worker import Worker
from muse.tools.registry import ToolRegistry


def distribution(samples):
    ordered=sorted(samples)
    return {"n":len(samples),"p50_ms":ordered[math.ceil(.5*len(samples))-1],"p95_ms":ordered[math.ceil(.95*len(samples))-1],"max_ms":max(samples),"samples_ms":samples}


async def run():
    root=Path("work/performance-"+str(time.time_ns())).resolve();root.mkdir(parents=True)
    settings=load_settings(data_dir=root/"api",require_provider=False)
    app=create_app(settings);repo=app.state.repository;workspace=repo.workspaces()[0]
    headers={"Authorization":"Bearer "+settings.access_token.get_secret_value()}
    samples=[]
    with TestClient(app,base_url="http://127.0.0.1:8765") as client:
        for i in range(210):
            start=time.perf_counter()
            response=client.post("/api/tasks",headers=headers,json={"prompt":"Latency fixture","workspace_id":workspace["id"],"client_request_id":str(i)})
            assert response.status_code==201
            if i>=10:samples.append((time.perf_counter()-start)*1000)
    report={"track":"engineering-performance","model":"none","clock":"time.perf_counter, same host","creation_in_process_asgi":distribution(samples),"creation_http_transport":"not included in ASGI measurements","failures":0}
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    origin=f"http://127.0.0.1:{port}";settings.allowed_origins.append(origin)
    server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="error"));thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        while not server.started:await asyncio.sleep(.05)
        samples=[]
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH",str(Path("work/browsers").resolve()))
        async with async_playwright() as pw:
            browser=await pw.chromium.launch();page=await browser.new_page()
            await page.goto(origin);await page.get_by_label("本地访问令牌").fill(settings.access_token.get_secret_value());await page.get_by_role("button",name="进入工作台").click()
            await page.get_by_placeholder("描述目标，让 MUSE 帮你完成…").fill("Event latency fixture")
            await page.get_by_role("button",name="开始任务",exact=True).click()
            await page.get_by_text("你的目标",exact=True).wait_for()
            current=next(task for task in repo.list() if task.prompt=="Event latency fixture")
            for i in range(200):
                marker=f"LatencyMarker{i:04d}"
                repo.add_event(current.id,"text_delta",{"text":marker+"\n"})
                start=time.perf_counter()
                await page.locator(".message").filter(has_text=marker).wait_for(timeout=10000)
                samples.append((time.perf_counter()-start)*1000)
            await browser.close()
        report["event_commit_to_browser_observed"]=distribution(samples)
    finally:server.should_exit=True;await asyncio.to_thread(thread.join,10)
    settings=load_settings(data_dir=root/"worker",require_provider=False)
    repo=TaskRepository(settings.data_dir/"state.sqlite3")
    project=root/"project";project.mkdir();ws=repo.register_workspace(str(project))
    (project/"child.py").write_text("import pathlib,time\nwhile True:\n with pathlib.Path('ticks.txt').open('a') as f: f.write('x')\n time.sleep(.05)\n")
    (project/"parent.py").write_text("import subprocess,sys,pathlib,json,os,time\np=subprocess.Popen([sys.executable,'child.py'])\npathlib.Path('pids.json').write_text(json.dumps([os.getpid(),p.pid]))\ntime.sleep(60)\n")
    class Runner:
        async def run(self,task,ctx):
            await ToolRegistry(ctx).execute(ToolCall(id="fixture",name="run_command",arguments={"command":"python parent.py","timeout_seconds":60}))
            return AgentResult(status="SUCCEEDED",text="fixture ended")
    worker=Worker(settings,repo,Runner())
    confirm,stop=[] ,[]
    for i in range(30):
        for name in ("ticks.txt","pids.json"):
            if (project/name).exists():(project/name).unlink()
        task=repo.create(TaskRequest(prompt="Controlled cancellation fixture",workspace_id=ws["id"],client_request_id=f"cancel-{i}"))
        await worker.run_once();approval=repo.approvals(task.id)[0];repo.decide_approval(approval["id"],True,approval["action_digest"])
        future=asyncio.create_task(worker.run_once())
        deadline=time.monotonic()+10
        while not (project/"ticks.txt").exists() and time.monotonic()<deadline:await asyncio.sleep(.03)
        assert (project/"ticks.txt").exists()
        pids=json.loads((project/"pids.json").read_text())
        start=time.perf_counter();repo.control(task.id,"cancel",expected_revision=repo.get(task.id).revision);persisted=time.perf_counter()
        confirm.append((persisted-start)*1000)
        await asyncio.wait_for(future,10)
        stop.append((time.perf_counter()-persisted)*1000)
        assert all(not psutil.pid_exists(pid) for pid in pids)
        size=(project/"ticks.txt").stat().st_size;await asyncio.sleep(2);assert size==(project/"ticks.txt").stat().st_size
    report["cancel_repository_confirmation"]=distribution(confirm)
    report["process_tree_stop_after_confirmation"]=distribution(stop)
    report["cancel_confirmation_ui_click_latency"]="not measured; repository acknowledgement only"
    recovery=[]
    for i in range(30):
        task=repo.create(TaskRequest(prompt="Recovery fixture",workspace_id=ws["id"],client_request_id=f"recover-{i}"))
        claim=repo.claim_next("old",now=100,ttl=20)
        start=time.perf_counter();repo.recover_expired_tasks(now=121);new=repo.claim_next("new",now=122,ttl=20)
        recovery.append((time.perf_counter()-start)*1000)
        assert new.id==task.id and new.lease_epoch>claim.lease_epoch
        repo.abandon(task.id,"new",new.lease_epoch)
        repo.control(task.id,"cancel",expected_revision=repo.get(task.id).revision)
    report["expired_lease_recovery_without_waiting_for_ttl"]=distribution(recovery)
    report["memory_rss_peak"]=None;report["memory_note"]="Separate API/Worker/browser process-tree RSS not sampled; no memory performance claim."
    target=Path("reports/performance.json");target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({key:{k:v for k,v in value.items() if k!='samples_ms'} for key,value in report.items() if isinstance(value,dict)},indent=2))


if __name__=="__main__":asyncio.run(run())
