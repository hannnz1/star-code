from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page
from playwright.sync_api import expect
from time import monotonic


def _wait_for_held_save(page, held):
    # Busy UI renders before route.fetch completes. Pump Playwright until the
    # intercepted response is ready, while leaving the browser response pending.
    deadline = monotonic() + 10
    while not held and monotonic() < deadline:
        page.wait_for_timeout(20)
    assert len(held) == 1, 'Product save request was not intercepted'
    return held[0]


def test_uploaded_media_is_available_without_refresh_and_keeps_form_input(crew_page):
    import io
    from PIL import Image
    page,runtime,plan,root=crew_page
    page.get_by_role('button',name='商品',exact=True).click()
    editor=page.get_by_test_id('product-editor')
    editor.get_by_label('商品名称',exact=True).fill('Keep my product input')
    pixels=io.BytesIO();Image.new('RGB',(20,20),'blue').save(pixels,format='PNG')
    expect(page.get_by_label('商品图片',exact=True)).to_be_enabled()
    with page.expect_response(lambda response:'/media?' in response.url and response.request.method=='POST') as uploaded:
        page.get_by_label('商品图片',exact=True).set_input_files({'name':'fresh-media.png','mimeType':'image/png','buffer':pixels.getvalue()})
    assert uploaded.value.status==201,uploaded.value.text()
    expect(page.get_by_label('使用图片 fresh-media.png',exact=True)).to_be_visible()
    expect(editor.get_by_label('选择商品图片',exact=True).locator('option').filter(has_text='fresh-media.png')).to_have_count(1)
    expect(editor.get_by_label('商品名称',exact=True)).to_have_value('Keep my product input')
    page.get_by_role('button',name='网站',exact=True).click()
    design=page.get_by_test_id('store-editor')
    design.get_by_role('button',name='准备或更新编辑草稿',exact=True).click()
    expect(design.get_by_label('区块图片',exact=True).locator('option').filter(has_text='fresh-media.png')).to_have_count(1)


def test_product_form_preserves_input_and_saves_unpublished_version(crew_page):
    page,runtime,plan,root=crew_page
    page.get_by_role('button',name='商品',exact=True).click()
    editor=page.get_by_test_id('product-editor')
    editor.get_by_label('SKU',exact=True).fill('FORM-CUP')
    editor.get_by_label('商品名称',exact=True).fill('Merchant cup')
    editor.get_by_label('商品价格',exact=True).fill('12.30')
    editor.get_by_label('商品库存',exact=True).fill('4')
    page.reload()
    expect(editor.get_by_label('商品名称',exact=True)).to_have_value('Merchant cup')
    editor.get_by_role('button',name='保存商品草稿',exact=True).click()
    expect(editor.get_by_role('status')).to_have_text('商品草稿已保存，尚未上架')
    from muse.commerce.repository import CommerceRepository
    repo=CommerceRepository(runtime)
    latest=repo.list_product_imports(plan.project_id)
    matches=[p for batch in latest for p in batch.result.drafts if p.sku=='FORM-CUP']
    assert len(matches)==1 and str(matches[0].price)=='12.30' and matches[0].stock==4
    assert not any(p.products and any(d.sku=='FORM-CUP' for d in p.products) for p in repo.list_plans(plan.project_id))


def test_product_source_cannot_change_while_save_response_is_pending(crew_page):
    page, runtime, plan, root = crew_page
    page.get_by_role('button', name='商品', exact=True).click()
    editor = page.get_by_test_id('product-editor')
    editor.get_by_label('SKU', exact=True).fill('PENDING-CUP')
    editor.get_by_label('商品名称', exact=True).fill('Pending cup')
    held = []
    def hold(route):
        held.append((route, route.fetch()))
    page.route('**/product-draft', hold)
    editor.get_by_role('button', name='保存商品草稿', exact=True).click()
    expect(editor.get_by_role('button', name='正在保存…', exact=True)).to_be_visible()
    # Choosing another source here would disconnect the saved import from the visible form.
    expect(editor.get_by_label('选择商品草稿')).to_be_disabled()
    route, response = _wait_for_held_save(page, held)
    route.fulfill(response=response)
    expect(editor.get_by_role('status')).to_have_text('商品草稿已保存，尚未上架')
    expect(editor.get_by_label('选择商品草稿')).to_be_enabled()
    expect(editor.get_by_label('商品名称', exact=True)).to_have_value('Pending cup')


def test_old_product_save_cannot_mark_returned_store_session_saved(crew_page):
    from muse.commerce.repository import CommerceRepository
    page, runtime, plan, root = crew_page
    repo = CommerceRepository(runtime)
    first = repo.get_project(plan.project_id)
    second = repo.create_project(first.workspace_id, first.brief.model_copy(update={'brand_name':'Other shop'}), 'product-response-other')
    page.reload()
    page.get_by_role('button', name='商品', exact=True).click()
    editor = page.get_by_test_id('product-editor')
    editor.get_by_label('SKU', exact=True).fill('OLD-SESSION')
    editor.get_by_label('商品名称', exact=True).fill('Old request')
    held = []
    def hold(route):
        held.append((route, route.fetch()))
    page.route('**/product-draft', hold)
    editor.get_by_role('button', name='保存商品草稿', exact=True).click()
    expect(editor.get_by_role('button', name='正在保存…', exact=True)).to_be_visible()
    page.get_by_label('切换店铺', exact=True).select_option(second.id)
    page.get_by_role('button', name='商品', exact=True).click()
    expect(editor.get_by_label('商品名称', exact=True)).to_have_value('')
    page.get_by_label('切换店铺', exact=True).select_option(first.id)
    page.get_by_role('button', name='商品', exact=True).click()
    expect(editor.get_by_label('商品名称', exact=True)).to_have_value('Old request')
    # The returned store session is editable, not an acknowledgement of the old request.
    editor.get_by_label('商品名称', exact=True).fill('New session input')
    route, response = _wait_for_held_save(page, held)
    route.fulfill(response=response)
    # Drain the fetch callback without arbitrary sleeps.
    page.wait_for_load_state('networkidle')
    expect(editor.get_by_role('status')).to_have_count(0)
    expect(editor.get_by_label('商品名称', exact=True)).to_have_value('New session input')
