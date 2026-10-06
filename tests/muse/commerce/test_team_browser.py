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


@pytest.mark.parametrize('width', [1440, 390])
def test_team_preparation_ui_queues_real_tasks_and_shows_connection_errors(workflow, monkeypatch, width, tmp_path):
    service, repo, plan, worker = workflow
    project = service.repo.get_project(plan.project_id)
    csv = 'sku,name,price,currency,stock,category,description,image_names\n' + ''.join(
        f'BUILD-{index},Cup {index},12.30,USD,4,,,\n' for index in range(5))
    batch = service.repo.import_products(project.id, csv, 'build-five-products', project.revision)
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
            page.get_by_role('button', name='店铺连接', exact=True).click()
            page.get_by_text('已保存店铺上下文', exact=True).wait_for(timeout=3000)
            assert '1 件商品' not in page.locator('.commerce-connection').inner_text()
            page.get_by_role('button', name='刷新店铺上下文', exact=True).click()
            page.locator('.commerce-connection').get_by_role('alert').filter(has_text='店铺服务').wait_for()
            close_panel(page)
            page.get_by_test_id('commerce-task-board').get_by_role('button', name='新建任务', exact=True).click()
            page.get_by_label('团队任务目标', exact=True).fill('Prepare another shop proposal')
            page.get_by_label('共享模型请求上限', exact=True).fill('8')
            page.get_by_label('建站商品批次（可选）', exact=True).select_option(batch.id)
            page.get_by_role('button', name='启动三角色准备任务', exact=True).click()
            expect(page.get_by_test_id('commerce-task-board').locator('.commerce-board-card')).to_have_count(2)
            expect(page.get_by_role('button', name='刷新团队状态', exact=True)).to_have_count(1)
            created = next(p for p in service.repo.list_plans(plan.project_id) if p.id != plan.id)
            close_panel(page)
            page.get_by_label('搜索商家任务').fill(created.id[:8])
            expect(page.get_by_test_id('commerce-task-board').locator('.commerce-board-card')).to_have_count(1)
            close_panel(page)
            page.get_by_label('搜索商家任务').fill('')
            close_panel(page)
            page.get_by_test_id('commerce-task-board').get_by_role('button', name=f'搭建独立站 #{plan.id[:8]}', exact=False).click()
            page.locator('.commerce-plan-detail').get_by_text('技术明细与版本',exact=True).click()
            assert plan.id[:8] in page.locator('.commerce-plan-detail').inner_text()
            close_panel(page)
            page.get_by_test_id('commerce-task-board').get_by_role('button', name=f'搭建独立站 #{created.id[:8]}', exact=False).click()
            assert len(repo.list()) == 2
            assert created.products == batch.result.drafts and len(created.products) == 5
            assert all(task.checkpoint.get('model_requests', 0) == 0 for task in repo.list())
            assert next(s.task_id for s in created.steps if s.role == 'store_manager')[:8] in page.locator('.commerce-plan-detail').inner_text()
            expect(page.locator('.commerce-plan-detail')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.reload()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            expect(page.get_by_test_id('commerce-task-board').locator('.commerce-board-card')).to_have_count(2)
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').filter(has_text=created.id[:8]).click()
            expect(page.get_by_role('button', name='刷新团队状态', exact=True)).to_have_count(1)
            evidence = tmp_path / 'screenshots'
            evidence.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(evidence / f'team-{width}.png'), full_page=True)
            manager_task = next(s.task_id for s in created.steps if s.role == 'store_manager')
            page.get_by_role('button', name=f'打开执行日志与审批 · {manager_task[:8]}').click()
            expect(page.locator('.task-heading')).to_be_visible()
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()


def test_merchant_board_draft_archive_restore_start_and_rename(workflow, monkeypatch, tmp_path):
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
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').get_by_role('button', name='新建任务', exact=True).click()
            page.get_by_label('任务标题', exact=True).fill('秋季建站')
            page.get_by_label('团队任务目标', exact=True).fill('Prepare an autumn storefront')
            page.get_by_role('button', name='保存任务草稿').click()
            board = page.get_by_test_id('commerce-task-board')
            close_panel(page)
            board.get_by_role('button', name='更多筛选', exact=True).click()
            close_panel(page)
            board.get_by_label('筛选归档状态').select_option('all')
            expect(board.get_by_role('button', name='秋季建站', exact=False)).to_be_visible()
            assert len(tasks.list()) == 1
            board.get_by_role('button', name='秋季建站', exact=False).click()
            page.get_by_role('button', name='归档草稿').click()
            expect(board.locator('.commerce-board-card-id').filter(has_text='已归档')).to_be_visible()
            page.get_by_role('button', name='恢复草稿').click()
            expect(board.locator('.commerce-board-card-id').filter(has_text='草稿')).to_be_visible()
            close_panel(page)
            board.get_by_role('button', name='新建任务').click()
            page.get_by_label('任务标题', exact=True).fill('秋季商品')
            page.get_by_label('团队任务目标', exact=True).fill('Prepare product copy')
            page.get_by_role('button', name='保存任务草稿').click()
            close_panel(page)
            board.get_by_role('checkbox', name='选择草稿 秋季建站').check()
            close_panel(page)
            board.get_by_role('checkbox', name='选择草稿 秋季商品').check()
            close_panel(page)
            board.get_by_role('button', name='归档所选草稿').click()
            expect(board.get_by_role('checkbox', name='选择草稿 秋季建站')).to_have_count(0)
            close_panel(page)
            board.get_by_role('button', name='秋季建站', exact=False).click()
            page.get_by_role('button', name='恢复草稿').click()
            with page.expect_response(lambda response: response.url.endswith('/start') and response.request.method == 'POST') as started_response:
                page.get_by_role('button', name='启动这份草稿').click()
            started_plan_id = started_response.value.json()['plan_id']
            detail = page.locator(f'.commerce-plan-detail[data-plan-id="{started_plan_id}"]')
            expect(detail).to_have_count(1)
            expect(detail.get_by_test_id('commerce-review-summary')).to_have_count(1)
            expect(page.get_by_role('button', name='重命名任务')).to_be_visible()
            assert len(tasks.list()) == 2
            close_panel(page)
            board.get_by_role('button', name='秋季建站', exact=False).click()
            page.get_by_role('tab', name='成果审查', exact=True).click()
            with page.expect_response(lambda response: '/outputs' in response.url and response.request.method == 'GET') as output_response:
                detail.get_by_role('button', name='查看角色提交的成果').click()
            assert output_response.value.status == 200
            page.get_by_role('tab', name='任务进度', exact=True).click()
            page.get_by_label('任务显示标题').fill('秋季首页与商品目录')
            page.get_by_role('button', name='重命名任务').click()
            expect(board.get_by_role('button', name='秋季首页与商品目录', exact=False)).to_be_visible()
            close_panel(page)
            page.get_by_role('button', name='刷新看板').click()
            expect(board.get_by_role('button', name='秋季首页与商品目录', exact=False)).to_be_visible()
            page.reload()
            page.get_by_role('button', name='概览', exact=True).click()
            page.get_by_label('切换店铺').select_option(label='Cup Store')
            page.get_by_role('button', name='团队任务', exact=True).click()
            expect(page.get_by_test_id('commerce-task-board').get_by_role('button', name='秋季首页与商品目录', exact=False)).to_be_visible()
            close_panel(page)
            page.get_by_test_id('commerce-task-board').get_by_role('button', name='秋季首页与商品目录', exact=False).click()
            page.on('dialog', lambda dialog: dialog.accept())
            page.get_by_role('button', name='取消团队任务').click()
            expect(page.get_by_test_id('commerce-task-board').locator('.commerce-board-card-id').filter(has_text='已取消')).to_be_visible()
            board = page.get_by_test_id('commerce-task-board')
            close_panel(page)
            board.get_by_role('checkbox', name='选择已结束任务 秋季首页与商品目录').check()
            close_panel(page)
            board.get_by_role('button', name='归档所选任务').click()
            close_panel(page)
            board.get_by_role('button', name='更多筛选', exact=True).click()
            close_panel(page)
            board.get_by_label('筛选归档状态').select_option('archived')
            expect(board.get_by_role('button', name='秋季首页与商品目录', exact=False)).to_be_visible()
            close_panel(page)
            board.get_by_role('button', name='秋季首页与商品目录', exact=False).click()
            page.get_by_role('button', name='恢复此任务').click()
            expect(board.get_by_role('button', name='秋季首页与商品目录', exact=False)).to_have_count(0)
            close_panel(page)
            board.get_by_label('筛选归档状态').select_option('current')
            expect(board.get_by_role('button', name='秋季首页与商品目录', exact=False)).to_be_visible()
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
