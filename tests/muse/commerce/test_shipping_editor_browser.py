from playwright.sync_api import expect
from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page


def open_editor(page):
    page.get_by_role('button', name='网站', exact=True).click()
    panel = page.get_by_test_id('site-blueprint')
    panel.get_by_role('button', name='生成结构草稿', exact=True).click()
    return page.get_by_test_id('shipping-rules-editor')


def test_shipping_form_save_reload_boundaries_and_language(crew_page):
    page, _, _, root = crew_page
    panel = open_editor(page)
    panel.get_by_label('配送区域名称 1', exact=True).fill('Australia')
    panel.get_by_label('国家代码 1', exact=True).fill('AU')
    panel.get_by_label('固定运费 1', exact=True).fill('6.00')
    panel.get_by_label('免运门槛 1', exact=True).fill('50.00')
    panel.get_by_role('button', name='保存配送草稿', exact=True).click()
    expect(page.get_by_test_id('site-blueprint').get_by_role('status')).to_have_text('配送草稿已保存，尚未在店铺生效。')
    panel.get_by_label('配送国家', exact=True).fill('AU')
    for subtotal, amount in [('49.99', '6.00 USD'), ('50.00', '0.00 USD'), ('50.01', '0.00 USD')]:
        panel.get_by_label('购物车小计', exact=True).fill(subtotal)
        panel.get_by_role('button', name='计算草稿运费', exact=True).click()
        expect(panel.get_by_role('status')).to_have_text(amount)
    panel.get_by_label('配送国家', exact=True).fill('NZ')
    panel.get_by_role('button', name='计算草稿运费', exact=True).click()
    expect(panel.get_by_role('status')).to_have_text('该国家不在配送范围内')
    page.reload()
    expect(panel.get_by_label('固定运费 1', exact=True)).to_have_value('6.00')
    page.get_by_role('button', name='English', exact=True).first.click()
    expect(panel).to_contain_text('Shipping rules draft')
    out = root/'work/visual-editor-evidence/navigation-shipping'
    out.mkdir(exist_ok=True)
    for width in [1440, 390]:
        page.set_viewport_size({'width': width, 'height': 1000})
        panel.screenshot(path=str(out/f'shipping-draft-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_shipping_error_preserves_inputs(crew_page):
    page, _, _, _ = crew_page
    panel = open_editor(page)
    panel.get_by_label('配送区域名称 1', exact=True).fill('Wrong country')
    panel.get_by_label('国家代码 1', exact=True).fill('ZZ')
    panel.get_by_label('固定运费 1', exact=True).fill('5.00')
    panel.get_by_role('button', name='保存配送草稿', exact=True).click()
    expect(panel.get_by_role('alert')).to_be_visible()
    expect(panel.get_by_label('配送区域名称 1', exact=True)).to_have_value('Wrong country')
    expect(panel.get_by_label('固定运费 1', exact=True)).to_have_value('5.00')
    expect(panel.get_by_role('button', name='保存配送草稿', exact=True)).to_be_enabled()


def test_project_revision_during_pending_shipping_response_does_not_lock_new_form(crew_page):
    page, _, _, _=crew_page
    panel=open_editor(page)
    panel.get_by_label('配送区域名称 1',exact=True).fill('United States')
    panel.get_by_label('国家代码 1',exact=True).fill('US')
    panel.get_by_label('固定运费 1',exact=True).fill('6.00')
    held=[]
    def hold(route):
        held.append((route,route.fetch()))
    page.route('**/shipping-rules',hold)
    panel.get_by_role('button',name='保存配送草稿',exact=True).click()
    expect(panel.get_by_role('button',name='正在保存…',exact=True)).to_be_disabled()
    page.get_by_role('button',name='设置',exact=True).click()
    page.get_by_label('风格要求',exact=True).fill('Updated project scope')
    with page.expect_response(lambda r:'/commerce/projects/' in r.url and r.request.method=='PATCH' and '/shipping-rules' not in r.url) as updated:
        page.get_by_role('button',name='保存品牌资料',exact=True).click()
    assert updated.value.status==200,updated.value.text()
    page.get_by_role('button',name='网站',exact=True).click()
    source=page.get_by_test_id('site-blueprint')
    expect(source.get_by_role('button',name='生成结构草稿',exact=True)).to_be_enabled()
    assert held and held[0][1].status==200
    held[0][0].fulfill(response=held[0][1])
    source.get_by_role('button',name='生成结构草稿',exact=True).click()
    expect(source.get_by_role('button',name='编辑结构草稿',exact=True)).to_be_enabled()
    expect(panel.get_by_label('配送区域名称 1',exact=True)).to_have_value('')
    expect(panel.get_by_label('配送区域名称 1',exact=True)).to_be_enabled()
