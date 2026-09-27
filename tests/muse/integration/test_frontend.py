import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from muse.config import load_settings
from muse.main import create_app


def test_browser_create_pause_resume_cancel_memory_and_reconnect(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(root / "work" / "browsers")))
    settings = load_settings(data_dir=tmp_path / "data", require_provider=False)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    settings.allowed_origins.append(f"http://127.0.0.1:{port}")
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}")
            page.get_by_label("本地访问令牌").fill(settings.access_token.get_secret_value())
            page.get_by_role("button", name="进入工作台").click()
            page.get_by_placeholder("描述目标，让 MUSE 帮你完成…").fill("请整理本地资料")
            page.get_by_role("button", name="开始任务", exact=True).click()
            page.get_by_role("button", name="暂停", exact=True).click()
            page.get_by_role("button", name="继续执行", exact=True).click()
            page.get_by_role("button", name="取消任务", exact=True).click()
            page.get_by_text("已取消", exact=True).first.wait_for()
            page.reload()
            page.get_by_text("请整理本地资料", exact=True).first.click()
            page.get_by_text("已取消", exact=True).first.wait_for()
            page.get_by_role("button", name="记忆管理", exact=True).click()
            page.get_by_label("记忆标题").fill("语言偏好")
            page.get_by_label("记忆内容").fill("使用中文")
            page.get_by_role("button", name="保存记忆", exact=True).click()
            page.get_by_role("button", name="删除记忆 语言偏好").click()
            page.get_by_role("button", name="删除记忆 语言偏好").wait_for(state="detached")
            assert not app.state.memory.list()
            page.get_by_role("button", name="关闭弹窗").click()
            page.get_by_role("button", name="新建任务").click()
            page.get_by_placeholder("描述目标，让 MUSE 帮你完成…").wait_for()
            (root / "work" / "screenshots").mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(root / "work" / "screenshots" / "home.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.set_viewport_size({"width": 1440, "height": 1000})
            lost = []
            def lose_first_response(route):
                if route.request.method == "POST" and not lost:
                    route.fetch()
                    lost.append(True)
                    route.abort("failed")
                else:
                    route.continue_()
            page.route("**/api/tasks", lose_first_response)
            page.get_by_placeholder("描述目标，让 MUSE 帮你完成…").fill("Retry must be idempotent")
            page.get_by_role("button", name="开始任务", exact=True).click()
            page.get_by_role("alert").wait_for()
            page.get_by_role("button", name="开始任务", exact=True).click()
            page.get_by_text("你的目标", exact=True).wait_for()
            created = [task for task in app.state.repository.list() if task.prompt == "Retry must be idempotent"]
            assert len(created) == 1
            delayed = []
            def delay_pause_response(route):
                delayed.append((route, route.fetch()))
            page.route('**/api/tasks/*/pause', delay_pause_response)
            page.get_by_role('button', name='暂停', exact=True).click()
            page.get_by_text('请整理本地资料', exact=True).first.click()
            page.get_by_role('heading', name='请整理本地资料', exact=True).wait_for()
            assert delayed
            page.evaluate("""() => { window.seenTaskHeadings = []; window.headingObserver = new MutationObserver(() => window.seenTaskHeadings.push(document.querySelector('.task-heading h1')?.textContent)); window.headingObserver.observe(document.body, {childList:true, subtree:true, characterData:true}); }""")
            route, response = delayed[0]
            route.fulfill(response=response)
            page.wait_for_timeout(150)
            seen = page.evaluate('() => { window.headingObserver.disconnect(); return window.seenTaskHeadings; }')
            assert 'Retry must be idempotent' not in seen
            assert page.get_by_role('heading', name='请整理本地资料', exact=True).count() == 1
            page.unroute('**/api/tasks/*/pause', delay_pause_response)
            page.get_by_text('Retry must be idempotent', exact=True).first.click()
            page.get_by_role('heading', name='Retry must be idempotent', exact=True).wait_for()
            page.get_by_role('button', name='继续执行', exact=True).click()
            import json
            from sqlalchemy import text
            with app.state.repository.db.transaction() as conn:
                conn.execute(text("UPDATE tasks SET checkpoint=:cp WHERE id=:id"), {"id":created[0].id,"cp":json.dumps({"model_requests":1,"usage":{"input_tokens":10,"output_tokens":0,"complete":False}})})
            page.get_by_text("部分统计：10 / 0", exact=True).wait_for()
            parent = app.state.repository.claim_next('browser-fixture')
            app.state.repository.spawn_child(parent.id, 'browser-fixture', parent.lease_epoch, 'child', '浏览器子任务')
            page.get_by_role('heading', name='子任务', exact=True).wait_for()
            page.locator('.reply-box .space-item').filter(has_text='浏览器子任务').click()
            page.get_by_role('heading', name='浏览器子任务', exact=True).wait_for()
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)


def test_browser_input_approval_download_and_followup(tmp_path, monkeypatch):
    import asyncio
    import re
    from muse.agent.loop import AgentRunner
    from muse.contracts import ModelEvent, ToolCall
    from muse.tasks.worker import Worker
    from test_agent_loop import ScriptedProvider
    root=Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH',os.environ.get('PLAYWRIGHT_BROWSERS_PATH',str(root/'work/browsers')))
    settings=load_settings(data_dir=tmp_path/'data',require_provider=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}';settings.allowed_origins.append(origin)
    app=create_app(settings);repo=app.state.repository
    call=lambda id,name,arguments:[ModelEvent(type='call',call=ToolCall(id=id,name=name,arguments=arguments))]
    provider=ScriptedProvider([
        call('question','ask_user',{'question':'Which format?'}),
        call('denied','run_command',{'command':'echo must-not-run'}),
        call('approved','run_command',{'command':'echo approved-fixture'}),
        call('report','save_artifact',{'name':'report.md','content':'# Verified deliverable\nOriginal version.'}),
        [ModelEvent(type='text',text='Report saved.')],
        [ModelEvent(type='text',text='Follow-up completed.')],
    ])
    worker=Worker(settings,repo,AgentRunner(provider))
    def run_worker():
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(lambda: asyncio.run(worker.run_once())).result(timeout=30)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();page=browser.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(origin);page.get_by_label('本地访问令牌').fill(settings.access_token.get_secret_value())
            page.get_by_role('button',name='进入工作台').click()
            page.get_by_placeholder('描述目标，让 MUSE 帮你完成…').fill('Complete browser workflow')
            page.get_by_role('button',name='开始任务',exact=True).click()
            page.get_by_text('你的目标',exact=True).wait_for()
            original=repo.list()[0];run_worker()
            page.get_by_label('补充信息后继续').fill('Markdown')
            page.get_by_role('button',name='发送补充信息').click()
            page.get_by_label('补充信息后继续').wait_for(state='detached')
            run_worker()
            page.get_by_role('button',name='拒绝',exact=True).click()
            page.get_by_role('button',name='拒绝',exact=True).wait_for(state='detached')
            run_worker()
            page.get_by_text('echo approved-fixture',exact=True).wait_for()
            from sqlalchemy import text
            approval = next(a for a in repo.approvals(original.id) if a['status'] == 'PENDING')
            with repo.db.transaction() as conn:
                conn.execute(text('UPDATE approvals SET expires_at=1 WHERE id=:id'), {'id': approval['id']})
            page.get_by_role('button', name='审批已过期 · 续期后重新审阅', exact=True).click()
            page.get_by_role('button', name='批准执行').wait_for()
            assert repo.get(original.id).status == 'WAITING_APPROVAL'
            assert next(c for c in repo.calls(original.id) if c['id'] == 'approved')['attempts'] == 0
            page.get_by_role('button',name='批准执行').click()
            page.get_by_role('button',name='批准执行').wait_for(state='detached')
            run_worker()
            page.get_by_label('在此基础上继续').wait_for()
            with page.expect_download() as download:
                page.get_by_role('button',name=re.compile('report.md')).click()
            saved=tmp_path/'downloaded.md';download.value.save_as(saved)
            assert saved.read_text(encoding='utf-8')=='# Verified deliverable\nOriginal version.'
            calls=repo.calls(original.id)
            assert next(c for c in calls if c['id']=='denied')['attempts']==0
            assert next(c for c in calls if c['id']=='approved')['attempts']==1
            assert any(message.get('content')=='Markdown' for message in provider.requests[1])
            original_artifact=app.state.artifacts.list(original.id)[-1]
            page.get_by_label('在此基础上继续').fill('Continue this report')
            page.get_by_role('button',name='创建跟进任务').click()
            page.get_by_label('在此基础上继续').wait_for(state='detached')
            followup=next(t for t in repo.list() if t.id!=original.id)
            assert followup.parent_task_id==original.id
            run_worker()
            page.get_by_label('在此基础上继续').wait_for()
            assert repo.get(original.id).status=='SUCCEEDED'
            assert app.state.artifacts.list(original.id)[-1]['sha256']==original_artifact['sha256']
            assert not errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(10)
