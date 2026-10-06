from playwright.sync_api import expect
import pytest
from muse.commerce.repository import CommerceRepository
from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page


def test_pending_blueprint_request_does_not_block_or_error_another_store(crew_page):
    page, runtime, plan, _ = crew_page
    repo = CommerceRepository(runtime)
    first = repo.get_project(plan.project_id)
    second = repo.create_project(first.workspace_id, first.brief.model_copy(update={'brand_name':'Blueprint Second'}),
        'blueprint-scope-second')
    page.reload()
    page.get_by_role('button', name='网站', exact=True).click()
    panel = page.get_by_test_id('site-blueprint')
    pending=[]
    page.route(f'**/projects/{first.id}/site-blueprint', lambda route:pending.append(route))
    panel.get_by_role('button', name='生成结构草稿', exact=True).click()
    page.get_by_label('切换店铺', exact=True).select_option(second.id)
    page.get_by_role('button', name='网站', exact=True).click()
    expect(panel.get_by_role('button', name='生成结构草稿', exact=True)).to_be_enabled()
    assert pending
    for route in pending:
        route.fulfill(status=422,json={'detail':{'code':'INPUT_INVALID','message':'Old store request failed','retryable':False}})
    page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    expect(panel.get_by_role('alert')).to_have_count(0)
    expect(panel.get_by_role('button', name='生成结构草稿', exact=True)).to_be_enabled()


@pytest.mark.parametrize('return_to_first',[False,True])
def test_late_successful_blueprint_cannot_write_back_after_store_switch(crew_page,return_to_first):
    page,runtime,plan,_=crew_page
    repo=CommerceRepository(runtime)
    first=repo.get_project(plan.project_id)
    second=repo.create_project(first.workspace_id,first.brief.model_copy(update={'brand_name':'Second success store'}),'scope-success-second')
    page.reload()
    page.get_by_role('button',name='网站',exact=True).click()
    pending=[]
    def hold(route):
        pending.append((route,route.fetch()))
        page.evaluate('window.__heldBlueprintResponse = true')
    page.route(f'**/projects/{first.id}/site-blueprint',hold)
    panel=page.get_by_test_id('site-blueprint')
    panel.get_by_role('button',name='生成结构草稿',exact=True).click()
    expect(panel.get_by_role('button',name='正在准备…',exact=True)).to_be_disabled()
    page.wait_for_function('() => window.__heldBlueprintResponse === true')
    assert pending and pending[0][1].status==201
    page.get_by_label('切换店铺',exact=True).select_option(second.id)
    page.get_by_role('button',name='网站',exact=True).click()
    expect(panel.get_by_role('button',name='生成结构草稿',exact=True)).to_be_enabled()
    if return_to_first:
        page.get_by_label('切换店铺',exact=True).select_option(first.id)
        page.get_by_role('button',name='网站',exact=True).click()
        expect(panel.get_by_test_id('current-blueprint')).to_have_count(1)
    pending[0][0].fulfill(response=pending[0][1])
    page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    expect(panel.get_by_role('status')).to_have_count(0)
    expect(panel.get_by_role('alert')).to_have_count(0)
    expect(panel.get_by_test_id('current-blueprint')).to_have_count(1 if return_to_first else 0)
