from tests.muse.commerce.browser_navigation import close_panel
import os
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app
from muse.contracts import ModelEvent
from muse.commerce.follow_up_models import ModelSuggestionService
from test_agent_loop import ScriptedProvider


@pytest.mark.parametrize('width', [1440, 900, 390])
def test_follow_up_review_saves_linked_draft_without_starting_work(workflow, monkeypatch, width):
    service, tasks, plan, worker = workflow
    plan = service.repo.save_plan(plan.model_copy(update={'state': 'BLOCKED', 'error_code': 'MODEL_UNAVAILABLE'}), plan.revision)
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    worker.settings.allowed_origins.append(origin)
    app = create_app(worker.settings)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={'width': width, 'height': 900})
            errors, writes = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').filter(has_text=plan.id[:8]).click()
            page.get_by_role('tab', name='后续任务', exact=True).click()
            detail = page.locator(f'.commerce-plan-detail[data-plan-id="{plan.id}"]')
            expect(detail).to_have_count(1)
            page.on('request', lambda request: writes.append(request.url) if request.method == 'POST' else None)
            panel = detail.get_by_test_id('commerce-follow-ups')
            panel.get_by_role('button', name='读取后续建议').click()
            button = panel.get_by_role('button', name='保存建议草稿：修复阻塞后重新准备')
            expect(button).to_be_visible()
            expect(panel.get_by_text('错误码：MODEL_UNAVAILABLE', exact=True)).to_be_visible()
            assert writes == [] and len(tasks.list()) == 1
            screenshot_root = root / 'work/task-board-ui-2026-10-05'
            screenshot_root.mkdir(parents=True, exist_ok=True)
            panel.screenshot(path=str(screenshot_root / f'follow-ups-{width}.png'))
            button.click()
            expect(page.get_by_text('正在编辑：修复阻塞后重新准备 · 草稿', exact=True)).to_be_visible()
            expect(page.get_by_text(f'后续任务来源：计划 {plan.id[:8]} · 版本 {plan.revision}。这是成果来源记录，不会自动启动前后任务。', exact=True)).to_be_visible()
            assert len(tasks.list()) == 1
            assert len(writes) == 1 and writes[0].endswith('/follow-ups/accept')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.reload()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            close_panel(page)
            page.get_by_test_id('commerce-task-board').get_by_role('button', name='修复阻塞后重新准备', exact=False).click()
            expect(page.get_by_text('正在编辑：修复阻塞后重新准备 · 草稿', exact=True)).to_be_visible()
            close_panel(page)
            page.get_by_test_id('commerce-task-board').get_by_role('button', name='搭建独立站', exact=False).click()
            page.get_by_role('tab', name='后续任务', exact=True).click()
            panel = page.get_by_test_id('commerce-follow-ups')
            page.once('dialog', lambda dialog: dialog.accept())
            panel.get_by_role('button', name='用当前模型生成更多建议').click()
            expect(panel.get_by_role('status')).to_contain_text('QUEUED')
            provider = ScriptedProvider([[ModelEvent(type='text', text=json.dumps({'suggestions': [
                {'title': 'Review mobile navigation', 'kind': 'build_site', 'prompt': 'Review mobile navigation and verify.'}]}))]])
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(lambda: asyncio.run(ModelSuggestionService(service.repo, worker.settings).run_once(provider))).result(timeout=10)
            expect(panel.get_by_role('status')).to_contain_text('SUCCEEDED', timeout=10000)
            panel.get_by_role('button', name='读取后续建议').click()
            expect(panel.get_by_role('button', name='保存建议草稿：Review mobile navigation')).to_be_visible()
            assert len(provider.requests) == 1 and len(tasks.list()) == 1
            panel.screenshot(path=str(screenshot_root / f'model-follow-ups-{width}.png'))
            panel.get_by_role('button', name='批量管理建议').click()
            panel.get_by_role('checkbox', name='选择建议 修复阻塞后重新准备').check()
            panel.get_by_role('checkbox', name='选择建议 Review mobile navigation').check()
            panel.get_by_role('button', name='保存所选建议为草稿（2）').click()
            expect(panel.get_by_text('已保存 2 份建议草稿，可在看板批量启动或取消。', exact=True)).to_be_visible()
            board = page.get_by_test_id('commerce-task-board')
            close_panel(page)
            board.get_by_role('button', name='更多筛选', exact=True).click()
            close_panel(page)
            board.get_by_label('筛选草稿来源').select_option('suggested')
            expect(board.get_by_role('button', name='Review mobile navigation', exact=False)).to_be_visible()
            expect(board.get_by_role('button', name='修复阻塞后重新准备', exact=False)).to_have_count(1)
            assert len(tasks.list()) == 1
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
