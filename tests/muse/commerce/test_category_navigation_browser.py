from playwright.sync_api import expect
from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page


def test_category_navigation_save_order_reload_and_language(crew_page):
    page, repo, plan, root = crew_page
    from muse.commerce.repository import CommerceRepository
    repo=CommerceRepository(repo)
    project=repo.get_project(plan.project_id)
    repo.import_products(project.id,
        'sku,name,price,currency,stock,category,description,image_names\nC,Cup,12,USD,2,Cups,Good,\nT,Toy,10,USD,2,Toys,Good,',
        'navigation-browser-batch', project.revision)
    page.get_by_role('button', name='网站', exact=True).click()
    source=page.get_by_test_id('site-blueprint')
    source.get_by_role('button', name='生成结构草稿', exact=True).click()
    editor=page.get_by_test_id('category-navigation-editor')
    editor.get_by_label('分类导航 Cups', exact=True).check()
    editor.get_by_label('分类导航 Toys', exact=True).check()
    editor.get_by_label('分类导航名称 1', exact=True).fill('Shop cups')
    editor.get_by_label('分类导航上移 2', exact=True).click()
    shipping=page.get_by_test_id('shipping-rules-editor')
    shipping.get_by_label('配送区域名称 1', exact=True).fill('Unsaved shipping')
    shipping.get_by_label('国家代码 1', exact=True).fill('US')
    shipping.get_by_label('固定运费 1', exact=True).fill('6.00')
    editor.get_by_role('button', name='保存分类导航', exact=True).click()
    expect(source.get_by_role('status')).to_have_text('分类导航草稿已保存，尚未在店铺生效。')
    expect(shipping.get_by_label('配送区域名称 1', exact=True)).to_have_value('Unsaved shipping')
    editor.get_by_label('分类导航名称 1', exact=True).fill('Unsaved category label')
    assert shipping.locator('form').first.evaluate('(form)=>form.checkValidity()'), shipping.locator('input').evaluate_all('(inputs)=>inputs.map(i=>({label:i.getAttribute("aria-label"),value:i.value,invalid:!i.checkValidity()}))')
    with page.expect_response(lambda r: '/shipping-rules' in r.url and r.request.method=='PATCH') as saved:
        shipping.get_by_role('button',name='保存配送草稿',exact=True).click()
    assert saved.value.status==200,saved.value.text()
    expect(source.get_by_role('status')).to_have_text('配送草稿已保存，尚未在店铺生效。')
    expect(editor.get_by_label('分类导航名称 1',exact=True)).to_have_value('Unsaved category label')
    page.reload()
    expect(editor.get_by_label('分类导航名称 1', exact=True)).to_have_value('Unsaved category label')
    expect(editor.get_by_label('分类导航名称 2', exact=True)).to_have_value('Shop cups')
    page.get_by_role('button', name='English', exact=True).first.click()
    expect(editor).to_contain_text('Category navigation draft')
    for width in [1440,390]:
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        editor.screenshot(path=str(root/f'work/visual-editor-evidence/navigation-shipping/category-draft-{width}.png'))
