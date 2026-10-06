from tests.muse.commerce.browser_navigation import close_panel
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.commerce.api import TaskDraftInput
from muse.commerce.task_drafts import CommerceDraftService
from muse.commerce.task_automation import LocalApplyService
from muse.commerce.task_queue import CommerceTaskQueue
from muse.main import create_app
from tests.muse.commerce.test_code_integration import seal


@pytest.mark.parametrize('width', [1440, 900, 390])
def test_batch_queue_cancel_and_one_shot_local_apply(workflow, monkeypatch, width):
    service, tasks, plan, worker = workflow
    plan = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    project = service.repo.get_project(plan.project_id)
    drafts = CommerceDraftService(service.repo, service)
    for index in range(2):
        drafts.create(project.id, TaskDraftInput(kind='build_site', title=f'Batch {index}', prompt='Prepare site',
            expected_project_revision=project.revision, client_request_id=f'browser-batch-{index}'))
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
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept())
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            board = page.get_by_test_id('commerce-task-board')
            close_panel(page)
            board.get_by_label('搜索商家任务').fill('独立站')
            expect(board.get_by_role('button', name='搭建独立站', exact=False)).to_have_count(1)
            expect(board.get_by_role('button', name='Batch 0', exact=False)).to_have_count(0)
            close_panel(page)
            board.get_by_label('搜索商家任务').fill('')
            close_panel(page)
            board.get_by_role('button', name='更多筛选', exact=True).click()
            close_panel(page)
            board.get_by_label('筛选草稿来源').select_option('drafts')
            expect(board.get_by_role('button', name='搭建独立站', exact=False)).to_have_count(0)
            close_panel(page)
            board.get_by_label('筛选草稿来源').select_option('all')
            close_panel(page)
            board.get_by_role('checkbox', name='选择草稿 Batch 0').check()
            close_panel(page)
            board.get_by_role('checkbox', name='选择草稿 Batch 1').check()
            close_panel(page)
            board.get_by_role('button', name='启动所选草稿').click()
            expect(board.locator('.commerce-board-card-id').filter(has_text='排队中')).to_have_count(1)
            assert len(tasks.list()) == 3  # original manager and developer plus one admitted manager
            close_panel(page)
            board.get_by_role('button', name='Batch 1', exact=False).click()
            page.get_by_role('button', name='取消排队', exact=True).click()
            assert len(tasks.list()) == 3
            close_panel(page)
            board.get_by_role('button', name='搭建独立站', exact=False).click()
            panel = page.get_by_test_id('local-apply-automation')
            panel.get_by_role('button', name='这一次自动应用本地成果').click()
            expect(panel.get_by_role('status')).to_contain_text('ARMED')
            LocalApplyService(service.repo, worker.settings.data_dir / 'commerce-source.git').process()
            expect(panel.get_by_role('status')).to_contain_text('APPLIED', timeout=10000)
            assert tasks.db.rows('SELECT * FROM commerce_approvals') == []
            screenshot_root = root / 'work/task-board-ui-2026-10-05'
            screenshot_root.mkdir(parents=True, exist_ok=True)
            panel.screenshot(path=str(screenshot_root / f'auto-apply-{width}.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
