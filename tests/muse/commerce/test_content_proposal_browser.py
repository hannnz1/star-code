import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app
from tests.muse.commerce.test_content_proposals import pending_content


@pytest.mark.parametrize('width', [1440, 390])
def test_merchant_sees_wording_difference_and_explicitly_confirms_new_source(workflow, monkeypatch, width):
    _proposals, service, runtime, plan, manager, *_ = pending_content(workflow)
    worker = workflow[3]
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
            page = browser.new_page(viewport={'width': width, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').first.click()
            page.get_by_role('button', name='查看商品文案候选', exact=True).click(timeout=3000)
            panel = page.locator('.commerce-content-proposal')
            expect(panel).to_contain_text('Ceramic Cup')
            expect(panel).to_contain_text('Ceramic cup.')
            button = panel.get_by_role('button', name='确认文案并生成新资料批次', exact=True)
            expect(button).to_be_disabled()
            panel.get_by_label('我已核对改写文案中的商品事实').check()
            button.click()
            expect(page.get_by_text('文案已确认，请使用新批次重新创建团队任务。', exact=True)).to_be_visible()
            expect(page.get_by_role('button', name='查看商品文案候选', exact=True)).to_have_count(0)
            assert service.repo.get_plan(plan.id, project_id=plan.project_id).state == 'STALE'
            assert runtime.get(manager.task_id).cancel_requested
            assert len(service.repo.list_product_imports(plan.project_id)) == 2
            assert not runtime.db.rows("SELECT 1 FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
