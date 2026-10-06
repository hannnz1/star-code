"""Real browser controls with explicitly simulated verification status."""
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app


@pytest.mark.parametrize('width', [1440, 768, 390])
def test_verification_progress_and_explicit_controls(workflow, monkeypatch, width):
    _service, _repo, plan, worker = workflow
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers'))
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
            errors, commands = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            value = {'id': 'a' * 32, 'project_id': plan.project_id, 'plan_id': plan.id,
                'plan_revision': plan.revision, 'revision': 3, 'state': 'NEEDS_RECONCILIATION',
                'phase': 'staging', 'completed_phases': ['reference', 'source_capture'],
                'cancel_requested': False, 'error_code': None}
            def remote(route):
                if route.request.method == 'POST':
                    commands.append(route.request.url.rsplit('/', 1)[-1])
                    if commands[-1] == 'cancel': value.update(state='CANCELLED', cancel_requested=True)
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(value))
                else:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps([value]))
            page.route('**/verification-jobs**', remote)
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').first.click()
            page.get_by_role('tab', name='成果审查', exact=True).click()
            page.get_by_role('tab', name='验证结果', exact=True).click()
            panel = page.get_by_test_id('verification-panel').first
            expect(panel.get_by_role('status')).to_contain_text('结果待核对')
            expect(panel.get_by_text('封存来源 · 已完成', exact=True)).to_be_visible()
            panel.get_by_role('button', name='刷新验证进度').click()
            assert commands == []
            panel.get_by_role('button', name='只读核对中断结果').click()
            expect(panel.get_by_role('button', name='只读核对中断结果')).to_be_enabled()
            assert commands == ['reconcile']
            panel.get_by_role('button', name='取消此验证').click()
            expect(panel.get_by_role('status')).to_contain_text('已取消')
            assert commands == ['reconcile', 'cancel']
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True; thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
