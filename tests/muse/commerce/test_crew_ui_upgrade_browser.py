from pathlib import Path
import socket, threading, time
import pytest, uvicorn
from playwright.sync_api import expect, sync_playwright
from muse.main import create_app

@pytest.fixture
def crew_page(workflow, monkeypatch):
    service, repo, plan, worker = workflow
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    worker.settings.allowed_origins.append(origin)
    app = create_app(worker.settings)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={'width':1440,'height':1000})
            page.goto(origin)
            page.get_by_label('本地访问令牌').fill(worker.settings.access_token.get_secret_value())
            page.get_by_role('button', name='进入工作台', exact=True).click()
            # Authentication does not await the lazy merchant module and its
            # initial project fetch. Every scenario starts from a loaded store.
            expect(page.get_by_test_id('merchant-overview')).to_be_visible(timeout=15000)
            yield page, repo, plan, root
            browser.close()
    finally:
        server.should_exit=True; thread.join(timeout=5); app.state.repository.db.engine.dispose()


def test_merchant_navigation_and_developer_input(crew_page):
    page, repo, plan, root = crew_page
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    expect(page.locator('.crew-recent-tasks button').first).to_be_visible()
    out=root/'work/crew-ui-upgrade-20261006';out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'overview-1440-zh.png'))
    expect(page.locator('.studio-navigation')).to_have_count(0)
    expect(page.locator('.sidebar').get_by_role('button', name='记忆管理', exact=True)).to_have_count(0)
    page.get_by_role('button', name='开发空间', exact=True).click()
    page.locator('.composer textarea').fill('保留独立编程输入')
    page.get_by_role('button', name='概览', exact=True).click()
    page.get_by_role('button', name='开发空间', exact=True).click()
    expect(page.locator('.composer textarea')).to_have_value('保留独立编程输入')
    page.get_by_role('button', name='设置', exact=True).click()
    page.get_by_role('button', name='偏好与记忆', exact=True).click()
    expect(page.get_by_role('dialog', name='记忆管理')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.get_by_role('button', name='偏好与记忆', exact=True)).to_be_focused()


def test_flows_manager_draft_and_list(crew_page):
    page, repo, plan, root = crew_page
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    writes=[]
    page.on('request', lambda r: writes.append(r.url) if r.method != 'GET' else None)
    page.get_by_role('button', name='商品', exact=True).click()
    page.locator('#merchant-products-csv').fill('sku,name,price,currency,stock,category,description,image_names\nA,Cup,12,USD,2,Cups,Good,')
    page.get_by_role('button', name='团队任务', exact=True).click()
    page.get_by_role('button', name='列表', exact=True).click()
    expect(page.locator('.commerce-board-grid')).to_have_attribute('data-view', 'list')
    page.get_by_role('button', name='商品', exact=True).click()
    expect(page.locator('#merchant-products-csv')).to_have_value('sku,name,price,currency,stock,category,description,image_names\nA,Cup,12,USD,2,Cups,Good,')
    page.reload()
    expect(page.locator('#merchant-products-csv')).to_have_value('sku,name,price,currency,stock,category,description,image_names\nA,Cup,12,USD,2,Cups,Good,')
    page.get_by_role('button', name='店长助手', exact=True).click()
    expect(page.get_by_role('dialog', name='店长助手', exact=True)).to_contain_text('Cup Store')
    page.get_by_label('交给店长的目标').fill('准备新品内容，先保存草稿')
    page.get_by_role('button', name='准备计划草稿', exact=True).click()
    expect(page.get_by_role('button', name='查看计划草稿', exact=True)).to_be_visible()
    out=root/'work/crew-ui-upgrade-20261006';out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'manager-1440-zh.png'))
    page.get_by_role('dialog',name='店长助手',exact=True).get_by_role('button',name='English',exact=True).click()
    expect(page.get_by_text('Store manager confirms the product scope and store context',exact=True)).to_be_visible()
    page.get_by_role('dialog',name='Store manager',exact=True).get_by_role('button',name='中文',exact=True).click()
    assert len(writes)==1 and writes[0].endswith('/task-drafts')
    page.get_by_role('button', name='查看计划草稿', exact=True).click()
    expect(page.locator('dialog[open]')).to_contain_text('准备新品内容，先保存草稿')
    assert len(writes)==1


@pytest.mark.parametrize('width',[1440,1280,900,390,360])
def test_responsive_language_and_history(crew_page,width):
    page, repo, plan, root = crew_page
    page.set_viewport_size({'width':width,'height':1000})
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    page.get_by_role('button', name='网站', exact=True).click()
    expect(page.get_by_test_id('build-site-flow')).to_be_visible()
    page.get_by_role('button', name='English', exact=True).first.click()
    expect(page.locator('html')).to_have_attribute('lang','en')
    page.reload()
    expect(page.get_by_test_id('build-site-flow')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    out=root/'work/crew-ui-upgrade-20261006'; out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/f'website-{width}-en.png'))


def test_assistant_restores_workflow_and_budget(crew_page):
    page, repo, plan, root = crew_page
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    page.get_by_role('button', name='商品', exact=True).click()
    page.get_by_role('button', name='店长助手', exact=True).click()
    dialog=page.get_by_role('dialog', name='店长助手', exact=True)
    dialog.get_by_label('交给店长的目标').fill('这次只准备新品')
    dialog.locator('select').first.select_option('launch_products')
    dialog.get_by_label('共享模型请求上限').fill('3')
    page.keyboard.press('Escape')
    page.reload()
    page.get_by_role('button', name='店长助手', exact=True).click()
    expect(dialog.locator('select').first).to_have_value('launch_products')
    expect(dialog.get_by_label('共享模型请求上限')).to_have_value('3')
    expect(dialog.get_by_label('交给店长的目标')).to_have_value('这次只准备新品')


def test_task_route_survives_refresh_and_back(crew_page):
    page, repo, plan, root = crew_page
    page.get_by_role('button', name='团队任务', exact=True).click()
    board=page.get_by_test_id('commerce-task-board')
    board.locator('.commerce-board-card').first.click()
    page.get_by_role('button', name='打开执行日志与审批', exact=False).first.click()
    expect(page.locator('.task-heading')).to_be_visible()
    assert '?task=' in page.url
    page.reload()
    expect(page.locator('.task-heading')).to_be_visible()
    page.go_back()
    expect(board).to_be_visible()
    expect(page.locator('.conversation')).not_to_be_visible()


def test_project_revision_does_not_migrate_old_csv(crew_page):
    page, repo, plan, root = crew_page
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    page.get_by_role('button', name='商品', exact=True).click()
    page.get_by_label('商品 CSV').fill('old revision draft')
    page.get_by_role('button', name='设置', exact=True).click()
    page.get_by_label('风格要求', exact=True).fill('Updated style')
    page.get_by_role('button', name='保存品牌资料', exact=True).click()
    page.get_by_role('button', name='商品', exact=True).click()
    expect(page.get_by_label('商品 CSV')).to_have_value('')


def test_independent_store_drafts_and_browser_back(crew_page):
    from muse.commerce.models import SiteBrief
    from muse.commerce.repository import CommerceRepository
    page,repo,plan,root=crew_page
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    commerce=CommerceRepository(repo)
    original=commerce.get_project(plan.project_id)
    other=commerce.create_project(original.workspace_id,SiteBrief(brand_name='Second Store',language='en-US',currency='USD'),'other-ui-project')
    page.reload()
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    page.get_by_role('button', name='商品', exact=True).click()
    page.get_by_label('商品 CSV').fill('Store A draft')
    page.get_by_label('切换店铺').select_option(other.id)
    page.get_by_role('button', name='商品', exact=True).click()
    expect(page.get_by_label('商品 CSV')).to_have_value('')
    page.get_by_label('商品 CSV').fill('Store B draft')
    page.get_by_label('切换店铺').select_option(original.id)
    page.get_by_role('button', name='商品', exact=True).click()
    expect(page.get_by_label('商品 CSV')).to_have_value('Store A draft')
    page.go_back()
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    assert original.id in page.url


def test_connection_is_available_from_settings(crew_page):
    page,repo,plan,root=crew_page
    expect(page.get_by_test_id('merchant-overview')).to_be_visible()
    page.get_by_role('button',name='设置',exact=True).click()
    page.locator('.crew-settings').get_by_role('button',name='店铺连接',exact=True).click()
    expect(page.get_by_role('dialog',name='店铺连接',exact=True)).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.get_by_test_id('commerce-task-board')).to_be_visible()


def test_unsaved_team_form_restores_after_reload(crew_page):
    page,repo,plan,root=crew_page
    page.get_by_role('button',name='团队任务',exact=True).click()
    board=page.get_by_test_id('commerce-task-board')
    board.get_by_role('button',name='新建任务',exact=True).click()
    page.get_by_label('任务标题',exact=True).fill('Keep team proposal')
    page.get_by_label('团队任务目标',exact=True).fill('未启动的团队目标')
    page.get_by_label('共享模型请求上限',exact=True).fill('4')
    page.reload()
    board.get_by_role('button',name='新建任务',exact=True).click()
    expect(page.get_by_label('任务标题',exact=True)).to_have_value('Keep team proposal')
    expect(page.get_by_label('团队任务目标',exact=True)).to_have_value('未启动的团队目标')
    expect(page.get_by_label('共享模型请求上限',exact=True)).to_have_value('4')
    assert len(repo.list())==1


def test_long_title_and_error_screenshots(crew_page,workflow):
    from muse.commerce.api import TaskDraftInput
    from muse.commerce.task_drafts import CommerceDraftService
    page,repo,plan,root=crew_page
    service=workflow[0]
    title='夏季新品上线：核对商品事实与图片、页面展示和最终发布目标。'*4
    project=service.repo.get_project(plan.project_id)
    CommerceDraftService(service.repo,service).create(project.id,TaskDraftInput(
        kind='launch_products',title=title,prompt='Prepare products without starting a model',
        expected_project_revision=project.revision,client_request_id='ui-long-title'))
    page.set_viewport_size({'width':390,'height':1000})
    page.get_by_role('button',name='团队任务',exact=True).click()
    board=page.get_by_test_id('commerce-task-board')
    board.get_by_role('button',name='刷新看板',exact=True).click()
    expect(board.locator('.commerce-board-card-top strong').filter(has_text=title)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    out=root/'work/crew-ui-upgrade-20261006';out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'long-title-390-zh.png'),full_page=True)
    page.route('**/api/commerce/projects/*/plans',lambda route:route.fulfill(status=409,content_type='application/json',body='{"error":{"code":"RESOURCE_CONFLICT"}}'))
    board.get_by_role('button',name='刷新看板',exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='资料已更新')).to_be_visible()
    page.screenshot(path=str(out/'error-390-zh.png'),full_page=True)
from playwright.sync_api import expect

from muse.commerce.repository import CommerceRepository
from muse.commerce.models import SiteBrief


def test_store_archive_restore_delete(crew_page):
    page, runtime, plan, _ = crew_page
    repo = CommerceRepository(runtime)
    original = repo.get_project(plan.project_id)
    project = repo.create_project(original.workspace_id, SiteBrief(brand_name='Disposable', language='en-US', currency='USD'), 'disposable-ui')
    page.reload()
    page.get_by_label('切换店铺').select_option(project.id)
    page.get_by_role('button', name='设置', exact=True).click()
    page.get_by_role('button', name='归档店铺', exact=True).click()
    expect(page.get_by_label('切换店铺').locator('option', has_text='Disposable')).to_have_count(0)
    expect(page.get_by_test_id('archived-projects')).to_contain_text('Disposable')
    page.get_by_role('button', name='恢复店铺', exact=True).click()
    expect(page.get_by_label('切换店铺')).to_have_value(project.id)
    page.get_by_role('button', name='永久删除店铺', exact=True).click()
    dialog = page.get_by_role('dialog', name='永久删除店铺', exact=True)
    expect(dialog.get_by_role('button', name='确认永久删除', exact=True)).to_be_disabled()
    dialog.get_by_label('输入店铺名称确认').fill('wrong')
    expect(dialog.get_by_role('button', name='确认永久删除', exact=True)).to_be_disabled()
    dialog.get_by_label('输入店铺名称确认').fill('Disposable')
    page.evaluate("ids=>{sessionStorage.setItem('crew-draft:products:'+ids[0]+':1','deleted');sessionStorage.setItem('crew-draft:products:'+ids[1]+':1','keep');}", [project.id,original.id])
    dialog.get_by_role('button', name='确认永久删除', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.get_by_label('切换店铺').locator('option', has_text='Disposable')).to_have_count(0)
    assert page.evaluate("id=>sessionStorage.getItem('crew-draft:products:'+id+':1')",project.id) is None
    assert page.evaluate("id=>sessionStorage.getItem('crew-draft:products:'+id+':1')",original.id) == 'keep'
    page.reload()
    expect(page.get_by_label('切换店铺').locator('option', has_text='Disposable')).to_have_count(0)
    assert repo.get_project(original.id)


def test_busy_store_shows_reason(crew_page):
    page, _, _, _ = crew_page
    page.get_by_role('button', name='设置', exact=True).click()
    page.get_by_role('button', name='归档店铺', exact=True).click()
    expect(page.get_by_test_id('project-management').get_by_role('alert')).to_contain_text('运行中任务')
    expect(page.get_by_label('切换店铺')).not_to_have_value('')


def test_developer_mode_guidance_preserves_input_and_does_not_start(crew_page):
    page, _, _, root = crew_page
    writes=[]
    page.on('request',lambda r:writes.append(r.url) if r.method!='GET' else None)
    page.get_by_role('button',name='开发空间',exact=True).click()
    text=page.locator('.composer textarea')
    expect(text).to_have_attribute('placeholder','你想完成什么？')
    page.locator('.mode-row').get_by_role('button',name='网页研究',exact=True).click()
    expect(page.get_by_test_id('mode-guidance')).to_contain_text('记录来源')
    expect(text).to_have_attribute('placeholder','输入网页链接和你想研究的问题…')
    page.get_by_role('button',name='填入示例',exact=True).click()
    expect(text).not_to_have_value('')
    text.fill('保留我的任务目标')
    page.locator('.mode-row').get_by_role('button',name='编程助手',exact=True).click()
    expect(text).to_have_value('保留我的任务目标')
    expect(page.locator('.mode-row').get_by_role('button',name='编程助手',exact=True)).to_have_attribute('aria-pressed','true')
    expect(page.get_by_role('button',name='填入示例',exact=True)).to_be_disabled()
    page.get_by_label('团队协作',exact=True).check()
    expect(page.get_by_test_id('mode-guidance')).to_contain_text('多个 AI 分工')
    page.get_by_role('button',name='English',exact=True).click()
    expect(text).to_have_value('保留我的任务目标')
    expect(page.get_by_role('button',name='Start task',exact=True)).to_be_visible()
    page.set_viewport_size({'width':390,'height':1000})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(root/'work/crew-ui-upgrade-20261006/developer-guidance-390-en.png'))
    assert writes==[]


def test_developer_workspace_context_and_settings_switch(crew_page):
    page, runtime, plan, root = crew_page
    original = CommerceRepository(runtime).get_project(plan.project_id)
    current_path = runtime.db.rows('SELECT path FROM workspaces WHERE id=:id',{'id':original.workspace_id})[0]['path']
    other_path = Path(current_path).parent/'another-workspace'
    other_path.mkdir()
    runtime.register_workspace(str(other_path),'Another workspace')
    page.reload()
    page.get_by_role('button',name='开发空间',exact=True).click()
    expect(page.locator('.composer').get_by_role('combobox',name='选择工作区',exact=True)).to_have_count(0)
    expect(page.get_by_test_id('developer-workspace')).to_contain_text(current_path)
    page.get_by_label('任务目标',exact=True).fill('保留任务输入')
    page.get_by_role('button',name='工作区设置',exact=True).click()
    page.get_by_role('dialog',name='工作区管理',exact=True).get_by_role('button',name='Another workspace',exact=False).click()
    expect(page.get_by_test_id('developer-workspace')).to_contain_text(str(other_path))
    expect(page.get_by_label('任务目标',exact=True)).to_have_value('保留任务输入')
    page.set_viewport_size({'width':390,'height':1000})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(root/'work/crew-ui-upgrade-20261006/developer-workspace-390-zh.png'))



def test_blueprint_current_editor_history_and_reload(crew_page):
    from muse.commerce.repository import CommerceRepository, encode
    from sqlalchemy import text
    page, runtime, team, root = crew_page
    repo = CommerceRepository(runtime)
    project = repo.get_project(team.project_id)
    draft = repo.create_site_blueprint(project.id, 'structure-old', project.revision)
    # Reproduce pre-fix historical duplicates without deleting any team records.
    old = draft.model_copy(update={'id':'old-duplicate'})
    with repo.db.transaction() as conn:
        conn.execute(text('INSERT INTO commerce_plans VALUES(:id,:project,:request,:digest,1,:data,NULL)'),
                     {'id':old.id,'project':project.id,'request':'old-duplicate','digest':'old','data':encode(old)})
    pending = []
    page.route('**/commerce/projects/*/plans', lambda route: pending.append(route))
    # The workbench may already have prefetched plans while opening overview.
    # Install the delayed route before a fresh page load to test the loader.
    page.reload()
    page.get_by_role('button', name='网站', exact=True).click()
    panel = page.get_by_test_id('site-blueprint')
    expect(panel.get_by_role('button', name='生成结构草稿',exact=True)).to_be_disabled()
    for _ in range(100):
        if pending: break
        page.wait_for_timeout(20)
    assert pending
    for route in pending: route.continue_()
    page.unroute('**/commerce/projects/*/plans')
    expect(panel.get_by_test_id('current-blueprint')).to_have_count(1)
    expect(panel.get_by_test_id('blueprint-history')).not_to_have_attribute('open', '')
    expect(panel.get_by_role('button', name='生成结构草稿',exact=True)).to_have_count(0)
    assert len(repo.list_plans(project.id)) == 3  # team + two standalone, all retained
    panel.get_by_role('button',name='编辑结构草稿',exact=True).click()
    panel.get_by_label('页面名称 1',exact=True).fill('Pet Home')
    panel.get_by_label('页面路径 1',exact=True).fill('pet-home')
    panel.get_by_label('导航名称 1',exact=True).fill('Pets')
    panel.get_by_role('button',name='保存结构草稿',exact=True).click()
    expect(panel.get_by_role('status')).to_contain_text('结构草稿已保存')
    page.reload()
    panel = page.get_by_test_id('site-blueprint')
    expect(panel.get_by_test_id('current-blueprint')).to_contain_text('Pet Home')
    expect(panel.get_by_test_id('current-blueprint')).to_contain_text('Pets')
    panel.get_by_role('button',name='编辑结构草稿',exact=True).click()
    expect(panel.get_by_label('页面路径 1',exact=True)).to_have_value('pet-home')
    page.set_viewport_size({'width':390,'height':1000})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    out=root/'work/crew-ui-upgrade-20261006';out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'blueprint-editor-390-zh.png'))
    panel.get_by_role('button',name='取消',exact=True).click()
    assert len(repo.list_plans(project.id)) == 3
