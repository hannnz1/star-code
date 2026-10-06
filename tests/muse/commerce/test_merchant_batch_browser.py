import json
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


@pytest.mark.parametrize('outcome', ['success', 'unknown', 'no_progress', 'leave', 'leave_detail'])
def test_explicit_batch_stops_on_unknown_or_no_progress_without_resending(merchant_review, workflow, monkeypatch, outcome):  # noqa: F811
    """Real browser and approvals; deliberately simulated publication DTOs only."""
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    repo, _project, plan, intent, evidence, connection, clock, _ = merchant_review
    approvals = MerchantReleaseApprovalRepository(repo, clock=lambda: clock[0])
    approvals.stage_review(intent, evidence, connection=connection, expected_plan_revision=plan.revision)
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    settings = workflow[3].settings
    settings.allowed_origins.append(origin)
    app = create_app(settings)
    app.state.commerce_merchant_approvals = approvals
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
            page = browser.new_page(viewport={'width': 390, 'height': 900})
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台').click()
            page.get_by_role('button', name='团队任务', exact=True).click()
            page.get_by_test_id('commerce-task-board').locator('.commerce-board-card').filter(has_text=plan.id[:8]).click()
            page.get_by_role('tab', name='成果审查', exact=True).click()
            page.get_by_role('tab', name='发布审查', exact=True).click()
            page.get_by_role('button', name='查看发布审查', exact=True).click()
            page.get_by_label('我已审查目标站点、商品、图片和代码版本').check()
            page.get_by_role('button', name='批准这份发布内容', exact=True).click()
            review = page.get_by_test_id('merchant-release-review')
            expect(review.get_by_role('heading', name='商家发布审查 · 已批准', exact=True)).to_be_visible()
            from muse.commerce.merchant_review import MerchantReviewRepository
            current = repo.get_plan(plan.id, project_id=plan.project_id)
            view = MerchantReviewRepository(approvals).read(plan.project_id, plan.id, intent.digest, current.revision).model_dump(mode='json')
            commands = []
            pending = []
            def publish(route):
                command = json.loads(route.request.post_data)
                commands.append(command)
                assert command == {'expected_revision': view['plan_revision']}
                if outcome == 'unknown' and len(commands) == 2:
                    view['phase'] = 'NEEDS_RECONCILIATION'
                    view['last_attempt'] = {'index': 1, 'operation_id': 'simulated-unknown', 'state': 'NEEDS_RECONCILIATION', 'effect_verified': False}
                elif outcome != 'no_progress':
                    view['completed_steps'] += 1
                    view['plan_revision'] += 1
                    view['last_attempt'] = {'index': view['completed_steps'] - 1, 'operation_id': 'simulated', 'state': 'SUCCEEDED', 'effect_verified': True}
                    view['phase'] = 'PUBLISHING'
                    if view['completed_steps'] == view['total_steps']:
                        view['status'], view['phase'] = 'consumed', 'SUCCEEDED'
                if outcome in ('leave', 'leave_detail') and len(commands) == 1:
                    pending.append(route)
                else:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(view))
            page.route('**/releases/*/publish', publish)
            batch = page.get_by_role('button', name='连续发布已批准步骤', exact=True)
            expect(batch).to_be_enabled()
            batch.click(timeout=3000)
            if outcome in ('leave', 'leave_detail'):
                # Hold the first receipt until the user leaves the publishing panel.
                page.get_by_role('tab', name='任务进度' if outcome == 'leave_detail' else '审查概览', exact=True).click()
                assert len(pending) == 1
                pending[0].fulfill(status=200, content_type='application/json', body=json.dumps(view))
                if outcome == 'leave_detail':
                    page.get_by_role('tab', name='成果审查', exact=True).click()
                else:
                    page.get_by_role('tab', name='发布审查', exact=True).click()
                expect(review.get_by_role('status')).to_contain_text('已停止后续步骤')
                assert len(commands) == 1
                expect(batch).to_be_enabled()  # A new batch requires another explicit click.
            elif outcome == 'success':
                expect(review).to_contain_text('执行进度：18 / 18', timeout=20000)
                assert len(commands) == 18
            elif outcome == 'unknown':
                expect(review).to_contain_text('发送结果未知，请只读核对。后续步骤已停止。')
                assert len(commands) == 2
            else:
                expect(review.get_by_role('alert')).to_contain_text('进度未得到确认')
                assert len(commands) == 1
            if outcome not in ('leave', 'leave_detail'):
                expect(batch).to_be_disabled()
            page.wait_for_timeout(250)
            assert len(commands) == (18 if outcome == 'success' else 2 if outcome == 'unknown' else 1)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.repository.db.engine.dispose()
