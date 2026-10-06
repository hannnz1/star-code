"""The board stays compact while task editing and review use accessible panels."""
import os
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from muse.main import create_app
from muse.commerce.api import TaskDraftInput
from muse.commerce.task_drafts import CommerceDraftService


@pytest.mark.parametrize('width', [1440, 900, 390])
def test_board_composer_and_review_panels_preserve_input_and_read_only_navigation(workflow, monkeypatch, width):
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
            page = browser.new_page(viewport={'width': width, 'height': 1000})
            errors, writes = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='团队任务', exact=True).click()
            board = page.get_by_test_id('commerce-task-board')
            expect(board).to_be_visible()
            expect(page.get_by_label('团队任务目标', exact=True)).not_to_be_visible()
            expect(page.locator('.commerce-plan-detail')).not_to_be_visible()
            page.on('request', lambda request: writes.append(request.url) if request.method != 'GET' else None)
            board.get_by_role('button', name='新建任务', exact=True).click()
            composer = page.locator('dialog[open]')
            expect(composer).to_be_visible()
            composer.get_by_label('任务标题', exact=True).fill('春季商家目标')
            composer.get_by_label('团队任务目标', exact=True).fill('保留中文商家需求，不调用模型。')
            # The background language control is inert while a modal is open.
            composer.get_by_role('button', name='English', exact=True).click()
            expect(page.get_by_role('dialog', name='Create merchant task', exact=True)).to_be_visible()
            expect(composer.get_by_label('Task title', exact=True)).to_have_value('春季商家目标')
            expect(composer.get_by_label('Team task goal', exact=True)).to_have_value('保留中文商家需求，不调用模型。')
            composer.get_by_role('button', name='Back to board', exact=True).click()
            expect(board.get_by_role('button', name='New task', exact=True)).to_be_focused()
            board.get_by_role('button', name='New task', exact=True).click()
            expect(page.get_by_label('Task title', exact=True)).to_have_value('春季商家目标')
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog')).not_to_be_visible()
            output = root / 'work/workspace-panels-20261006'
            output.mkdir(parents=True, exist_ok=True)
            board.screenshot(path=str(output / f'board-{width}.png'))
            page.screenshot(path=str(output / f'workspace-{width}.png'))
            board.locator('.commerce-board-card').first.click()
            detail = page.get_by_role('dialog', name='Task details', exact=True)
            expect(detail).to_be_visible()
            expect(detail.get_by_test_id('plan-next-action')).to_be_visible()
            detail.get_by_role('tab', name='Results review', exact=True).click()
            expect(detail.get_by_test_id('commerce-review-summary')).to_be_visible()
            expect(detail.get_by_test_id('commerce-follow-ups')).not_to_be_visible()
            overview_tab = detail.get_by_role('tab', name='Review overview', exact=True)
            overview_tab.focus()
            page.keyboard.press('ArrowRight')
            expect(detail.get_by_role('tab', name='Code changes and integration', exact=True)).to_be_focused()
            expect(detail.locator('#review-panel-code')).to_be_visible()
            page.keyboard.press('Home')
            expect(overview_tab).to_be_focused()
            expect(detail.get_by_test_id('commerce-review-summary')).to_be_visible()
            detail.screenshot(path=str(output / f'review-{width}.png'))
            detail.get_by_role('button', name='中文', exact=True).click()
            page.locator('dialog[open]').screenshot(path=str(output / f'review-zh-{width}.png'))
            page.screenshot(path=str(output / f'workspace-review-zh-{width}.png'))
            page.locator('dialog[open]').get_by_role('button', name='English', exact=True).click()
            detail.get_by_role('tab', name='Next tasks', exact=True).click()
            expect(detail.get_by_test_id('commerce-follow-ups')).to_be_visible()
            detail.get_by_role('button', name='Read follow-up suggestions', exact=True).click()
            expect(detail.get_by_role('status').filter(has_text='No suggestions available')).to_be_visible()
            if width in (1440, 900):
                # Leaving this panel during its read must not submit a paid model job.
                held = []
                capacity_url = '**/api/commerce/projects/*/task-capacity'
                page.route(capacity_url, lambda route: held.append(route))
                page.once('dialog', lambda dialog: dialog.accept())
                detail.get_by_role('button', name='Generate more suggestions with current model', exact=True).click()
                detail.get_by_role('tab', name='Task progress', exact=True).click()
                if width == 900:
                    detail.get_by_role('tab', name='Next tasks', exact=True).click()
                assert held
                with page.expect_response(lambda response: response.url.endswith('/task-capacity')):
                    held[0].fulfill(status=200, content_type='application/json', body=json.dumps({
                        'project_revision': service.repo.get_project(plan.project_id).revision}))
                page.unroute(capacity_url)
                expect(detail.locator('#task-panel-next button').filter(has_text='Generate more suggestions with current model')).to_be_enabled()
                assert writes == []
                if width == 1440:
                    detail.get_by_role('tab', name='Next tasks', exact=True).click()
            detail.get_by_role('button', name='Back to board', exact=True).click()
            page.get_by_role('button', name='Store connection', exact=True).click()
            expect(page.get_by_role('dialog', name='Store connection', exact=True)).to_be_visible()
            page.keyboard.press('Escape')
            assert errors == [] and writes == []
            assert len(tasks.list()) == 1
            assert service.repo.get_plan(plan.id, project_id=plan.project_id).revision == plan.revision
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            # Editing another saved draft cannot erase the independent new-task input.
            project = service.repo.get_project(plan.project_id)
            existing = CommerceDraftService(service.repo, service).create(project.id, TaskDraftInput(
                kind='build_site', title='Existing draft', prompt='Prepare site',
                expected_project_revision=project.revision, client_request_id='panel-draft'))
            board.get_by_role('button', name='Refresh board').click()
            board.get_by_role('button', name='Existing draft', exact=False).click()
            page.get_by_label('Task title', exact=True).fill('Edited draft')
            page.get_by_role('button', name='Save draft changes', exact=True).click()
            page.get_by_role('button', name='Back to board', exact=True).click()
            board.get_by_role('button', name='New task', exact=True).click()
            expect(page.get_by_label('Task title', exact=True)).to_have_value('春季商家目标')
            page.keyboard.press('Escape')
            board.get_by_role('button', name='Edited draft', exact=False).click()
            page.once('dialog', lambda dialog: dialog.accept())
            page.get_by_role('button', name='Join background queue', exact=True).click()
            expect(page.get_by_role('dialog', name='Task details', exact=True)).to_be_visible()
            expect(page.get_by_role('dialog', name='Create merchant task', exact=True)).not_to_be_visible()
            assert len(tasks.list()) == 2
            assert len(writes) == 2 and writes[0].endswith('/task-drafts/' + existing.id) and writes[1].endswith('/task-drafts/batch')
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
