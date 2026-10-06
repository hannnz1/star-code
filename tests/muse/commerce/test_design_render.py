import pytest
from muse.commerce.design_repository import DesignRepository
from muse.commerce.theme import render_site_files, validate_theme_files


def test_design_rejects_protocol_relative_link():
    from muse.commerce.design_models import SectionProps
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SectionProps(link='//evil/')
    assert SectionProps(link='/shop/').link == '/shop/'


def test_theme_rejects_protocol_relative_link(workflow):
    service, runtime, team, worker = workflow
    files = render_site_files(team.blueprint, team.products)
    files['templates/front-page.html'] += b'\n<a href="//evil/">External target</a>'
    with pytest.raises(ValueError, match='Unsupported link target'):
        validate_theme_files(files)


def test_theme_rejects_external_link_hidden_in_block_attributes(workflow):
    from muse.commerce.theme import block
    service, runtime, team, worker = workflow
    files = render_site_files(team.blueprint, team.products)
    files['parts/header.html'] += block('navigation-link', {'label':'Unsafe', 'url':'//evil/'}).encode()
    with pytest.raises(ValueError, match='Unsupported block attribute'):
        validate_theme_files(files)


def test_theme_rejects_external_resource_hidden_in_theme_settings(workflow):
    import json
    service, runtime, team, worker = workflow
    files = render_site_files(team.blueprint, team.products)
    settings = json.loads(files['theme.json'])
    settings.setdefault('styles', {})['background'] = {'backgroundImage': {'url':'//evil/a.png'}}
    files['theme.json'] = json.dumps(settings).encode()
    with pytest.raises(ValueError, match='Unsupported block attribute path'):
        validate_theme_files(files)


def test_design_compiles_and_source_is_frozen(workflow):
    service,runtime,team,worker=workflow
    project=service.repo.get_project(team.project_id)
    designs=DesignRepository(service.repo)
    doc=designs.get_or_create(project.id,project.revision)
    doc.home_sections[0].props.title='<script>alert(1)</script>'
    doc.home_sections[0].props.text='Pet stories'
    doc.home_sections[0].props.button_label='Shop pets'
    doc=designs.save(project.id,project.revision,doc.revision,'render-edit',doc)
    plan=service.create_workflow(project.id,'build_site','Build this design','design-workflow',project.revision)
    assert plan.blueprint.required_settings['store_design']['revision'] == doc.revision
    files=render_site_files(plan.blueprint,plan.products)
    assert b'Pet stories' in files['templates/front-page.html']
    assert b'<script>' not in files['templates/front-page.html']
    assert b'woocommerce/checkout' in files['templates/page-checkout.html']
    validate_theme_files(files)
    doc.home_sections[0].props.title='New version'
    designs.save(project.id,project.revision,doc.revision,'later',doc)
    assert service.repo.get_plan(plan.id,project_id=project.id).state == 'STALE'
    assert plan.blueprint.required_settings['store_design']['home_sections'][0]['props']['text'] == 'Pet stories'


@pytest.mark.parametrize('overlap', [False, True])
def test_design_preserves_disjoint_manual_code(workflow, overlap):
    import base64,time
    from muse.commerce.code_integration import CommerceCodeIntegration,source_files
    from muse.commerce.restore import ProjectRestorer
    from muse.commerce.models import CommerceCodeHead
    from muse.commerce.repository import digest
    from muse.commerce.theme import build_file_archive
    service,runtime,team,worker=workflow
    project=service.repo.get_project(team.project_id)
    original=render_site_files(team.blueprint,team.products)
    original['style.css']+=b'\n/* reviewed manual customization */\n'
    if overlap:
        original['templates/front-page.html'] = original['templates/front-page.html'].replace(b'<h1', b'<h2').replace(b'</h1>', b'</h2>')
    package,archive=build_file_archive(original,code_revision='d'*40,content_hash=team.content_hash)
    head=CommerceCodeHead(project_id=project.id,plan_id=team.id,source_id='manual-source',code_revision='d'*40,revision=1,updated_at=time.time())
    with service.repo.db.transaction() as conn:
        CommerceCodeIntegration._save(conn,'manual-source',project.id,None,'restored_theme_source',{'package':package.model_dump(mode='json'),'archive_base64':base64.b64encode(archive).decode(),'deployment_verified':False})
        CommerceCodeIntegration._save(conn,digest([project.id,'local-code-head']),project.id,None,'local_code_head',head.model_dump(mode='json'))
    designs=DesignRepository(service.repo);doc=designs.get_or_create(project.id,project.revision)
    doc.home_sections[0].props.title='Merchant design with custom code'
    designs.save(project.id,project.revision,doc.revision,'manual-design',doc)
    if overlap:
        from muse.commerce.errors import CommerceFailure
        with pytest.raises(CommerceFailure) as error:
            service.create_workflow(project.id,'build_site','Merge merchant design','merged-design',project.revision)
        assert error.value.public.code == 'RESOURCE_CONFLICT'
        source = ProjectRestorer(service.repo).theme_source(project.id, 'manual-source')
        assert source_files(source) == original
        return
    plan=service.create_workflow(project.id,'build_site','Merge merchant design','merged-design',project.revision)
    source=ProjectRestorer(service.repo).theme_source(project.id,plan.blueprint.required_settings['restored_theme_source']['id'])
    files=source_files(source)
    assert b'reviewed manual customization' in files['style.css']
    assert b'Merchant design with custom code' in files['templates/front-page.html']


def test_design_export_restore_remaps_images_and_requires_new_source(workflow):
    import io,base64
    from PIL import Image
    from muse.commerce.media import MediaRepository
    from muse.commerce.export import ProjectExporter
    from muse.commerce.restore import ProjectRestorer
    service, runtime, team, worker = workflow
    project = service.repo.get_project(team.project_id)
    pixels = io.BytesIO(); Image.new('RGB',(8,8),'blue').save(pixels,format='PNG')
    image = MediaRepository(service.repo).upload(project.id,'hero.png','image/png',pixels.getvalue(),'hero-upload',project.revision)
    designs = DesignRepository(service.repo); doc = designs.get_or_create(project.id,project.revision)
    doc.home_sections[0].props.media_id = image.id
    doc.home_sections[0].props.title = 'Merchant-owned hero'
    designs.save(project.id,project.revision,doc.revision,'exportable',doc)
    archive = base64.b64decode(ProjectExporter(service.repo).download_project(project.id,project.revision).archive_base64)
    restorer = ProjectRestorer(service.repo)
    result = restorer.restore(project.workspace_id,archive,'restore-design')
    assert restorer.restore(project.workspace_id,archive,'restore-design') == result
    restored = designs.get(result.project.id)
    assert restored.home_sections[0].props.title == 'Merchant-owned hero'
    assert restored.home_sections[0].props.media_id != image.id
    assert restored.home_sections[0].props.media_id in result.media_ids
    assert restored.blueprint_plan_id == 'restored-unbound'
    assert result.project.environment_refs == [] and result.deployment_verified is False
