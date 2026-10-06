import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.commerce_connector.reference_service import ReferenceEnvironmentService
from muse.main import create_app
from tests.muse.commerce.test_reference_runner import inputs
from tests.muse.commerce.test_reference_service import Runner


@pytest.mark.parametrize('width', [1440, 390])
def test_preview_setup_timeout_requires_refresh_and_never_reinstalls(workflow, tmp_path, monkeypatch, width):
    """Real UI/DB/service; Docker provisioning is deliberately simulated."""
    jobs, job, bundle, _ = inputs(workflow, tmp_path)
    runner = Runner(jobs, job)
    host = ReferenceEnvironmentService(jobs, runner, bundle, ports=(63660, 63661))
    settings = workflow[3].settings
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    settings.allowed_origins.append(origin)
    app = create_app(settings)
    app.state.commerce_reference = host
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={'width': width, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='设置', exact=True).click()
            panel = page.get_by_test_id('reference-setup')
            expect(panel.get_by_role('button', name='清理此预览站', exact=True)).to_be_disabled()
            panel.get_by_role('button', name='开始准备预览站', exact=True).click()
            expect(panel.get_by_role('alert')).to_be_visible()
            assert jobs.read(job.project_id, job.id).state == 'UNKNOWN' and len(runner.calls) == 2
            panel.get_by_role('button', name='刷新预览作业', exact=True).click()
            expect(panel).to_contain_text('准备结果未知')
            expect(panel.get_by_role('button', name='开始准备预览站', exact=True)).to_have_count(0)
            panel.get_by_role('button', name='只读查询资源', exact=True).click()
            expect(panel.get_by_role('status')).to_contain_text('资源存在不代表预览站就绪')
            assert runner.calls == ['prepare', ('bootstrap', {'currency': 'USD', 'language': 'en-US'}), 'recover']
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
