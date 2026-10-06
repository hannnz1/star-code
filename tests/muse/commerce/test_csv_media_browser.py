from playwright.sync_api import expect
from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page


def test_csv_save_waits_for_media_selection_to_finish_loading(crew_page):
    page, _, _, _ = crew_page
    held = []
    page.route('**/media', lambda route: held.append(route))
    page.reload()
    page.get_by_role('button', name='商品', exact=True).click()
    page.get_by_label('商品 CSV', exact=True).fill(
        'sku,name,price,currency,stock,category,description,image_names\nWAIT,Cup,12,USD,1,Cups,Good,')
    expect(page.get_by_text('正在读取图片…', exact=True)).to_be_visible()
    save = page.get_by_role('button', name='校验并保存草稿', exact=True)
    expect(save).to_be_disabled()
    assert held
    for route in held:
        route.fulfill(response=route.fetch())
    expect(page.get_by_text('正在读取图片…', exact=True)).to_have_count(0)
    expect(save).to_be_enabled()
    with page.expect_response(lambda response: response.url.endswith('/product-imports') and response.request.method == 'POST') as saved:
        save.click()
    assert saved.value.status == 201
    expect(page.get_by_text('WAIT', exact=True)).to_be_visible()
