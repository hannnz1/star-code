from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page
from playwright.sync_api import expect


def initialize_editor(page, editor):
    # Initialization persists a version; wait for that actual API result before
    # asserting the editor content, rather than timing from the click alone.
    with page.expect_response(lambda response: response.request.method == 'POST'
                              and response.url.endswith('/design')) as response:
        editor.get_by_role('button', name='准备或更新编辑草稿', exact=True).click()
    assert response.value.status == 200, response.value.text()


def test_accepted_ai_edit_can_be_undone_as_a_new_saved_version(crew_page, workflow):
    import asyncio, json
    from muse.commerce.design_proposals import DesignProposalService
    from muse.commerce.design_repository import DesignRepository
    from muse.contracts import ModelEvent
    from test_agent_loop import ScriptedProvider
    page, runtime, plan, root = crew_page
    service, _, _, worker = workflow
    proposals = DesignProposalService(service.repo, worker.settings)
    page.get_by_role('button', name='网站', exact=True).click()
    editor = page.get_by_test_id('store-editor')
    initialize_editor(page, editor)
    title = editor.get_by_label('区块标题', exact=True)
    expect(title).to_have_value('Welcome to Cup Store')
    before = DesignRepository(service.repo).get(plan.project_id)
    after = before.home_sections[0].props.model_dump(mode='json')
    after['title'] = 'Reviewed AI headline'
    def generate(route):
        response = route.fetch()
        assert response.ok
        job = response.json()
        provider = ScriptedProvider([[ModelEvent(type='text', text=json.dumps(after))]])
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(proposals.run_once(provider, job_id=job['id']))).result(timeout=10)
        route.fulfill(json=proposals.read(plan.project_id, job['id']))
    page.route('**/design-proposals', generate)
    editor.get_by_label('区块修改要求').fill('Improve headline')
    editor.get_by_role('button', name='生成修改建议', exact=True).click()
    editor.get_by_role('button', name='接受修改', exact=True).click()
    expect(title).to_have_value('Reviewed AI headline')
    accepted = DesignRepository(service.repo).get(plan.project_id)
    assert accepted.revision == before.revision + 1
    expect(editor.get_by_role('button', name='撤销', exact=True)).to_be_enabled()
    editor.get_by_role('button', name='撤销', exact=True).click()
    expect(title).to_have_value('Welcome to Cup Store')
    # Undo is a local change; accepting already created a server version.
    assert DesignRepository(service.repo).get(plan.project_id) == accepted
    editor.get_by_role('button', name='保存网站草稿', exact=True).click()
    expect(editor.get_by_role('status').first).to_have_text('已保存草稿')
    restored = DesignRepository(service.repo).get(plan.project_id)
    assert restored.revision == accepted.revision + 1
    assert restored.home_sections == before.home_sections


def test_late_design_response_cannot_replace_another_store(crew_page):
    from muse.commerce.repository import CommerceRepository
    from muse.commerce.design_repository import DesignRepository
    page,runtime,plan,root=crew_page
    repo=CommerceRepository(runtime);first=repo.get_project(plan.project_id)
    designs=DesignRepository(repo);first_doc=designs.get_or_create(first.id,first.revision)
    second=repo.create_project(first.workspace_id,first.brief.model_copy(update={'brand_name':'Second store'}),'late-response-second-store')
    second_doc=designs.get_or_create(second.id,second.revision)
    pending=[]
    page.route(f'**/api/commerce/projects/{first.id}/design',lambda route:pending.append(route) if route.request.method=='GET' else route.continue_())
    page.reload()
    expect(page.get_by_label('切换店铺',exact=True).locator('option').filter(has_text='Second store')).to_have_count(1)
    page.get_by_role('button',name='网站',exact=True).click()
    expect(page.get_by_test_id('store-editor').get_by_role('status')).to_have_text('正在保存…')
    page.get_by_label('切换店铺',exact=True).select_option(second.id)
    page.get_by_role('button',name='网站',exact=True).click()
    title=page.get_by_test_id('store-editor').get_by_label('区块标题',exact=True)
    expect(title).to_have_value(second_doc.home_sections[0].props.title,timeout=15000)
    assert pending
    for route in pending:route.fulfill(json=first_doc.model_dump(mode='json'))
    expect(title).to_have_value(second_doc.home_sections[0].props.title)
    assert page.url.endswith('/'+second.id)
    assert designs.get(second.id)==second_doc


def test_cancel_browser_back_keeps_route_and_unsaved_draft(crew_page):
    page,repo,plan,root=crew_page
    page.get_by_role('button',name='网站',exact=True).click()
    editor=page.get_by_test_id('store-editor')
    initialize_editor(page, editor)
    expect(editor.get_by_label('区块标题',exact=True)).to_be_visible()
    editor.get_by_label('区块标题',exact=True).fill('Preserve when back is cancelled')
    dialogs=[]
    def record_dialog(dialog):
        dialogs.append(dialog.message);dialog.accept()
    page.on('dialog',record_dialog)
    page.get_by_role('button',name='网站',exact=True).click()
    assert dialogs==[]
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Preserve when back is cancelled')
    page.remove_listener('dialog',record_dialog)
    original=page.url
    page.once('dialog',lambda dialog:dialog.dismiss())
    page.evaluate('history.back()')
    expect(editor).to_be_visible()
    expect(page).to_have_url(original)
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Preserve when back is cancelled')
    page.once('dialog',lambda dialog:dialog.dismiss())
    page.get_by_label('切换店铺',exact=True).select_option('')
    expect(page.get_by_label('切换店铺',exact=True)).not_to_have_value('')
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Preserve when back is cancelled')


def test_cancelled_back_does_not_destroy_previous_history_entry(crew_page):
    page, runtime, plan, root = crew_page
    import re
    expect(page).to_have_url(re.compile('/#crew/overview/'+plan.project_id+'$'))
    overview_url = page.url
    page.get_by_role('button', name='网站', exact=True).click()
    editor = page.get_by_test_id('store-editor')
    initialize_editor(page, editor)
    editor.get_by_label('区块标题', exact=True).fill('Unsaved history test')
    website_url = page.url
    page.once('dialog', lambda dialog: dialog.dismiss())
    page.evaluate('history.back()')
    expect(page).to_have_url(website_url)
    expect(editor.get_by_label('区块标题', exact=True)).to_have_value('Unsaved history test')
    page.once('dialog', lambda dialog: dialog.accept())
    page.evaluate('history.back()')
    expect(page).to_have_url(overview_url)
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    page.evaluate('history.forward()')
    expect(page).to_have_url(website_url)
    expect(editor.get_by_label('区块标题', exact=True)).to_have_value('Welcome to Cup Store')
    page.get_by_role('button', name='商品', exact=True).click()
    product_url = page.url
    page.evaluate('history.back()')
    expect(page).to_have_url(website_url)
    editor.get_by_label('区块标题', exact=True).fill('Cancel forward draft')
    page.once('dialog', lambda dialog: dialog.dismiss())
    page.evaluate('history.forward()')
    expect(page).to_have_url(website_url)
    expect(editor.get_by_label('区块标题', exact=True)).to_have_value('Cancel forward draft')
    page.once('dialog', lambda dialog: dialog.accept())
    page.evaluate('history.forward()')
    expect(page).to_have_url(product_url)


def test_edit_save_reload_and_cancel(crew_page):
    page,repo,plan,root=crew_page
    page.get_by_role('button',name='网站',exact=True).click()
    editor=page.get_by_test_id('store-editor')
    initialize_editor(page, editor)
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Welcome to Cup Store',timeout=15000)
    editor.get_by_label('区块标题',exact=True).fill('Pet Home')
    expect(editor.get_by_role('status')).to_have_text('有未保存的修改')
    editor.get_by_role('button',name='保存网站草稿',exact=True).click()
    expect(editor.get_by_role('status')).to_have_text('已保存草稿')
    page.reload()
    expect(page.get_by_test_id('store-editor').get_by_label('区块标题',exact=True)).to_have_value('Pet Home')
    editor.get_by_label('区块标题',exact=True).fill('Unsaved')
    editor.get_by_role('button',name='撤销',exact=True).click()
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Pet Home')
    editor.get_by_role('button',name='重做',exact=True).click()
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Unsaved')
    editor.get_by_role('button',name='放弃修改',exact=True).click()
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Pet Home')
    for width in (1440,1280,900,390,360):
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    out=root/'work/visual-editor-evidence';out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'editor-360.png'))


def test_failed_save_preserves_input(crew_page):
    page,repo,plan,root=crew_page
    page.get_by_role('button',name='网站',exact=True).click()
    editor=page.get_by_test_id('store-editor')
    initialize_editor(page, editor)
    expect(editor.get_by_label('区块标题',exact=True)).to_be_visible()
    editor.get_by_label('区块标题',exact=True).fill('Keep my input')
    page.route('**/commerce/projects/*/design',lambda r:r.fulfill(status=409,json={'error':{'code':'RESOURCE_CONFLICT'}}) if r.request.method=='PATCH' else r.continue_())
    editor.get_by_role('button',name='保存网站草稿',exact=True).click()
    expect(editor.get_by_role('alert')).to_be_visible()
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Keep my input')
    expect(editor.get_by_role('status')).to_have_text('有未保存的修改')
    editor.get_by_role('button',name='放弃修改',exact=True).click()


def test_two_tabs_conflict_keeps_local_input_and_explicit_reload(crew_page):
    page,repo,plan,root=crew_page
    page.get_by_role('button',name='网站',exact=True).click()
    first=page.get_by_test_id('store-editor')
    initialize_editor(page, first)
    expect(first.get_by_label('区块标题',exact=True)).to_be_visible()
    token=page.evaluate("sessionStorage.getItem('muse-token')")
    second_context=page.context.browser.new_context(storage_state=page.context.storage_state())
    second_page=second_context.new_page()
    second_page.add_init_script("sessionStorage.setItem('muse-token',"+__import__('json').dumps(token)+")")
    second_page.goto(page.url)
    second=second_page.get_by_test_id('store-editor')
    # goto waits for the document, not lazy UI loading or authenticated API
    # initialization. The existing route already identifies the editor/store.
    expect(second.get_by_label('区块标题',exact=True)).to_be_visible(timeout=15000)
    second.get_by_label('区块标题',exact=True).fill('Unsaved second tab')
    first.get_by_label('区块标题',exact=True).fill('Saved first tab')
    first.get_by_role('button',name='保存网站草稿',exact=True).click()
    expect(first.get_by_role('status')).to_have_text('已保存草稿')
    second.get_by_role('button',name='保存网站草稿',exact=True).click()
    expect(second.get_by_role('alert')).to_be_visible()
    expect(second.get_by_label('区块标题',exact=True)).to_have_value('Unsaved second tab')
    second_page.once('dialog',lambda dialog:dialog.accept())
    second.get_by_role('button',name='重新读取已保存版本',exact=True).click()
    expect(second.get_by_label('区块标题',exact=True)).to_have_value('Saved first tab')
    second_context.close()
