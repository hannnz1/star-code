from tests.muse.commerce.browser_navigation import close_panel
"""Language changes are local presentation changes, never merchant writes."""
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app


@pytest.mark.parametrize('width', [1440, 390])
def test_language_persists_without_changing_merchant_data(workflow, monkeypatch, width):
    service, tasks, plan, worker = workflow
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    worker.settings.allowed_origins.append(origin)
    app = create_app(worker.settings)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={'width': width, 'height': 1000})
            errors, writes = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_role('button', name='团队任务', exact=True).click()
            board = page.get_by_test_id('commerce-task-board')
            expect(board.get_by_role('heading', name='团队任务看板')).to_be_visible()
            page.on('request', lambda r: writes.append(r.url) if r.method != 'GET' else None)
            page.get_by_role('button', name='English', exact=True).click()
            expect(board.get_by_role('heading', name='Team task board')).to_be_visible()
            expect(board.get_by_role('heading', name='Active', exact=True)).to_be_visible()
            expect(page.get_by_role('button', name='Team tasks', exact=True)).to_be_visible()
            expect(page.locator('html')).to_have_attribute('lang', 'en')
            assert page.evaluate("localStorage.getItem('muse-ui-language')") == 'en'
            close_panel(page)
            board.get_by_label('Search merchant tasks').fill('Cup 商家资料')
            page.get_by_role('button', name='中文', exact=True).click()
            expect(board.get_by_label('搜索商家任务')).to_have_value('Cup 商家资料')
            page.get_by_role('button', name='English', exact=True).click()
            close_panel(page)
            board.get_by_label('Search merchant tasks').fill('')
            close_panel(page)
            board.get_by_role('button', name='More filters').click()
            expect(board.get_by_label('Filter task status')).to_be_visible()
            close_panel(page)
            board.get_by_label('Filter task status').select_option('attention')
            page.get_by_role('button', name='中文', exact=True).click()
            expect(board.get_by_label('筛选任务状态')).to_have_value('attention')
            page.get_by_role('button', name='English', exact=True).click()
            close_panel(page)
            board.get_by_label('Filter task status').select_option('all')
            output = root / 'work/ui-language-20261006'
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / f'merchant-en-{width}.png'), full_page=True)
            board.screenshot(path=str(output / f'task-board-en-{width}.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            # Dismissing the English confirmation must not submit cancellation.
            close_panel(page)
            board.locator('.commerce-board-card').first.click()
            dialogs = []
            def dismiss(dialog):
                dialogs.append(dialog.message)
                dialog.dismiss()
            page.on('dialog', dismiss)
            page.get_by_role('button', name='Cancel team task', exact=True).click()
            assert dialogs and 'Submitted remote operations' in dialogs[-1]
            close_panel(page)
            # A source-language API error already on screen must switch both ways.
            page.route('**/api/commerce/projects/*/plans', lambda route: route.fulfill(
                status=409, content_type='application/json',
                body='{"error":{"code":"RESOURCE_CONFLICT"}}'))
            close_panel(page)
            board.get_by_role('button', name='Refresh board').click()
            expect(page.get_by_role('alert').filter(has_text='Information changed. Reopen the project')).to_be_visible()
            page.get_by_role('button', name='中文', exact=True).click()
            expect(page.get_by_role('alert').filter(has_text='资料已更新，请重新打开项目后提交')).to_be_visible()
            page.get_by_role('button', name='English', exact=True).click()
            page.unroute('**/api/commerce/projects/*/plans')
            page.reload()
            expect(page.get_by_role('button', name='Team tasks', exact=True)).to_be_visible()
            expect(page.locator('html')).to_have_attribute('lang', 'en')
            assert errors == [] and writes == []
            assert len(tasks.list()) == 1
            assert service.repo.get_plan(plan.id, project_id=plan.project_id).revision == plan.revision
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
