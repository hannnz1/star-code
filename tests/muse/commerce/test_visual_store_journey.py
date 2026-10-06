"""Measured local editing benchmark; excludes model and remote build latency."""
import json,math,time
from playwright.sync_api import expect
from tests.muse.commerce.test_crew_ui_upgrade_browser import crew_page


def test_twenty_sections_thirty_edit_and_save_samples(crew_page):
    from muse.commerce.design_repository import DesignRepository
    from muse.commerce.repository import CommerceRepository
    from muse.commerce.design_models import StorySection,SectionProps
    page,runtime,plan,root=crew_page
    repo=CommerceRepository(runtime);project=repo.get_project(plan.project_id)
    designs=DesignRepository(repo);doc=designs.get_or_create(project.id,project.revision)
    doc.home_sections += [StorySection(id='section-'+str(i),kind='story',props=SectionProps(title='Section '+str(i))) for i in range(15)]
    designs.save(project.id,project.revision,doc.revision,'benchmark-sections',doc)
    page.get_by_role('button',name='网站',exact=True).click()
    editor=page.get_by_test_id('store-editor')
    expect(editor.get_by_label('区块标题',exact=True)).to_be_visible()
    edits=[];saves=[]
    for i in range(30):
        title='Measured merchant title '+str(i)
        started=time.perf_counter()
        editor.get_by_label('区块标题',exact=True).fill(title)
        expect(editor.locator('.crew-design-canvas h2').first).to_have_text(title)
        edits.append((time.perf_counter()-started)*1000)
        started=time.perf_counter()
        editor.get_by_role('button',name='保存网站草稿',exact=True).click()
        expect(editor.get_by_role('status')).to_have_text('已保存草稿')
        saves.append((time.perf_counter()-started)*1000)
    page.reload()
    expect(editor.get_by_label('区块标题',exact=True)).to_have_value('Measured merchant title 29')
    def p95(values):return sorted(values)[math.ceil(.95*len(values))-1]
    result={'sections':20,'samples':30,'measurement':'browser automation end-to-end local latency including Playwright overhead','edit_p95_ms':round(p95(edits),3),'save_p95_ms':round(p95(saves),3),'edit_samples_ms':edits,'save_samples_ms':saves,'model_calls':0}
    out=root/'work/visual-editor-evidence';out.mkdir(exist_ok=True)
    (out/'latency.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    editor.screenshot(path=str(out/'editor-1440-zh.png'))
    assert result['edit_p95_ms']<=200
    assert result['save_p95_ms']<=1000
