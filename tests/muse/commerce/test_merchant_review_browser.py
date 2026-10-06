import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401


@pytest.mark.parametrize('width', [1440, 390])
def test_merchant_reviews_exact_products_and_images_and_explicitly_approves_only_once(merchant_review, workflow, monkeypatch, width, tmp_path):  # noqa: F811
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    repo, _project, plan, intent, evidence, connection, clock, _ = merchant_review
    approvals = MerchantReleaseApprovalRepository(repo, clock=lambda: clock[0])
    approvals.stage_review(intent, evidence, connection=connection, expected_plan_revision=plan.revision)
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'; settings = workflow[3].settings
    settings.allowed_origins.append(origin)
    app = create_app(settings); app.state.commerce_merchant_approvals = approvals
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(); page = browser.new_page(viewport={'width': width, 'height': 900})
            errors = []; writes = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: writes.append(request.url) if request.method == 'POST' and '/releases/' in request.url else None)
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').first.click()
            page.get_by_role('tab', name='成果审查', exact=True).click()
            page.get_by_role('tab', name='发布审查', exact=True).click()
            page.get_by_role('button', name='查看发布审查', exact=True).click(timeout=3000)
            review = page.get_by_test_id('merchant-release-review')
            expect(review).to_contain_text(intent.digest)
            expect(review).to_contain_text('CUP')
            expect(review).to_contain_text('10.00 USD')
            expect(review).to_contain_text('18 个固定步骤')
            expect(review).to_contain_text(intent.images[0].image.sha256)
            assert writes == []
            approve = page.get_by_role('button', name='批准这份发布内容', exact=True)
            expect(approve).to_be_disabled()
            page.get_by_label('我已审查目标站点、商品、图片和代码版本').check()
            approve.click()
            expect(review.get_by_role('heading', name='商家发布审查 · 已批准', exact=True)).to_be_visible()
            expect(approve).to_be_disabled()
            assert len(writes) == 1 and writes[0].endswith('/approve')
            page.get_by_role('button', name='发布下一步', exact=True).click()
            expect(review.get_by_role('alert')).to_contain_text('隔离执行环境')
            assert len(writes) == 2 and writes[-1].endswith('/publish')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert errors == []
            page.screenshot(path=str(tmp_path / f'merchant-review-{width}.png'), full_page=True)
            browser.close()
    finally:
        server.should_exit = True; thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
