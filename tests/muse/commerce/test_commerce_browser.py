from tests.muse.commerce.browser_navigation import close_panel
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.config import load_settings
from muse.main import create_app


@pytest.mark.parametrize('width', [1440, 768, 390])
def test_merchant_prepare_import_reload_and_standalone_coding(tmp_path, monkeypatch, width):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    settings = load_settings(data_dir=tmp_path / 'state', require_provider=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
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
            page.get_by_role('button', name='概览', exact=True).click(timeout=2000)
            page.get_by_role('button', name='新建商家项目', exact=True).click()
            page.get_by_label('品牌名称', exact=True).fill('Green Cup Shop')
            page.get_by_role('button', name='保存商家项目', exact=True).click()
            page.get_by_role('heading', name='Green Cup Shop', exact=True).wait_for()
            page.get_by_role('button', name='网站', exact=True).click()
            expect(page.get_by_role('button', name='网站', exact=True)).to_have_attribute('aria-current', 'page')
            page.get_by_role('button', name='生成结构草稿', exact=True).click(timeout=2000)
            page.get_by_text('7 类页面 · 结构草稿，尚未建站', exact=True).wait_for()
            assert page.locator('.commerce-blueprint li').count() == 7
            page.get_by_role('button', name='商品', exact=True).click()
            from PIL import Image
            image = tmp_path / 'cup.png'
            Image.new('RGB', (8, 8), 'green').save(image, 'PNG')
            expect(page.get_by_label('商品图片', exact=True)).to_be_enabled()
            page.get_by_label('商品图片', exact=True).set_input_files(str(image))
            page.get_by_text('cup.png · 8 × 8', exact=True).wait_for()
            data = 'sku,name,price,currency,stock,category,description,image_names\nSKU1,Cup,19.99,CNY,3,Cups,Ceramic cup.,'
            data += 'cup.png'
            page.get_by_label('商品 CSV', exact=True).fill(data)
            page.get_by_role('button', name='校验并保存草稿', exact=True).click()
            page.get_by_role('alert').filter(has_text='币种').wait_for()
            assert app.state.commerce.list_product_imports(app.state.commerce.list_projects()[0].id) == []
            assert '商品 CSV' in page.locator('label').all_text_contents()
            page.get_by_label('商品 CSV', exact=True).fill(data.replace('CNY', 'USD'))
            page.get_by_role('button', name='校验并保存草稿', exact=True).click()
            page.get_by_role('button', name='商品', exact=True).click()
            page.get_by_text('文件校验通过：1 件商品；尚未发布', exact=True).wait_for()
            assert '19.99' in page.locator('main').inner_text()
            page.reload()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Green Cup Shop')
            page.get_by_role('button', name='商品', exact=True).click()
            page.get_by_text('文件校验通过：1 件商品；尚未发布', exact=True).wait_for()
            assert settings.access_token.get_secret_value() not in page.locator('body').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.emulate_media(reduced_motion='reduce')
            assert page.locator('.crew-sections').evaluate('(el) => getComputedStyle(el).animationName') == 'none'
            from muse.commerce.models import CommercePlan, StoreSnapshot
            from muse.commerce.site import build_site_blueprint
            from muse.commerce.theme import build_site_archive
            source_project = app.state.commerce.list_projects()[0]
            source_blueprint = build_site_blueprint(source_project.brief,
                StoreSnapshot(project_id=source_project.id, environment='staging'))
            source_package, theme_archive = build_site_archive(source_blueprint, [], code_revision='a' * 40)
            app.state.commerce.save_plan(CommercePlan(id='offline-theme', project_id=source_project.id, kind='build_site',
                blueprint=source_blueprint, code_revision='a' * 40, content_hash=source_package.content_sha256), 0)
            page.get_by_role('button', name='设置', exact=True).click()
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='下载项目资料', exact=True).click(timeout=2000)
            path = tmp_path / 'project.zip'
            downloaded.value.save_as(path)
            import json
            import zipfile
            with zipfile.ZipFile(path) as archive:
                products = json.loads(archive.read('products.json'))
                assert products[0]['drafts'][0]['price'] == '19.99'
                assert settings.access_token.get_secret_value().encode() not in archive.read('project.json')
            expect(page.get_by_text('项目资料已导出', exact=True)).to_be_visible()
            evidence = tmp_path / 'screenshots'
            evidence.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(evidence / f'merchant-{width}.png'), full_page=True)
            if width == 1440:
                # Finish A's POST only after B's real GET has completed. No fake API records.
                original = app.state.commerce.list_projects()[0]
                page.get_by_role('button', name='新建商家项目', exact=True).click()
                page.get_by_label('品牌名称', exact=True).fill('Other Store')
                page.get_by_role('button', name='保存商家项目', exact=True).click()
                page.get_by_role('heading', name='Other Store', exact=True).wait_for()
                other = next(p for p in app.state.commerce.list_projects() if p.id != original.id)
                page.get_by_label('切换店铺').select_option(label='Green Cup Shop')
                page.get_by_role('heading', name='Green Cup Shop', exact=True).wait_for()
                page.get_by_role('button', name='商品', exact=True).click()
                # The CSV below references this image. The merchant heading
                # does not imply its asynchronous media selection has loaded.
                expect(page.get_by_label('使用图片 cup.png', exact=True)).to_be_checked()
                held = []
                def hold(route):
                    if route.request.method == 'POST':
                        held.append((route, route.fetch()))
                        page.evaluate('window.__importIntercepted = true')
                    else:
                        route.continue_()
                path = '/api/commerce/projects/' + original.id + '/product-imports'
                page.route('**' + path, hold)
                page.evaluate('''() => {
                  const previous = window.fetch;
                  window.__importFinished = false;
                  window.__importIntercepted = false;
                  window.fetch = async (...args) => {
                    const response = await previous(...args);
                    if (args[1]?.method === 'POST' && String(args[0]).endsWith('/product-imports')) {
                      await response.clone().json();
                      setTimeout(() => {window.__importFinished = true;}, 0);
                    }
                    return response;
                  };
                }''')
                page.get_by_label('商品 CSV', exact=True).fill(data.replace('CNY', 'USD').replace('SKU1', 'SKU2'))
                page.get_by_role('button', name='校验并保存草稿', exact=True).click()
                page.wait_for_function('() => window.__importIntercepted === true')
                assert len(held) == 1
                assert held[0][1].status == 201, held[0][1].text()
                with page.expect_response(lambda r: r.url.endswith(other.id + '/product-imports') and r.request.method == 'GET'):
                    page.get_by_label('切换店铺').select_option(label='Other Store')
                page.get_by_role('heading', name='Other Store', exact=True).wait_for()
                held[0][0].fulfill(response=held[0][1])
                page.wait_for_function('() => window.__importFinished === true')
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                expect(page.get_by_text('SKU2', exact=True)).to_have_count(0)
                assert len(app.state.commerce.list_product_imports(original.id)) == 2
                assert app.state.commerce.list_product_imports(other.id) == []
            before_restore = {p.id for p in app.state.commerce.list_projects()}
            page.get_by_role('button', name='新建商家项目', exact=True).click()
            page.get_by_label('项目资料 ZIP', exact=True).set_input_files(str(path if width == 390 else tmp_path / 'project.zip'))
            page.get_by_role('button', name='恢复为新商家项目', exact=True).click()
            page.get_by_role('heading', name='Green Cup Shop', exact=True).wait_for()
            page.get_by_role('button', name='商品', exact=True).click()
            page.get_by_text('文件校验通过：1 件商品；尚未发布', exact=True).wait_for()
            restored = next(p for p in app.state.commerce.list_projects() if p.id not in before_restore)
            assert restored.environment_refs == []
            assert app.state.commerce.list_plans(restored.id) == []
            expect(page.get_by_text('cup.png · 8 × 8', exact=True)).to_be_visible()
            from muse.commerce.restore import ProjectRestorer
            theme_source = ProjectRestorer(app.state.commerce).list_theme_sources(restored.id)[0]
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').get_by_role('button', name='新建任务', exact=True).click()
            page.get_by_label('主题代码起点', exact=True).select_option(theme_source.id)
            with page.expect_download() as restored_download:
                page.get_by_role('button', name='下载恢复的主题代码', exact=True).click()
            recovered_path = tmp_path / 'recovered-theme.zip'
            restored_download.value.save_as(recovered_path)
            assert recovered_path.read_bytes() == theme_archive
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            close_panel(page)
            page.get_by_role('button', name='开发空间', exact=True).click()
            page.get_by_role('button', name='编程助手', exact=True).click()
            page.get_by_label('任务目标', exact=True).fill('Inspect the project entry point')
            page.get_by_role('button', name='开始任务', exact=True).click()
            page.get_by_role('heading', name='Inspect the project entry point', exact=True).wait_for()
            assert app.state.repository.list()[0].scenario == 'coding'
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
