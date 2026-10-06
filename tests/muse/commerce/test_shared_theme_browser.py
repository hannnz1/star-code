"""Shared presentation must not depend on opening the lazy merchant workspace."""
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app


@pytest.mark.parametrize('width', [1440, 900, 390])
def test_shared_theme_before_and_after_merchant_navigation(workflow, monkeypatch, width):
    service, tasks, plan, worker = workflow
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    worker.settings.allowed_origins.append(origin)
    app = create_app(worker.settings)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    output = root / 'work/crew-shared-theme-20261006'
    output.mkdir(parents=True, exist_ok=True)
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
            page.get_by_role('button', name='English', exact=True).click(timeout=3000)
            expect(page.locator('html')).to_have_attribute('lang', 'en')
            page.get_by_role('button', name='中文', exact=True).click(timeout=3000)
            expect(page.locator('.login')).to_have_css('background-color', 'rgb(246, 246, 247)')
            assert 'Georgia' not in page.locator('.login h1').evaluate('(el) => getComputedStyle(el).fontFamily')
            page.screenshot(path=str(output / f'login-{width}.png'))
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='开发空间', exact=True).click()
            expect(page.locator('.home')).to_be_visible()
            page.on('request', lambda r: writes.append(r.url) if r.method != 'GET' else None)
            expect(page.locator('.sidebar')).to_have_css('background-color', 'rgb(240, 240, 241)')
            expect(page.locator('.app-shell')).to_have_css('background-color', 'rgb(246, 246, 247)')
            assert 'Georgia' not in page.locator('.home h1').evaluate('(el) => getComputedStyle(el).fontFamily')
            page.locator('.composer textarea').fill('统一样式时保留我的编程目标')
            page.get_by_role('button', name='English', exact=True).click()
            expect(page.locator('.composer textarea')).to_have_value('统一样式时保留我的编程目标')
            page.get_by_role('button', name='中文', exact=True).click()
            page.screenshot(path=str(output / f'home-{width}.png'))
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            expect(page.locator('.commerce-home.commerce-studio')).to_be_visible()
            page.screenshot(path=str(output / f'merchant-{width}.png'))
            page.get_by_role('button', name='开发空间', exact=True).click()
            expect(page.locator('.sidebar')).to_have_css('background-color', 'rgb(240, 240, 241)')
            expect(page.locator('.composer textarea')).to_have_value('统一样式时保留我的编程目标')
            page.get_by_role('button', name='设置', exact=True).click()
            page.get_by_role('button', name='偏好与记忆', exact=True).click()
            expect(page.locator('.modal')).to_have_css('background-color', 'rgb(255, 255, 255)')
            page.screenshot(path=str(output / f'memory-{width}.png'))
            page.locator('.modal-heading .icon-button').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').first.click()
            page.get_by_role('button', name='打开执行日志与审批', exact=False).first.click()
            expect(page.locator('.conversation')).to_be_visible()
            expect(page.locator('.task-heading')).to_be_visible()
            expect(page.locator('.evidence')).to_have_css('background-color', 'rgb(246, 246, 247)')
            page.screenshot(path=str(output / f'task-{width}.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert errors == [] and writes == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
