from playwright.sync_api import expect
from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page


def test_platform_setup_and_confirmation_are_distinct_actions(crew_page):
    page, _, _, root = crew_page
    page.get_by_role('button', name='网站', exact=True).click()
    panel = page.get_by_test_id('store-readiness')
    for key, tab in [('shipping', 'shipping'), ('payment', 'checkout')]:
        row = panel.get_by_test_id(f'readiness-{key}')
        expect(row.get_by_role('link', name='打开店铺配置', exact=True)).to_have_attribute(
            'href', f'https://shop.test/wp-admin/admin.php?page=wc-settings&tab={tab}')
        expect(row.get_by_role('link', name='确认店铺配置', exact=True)).to_have_attribute(
            'href', 'https://shop.test/wp-admin/options-general.php?page=muse-connector')
        expect(row).to_contain_text('购买验证仍需独立运行')
        expect(row).to_contain_text('需独立验证')
    page.get_by_role('button', name='English', exact=True).first.click()
    expect(panel.get_by_role('link', name='Confirm store configuration', exact=True)).to_have_count(2)
    expect(panel).to_contain_text('buyer verification must still run separately')
    out = root / 'work/visual-editor-evidence/readiness-guidance'
    out.mkdir(exist_ok=True)
    for width in [1440, 390]:
        page.set_viewport_size({'width': width, 'height': 1000})
        panel.screenshot(path=str(out / f'configuration-actions-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_old_shipping_quote_cannot_appear_in_another_store(crew_page):
    from muse.commerce.repository import CommerceRepository
    page, runtime, plan, _ = crew_page
    repo = CommerceRepository(runtime)
    first = repo.get_project(plan.project_id)
    second = repo.create_project(first.workspace_id,
        first.brief.model_copy(update={'brand_name': 'Second Store', 'currency': 'AUD'}),
        'shipping-second-store')
    page.reload()
    expect(page.get_by_label('切换店铺', exact=True).locator('option').filter(has_text='Second Store')).to_have_count(1)
    page.get_by_role('button', name='网站', exact=True).click()
    panel = page.get_by_test_id('store-readiness')
    panel.get_by_text('运费预估工具', exact=True).click()
    pending = []
    page.route('**/shipping-quote', lambda route: pending.append(route))
    panel.get_by_role('button', name='计算预估', exact=True).click()
    expect(panel.get_by_role('button', name='计算预估', exact=True)).to_be_visible()
    page.get_by_label('切换店铺', exact=True).select_option(second.id)
    page.get_by_role('button', name='网站', exact=True).click()
    assert pending
    for route in pending:
        route.fulfill(json={'amount': '6.00', 'currency': 'USD'})
    page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    expect(panel.get_by_role('status')).to_have_count(0)
    # Synchronize with a fresh valid request after the delayed previous result.
    page.unroute('**/shipping-quote')
    panel.get_by_label('购物车小计', exact=True).fill('50.00')
    panel.get_by_role('button', name='计算预估', exact=True).click()
    expect(panel.get_by_role('status')).to_have_text('0.00 AUD')
    page.get_by_label('切换店铺', exact=True).select_option(first.id)
    page.get_by_role('button', name='网站', exact=True).click()
    expect(panel.get_by_role('status')).to_have_count(0)
