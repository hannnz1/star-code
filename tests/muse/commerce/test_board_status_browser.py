from tests.muse.commerce.browser_navigation import close_panel
"""Board state semantics against persisted synthetic plans, without model calls."""
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app


@pytest.mark.parametrize('width', [1440, 900, 390])
def test_board_keeps_blocked_work_out_of_ready_and_filters_attention(workflow, monkeypatch, width):
    service, tasks, original, worker = workflow
    project = service.repo.get_project(original.project_id)
    states = ['NEEDS_INPUT', 'BLOCKED', 'NEEDS_RECONCILIATION', 'PARTIAL',
              'REVIEW_REQUIRED', 'APPROVED', 'SUCCEEDED']
    plans = {}
    for state in states:
        plan = service.create_workflow(project.id, 'build_site', 'State fixture ' + state,
                                       'state-' + state, project.revision, max_requests=8)
        plans[state] = service.repo.save_plan(plan.model_copy(update={'state': state}), plan.revision)
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
            expect(board.locator('.commerce-board-card')).to_have_count(8)
            page.on('request', lambda request: writes.append(request.url) if request.method != 'GET' else None)
            ready = board.get_by_role('region', name='待审查 2 项', exact=True)
            expect(ready).to_be_visible()
            for state in ('REVIEW_REQUIRED', 'APPROVED'):
                expect(ready.locator('.commerce-board-card-id').filter(has_text=plans[state].id[:8])).to_have_count(1)
            active = board.get_by_role('region', name='进行中 5 项', exact=True)
            for state in states[:4]:
                card = active.locator('.commerce-board-card').filter(has_text=plans[state].id[:8])
                expect(card.locator('.commerce-board-attention')).to_be_visible()
            close_panel(page)
            board.get_by_role('button', name='更多筛选', exact=True).click()
            close_panel(page)
            board.get_by_label('筛选任务状态').select_option('attention')
            expect(board.locator('.commerce-board-card')).to_have_count(4)
            card = board.locator('.commerce-board-card').filter(has_text=plans['BLOCKED'].id[:8])
            card.click()
            expect(page.locator('.commerce-plan-detail').get_by_test_id('plan-next-action')).to_contain_text('查看阻塞原因')
            close_panel(page)
            close_panel(page)
            board.get_by_label('筛选任务状态').select_option('review')
            expect(board.locator('.commerce-board-card')).to_have_count(2)
            close_panel(page)
            board.get_by_label('筛选任务状态').select_option('all')
            expect(board.locator('.commerce-board-card')).to_have_count(8)
            output = root / 'work/task-board-status-2026-10-05'
            output.mkdir(parents=True, exist_ok=True)
            board.screenshot(path=str(output / f'board-{width}.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert writes == []
            assert errors == []
            assert len(tasks.list()) == 8
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
