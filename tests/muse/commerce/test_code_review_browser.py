import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.commerce.code_bridge import ThemeCodeBridge
from muse.main import create_app
from muse.tools.context import ExecutionContext


@pytest.mark.parametrize('width', [1440, 768, 390])
def test_merchant_sees_sealed_code_diff_without_publish_or_verified_claim(workflow, monkeypatch, width, tmp_path):
    service, repo, plan, worker = workflow
    manager_task = repo.claim_next('manager')
    manager = ExecutionContext(worker.settings, repo, manager_task, 'manager', enforce_budgets=True)
    service.submit(manager, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'manager-output')
    service.dispatch_step(manager, next(s.id for s in plan.steps if s.role == 'site_developer'))
    child = repo.claim_next('developer')
    bridge = ThemeCodeBridge(ExecutionContext(worker.settings, repo, child, 'developer', enforce_budgets=True))
    original = bridge.read('style.css')
    saved = bridge.write('style.css', original['content'] + '\nbody { color: #123456; }\n', original['draft_hash'])
    sealed = bridge.seal(saved['draft_hash'])
    import hashlib
    import io

    from PIL import Image

    from muse.commerce.code_bridge import load_captured_code
    from muse.commerce.preview import PreviewFrame, StagePreviewCapture
    from muse.commerce.preview_repository import PreviewRepository
    current = service.repo.get_plan(plan.id, project_id=plan.project_id)
    project = service.repo.get_project(plan.project_id)
    code = load_captured_code(service.repo, current)
    png = io.BytesIO(); Image.new('RGB', (390, 900), 'white').save(png, format='PNG'); content = png.getvalue()
    target = project.environment_refs[0]
    # Explicit diagnostic UI fixture, not a real CMS or trusted approval report.
    PreviewRepository(service.repo).save(project.id, current.id, current.revision,
        StagePreviewCapture(code.source_digest, 'f' * 64, target.connector_ref, target.public_url,
            (PreviewFrame('home', 390, 900, hashlib.sha256(content).hexdigest(), content),),
            {'pages': False, 'layout_desktop': False, 'layout_tablet': False, 'layout_mobile': True, 'links': False},
            ('PAGE_CAPTURE_FAILED:shop:1440',), False))
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    settings = bridge.ctx.settings
    settings.allowed_origins.append(origin)
    app = create_app(settings)
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
            page.get_by_label('本地访问令牌').fill(settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').first.click()
            page.get_by_role('tab', name='成果审查', exact=True).click()
            page.get_by_role('tab', name='代码差异与整合', exact=True).click()
            page.get_by_role('button', name='查看主题代码差异').click(timeout=5000)
            card = page.get_by_test_id('theme-code-review')
            expect(card).to_contain_text(sealed['code_revision'])
            expect(card).to_contain_text('+body { color: #123456; }')
            expect(card).to_contain_text('网站验收和发布尚未完成')
            page.get_by_role('tab', name='页面预览', exact=True).click()
            page.locator('#review-panel-preview').get_by_role('button', name='查看站点预览', exact=True).click(timeout=5000)
            preview = page.get_by_test_id('store-preview')
            expect(preview).to_contain_text('尚未通过完整验收')
            page.get_by_role('button', name='首页 · 手机 390px', exact=True).click()
            image = page.get_by_role('img', name='首页预览 · 390px', exact=True)
            expect(image).to_be_visible()
            assert image.evaluate('(image) => image.naturalWidth') == 390
            assert page.get_by_role('button', name='发布', exact=True).count() == 0
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(tmp_path / f'code-review-{width}.png'), full_page=True)
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
