from tests.muse.commerce.browser_navigation import close_panel
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app
from tests.muse.commerce.test_code_integration import seal


@pytest.mark.parametrize('width', [1440, 900, 390])
def test_code_baseline_review_apply_and_file_diff_are_explicit(workflow, monkeypatch, tmp_path, width):
    service, tasks, plan, worker = workflow
    sealed = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
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
            page.on('request', lambda request: writes.append(request.url) if request.method == 'POST' else None)
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').first.click()
            page.get_by_role('tab', name='成果审查', exact=True).click()
            detail = page.locator(f'.commerce-plan-detail[data-plan-id="{sealed.id}"]')
            expect(detail.get_by_test_id('commerce-review-summary')).to_have_count(1)
            detail.get_by_role('button', name='读取代码、预览与发布目标').click()
            expect(detail.get_by_text('逐文件代码审查', exact=True)).to_be_visible()
            detail.get_by_text('style.css', exact=True).click()
            expect(detail.get_by_text('+body { color: #111; }', exact=False)).to_be_visible()
            page.get_by_role('tab', name='代码差异与整合', exact=True).click()
            panel = detail.get_by_test_id('code-integration')
            panel.get_by_role('button', name='审查代码整合').click()
            expect(panel.get_by_role('button', name='整合到项目代码基线')).to_be_disabled()
            assert not writes
            page.once('dialog', lambda dialog: dialog.accept())
            panel.get_by_role('button', name='放弃应用这份代码').click()
            expect(panel.get_by_role('status')).to_contain_text('已放弃')
            page.once('dialog', lambda dialog: dialog.accept())
            panel.get_by_role('button', name='恢复代码成果供审查').click()
            expect(panel.get_by_role('status')).to_contain_text('可整合')
            panel.get_by_role('checkbox').check()
            panel.get_by_role('button', name='整合到项目代码基线').click()
            expect(panel.get_by_role('status')).to_contain_text('已整合到代码基线版本 1')
            assert len(writes) == 3 and writes[-1].endswith('/code-integration')
            assert all(url.endswith('/code-disposition') for url in writes[:2])
            assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 2')
            page.screenshot(path=str(tmp_path / f'code-integration-{width}.png'), full_page=True)
            screenshots = root / 'work' / 'task-board-ui-2026-10-05'
            screenshots.mkdir(exist_ok=True)
            panel.screenshot(path=str(screenshots / f'code-integration-{width}.png'))
            page.get_by_test_id('commerce-task-board').screenshot(path=str(screenshots / f'task-board-{width}.png'))
            assert errors == []
            assert service.repo.get_plan(sealed.id, project_id=sealed.project_id) == sealed
            browser.close()
    finally:
        server.should_exit = True; thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
