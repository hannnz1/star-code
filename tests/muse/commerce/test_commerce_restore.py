import base64
import hashlib
import io
import json
import zipfile

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.export import ProjectExporter
from muse.commerce.repository import encode
from tests.muse.commerce.test_commerce_export import files, project  # noqa: F401


def repack(bundle, change, *, refresh=True):
    data = files(bundle)
    change(data)
    if refresh:
        manifest = json.loads(data['manifest.json'])
        manifest['files_manifest'] = [{'path': name, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
                                      for name, content in sorted(data.items()) if name != 'manifest.json']
        data['manifest.json'] = encode(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in data.items():
            archive.writestr(name, content)
    return output.getvalue()


def exported(repo, value):
    return base64.b64decode(ProjectExporter(repo).download_project(value.id, 1).archive_base64)


def test_restore_creates_new_offline_project_preserves_facts_and_is_idempotent(project):  # noqa: F811
    from muse.commerce.restore import ProjectRestorer
    repo, source = project
    restored = ProjectRestorer(repo).restore(source.workspace_id, exported(repo, source), 'restore-once')
    assert restored.project.id != source.id
    assert restored.project.revision == 1 and restored.project.environment_refs == []
    assert restored.project.brief == source.brief
    assert restored.deployment_verified is False and restored.requires_new_approval is True
    imports = repo.list_product_imports(restored.project.id)
    assert len(imports) == 1 and not imports[0].store_conflicts_checked
    assert imports[0].result.drafts[0] == repo.list_product_imports(source.id)[0].result.drafts[0]
    assert repo.list_plans(restored.project.id) == []
    assert ProjectRestorer(repo).restore(source.workspace_id, exported(repo, source), 'restore-once') == restored


@pytest.mark.parametrize('attack', ['checksum', 'extra', 'traversal', 'secret', 'currency', 'old_grant', 'bad_size'])
def test_invalid_archive_does_not_create_partial_project(project, attack):  # noqa: F811
    from muse.commerce.restore import ProjectRestorer
    repo, source = project
    bundle = ProjectExporter(repo).download_project(source.id, 1)
    def alter(data):
        if attack in {'extra', 'traversal', 'secret', 'old_grant'}:
            name = {'extra': 'extra.txt', 'traversal': '../outside.txt', 'secret': 'credentials.json',
                    'old_grant': 'grant.json'}[attack]
            data[name] = b'{}'
        elif attack == 'currency':
            value = json.loads(data['products.json'])
            value[0]['drafts'][0]['currency'] = 'EUR'
            data['products.json'] = encode(value).encode()
        elif attack == 'checksum':
            data['README.txt'] += b'tamper'
        else:
            manifest = json.loads(data['manifest.json'])
            manifest['files_manifest'][0]['bytes'] = True
            data['manifest.json'] = encode(manifest).encode()
    payload = repack(bundle, alter, refresh=attack not in {'checksum', 'bad_size'})
    before = len(repo.list_projects())
    with pytest.raises(CommerceFailure):
        ProjectRestorer(repo).restore(source.workspace_id, payload, 'invalid')
    assert len(repo.list_projects()) == before


def test_same_restore_request_cannot_replace_project_with_different_archive(project):  # noqa: F811
    from muse.commerce.restore import ProjectRestorer
    repo, source = project
    bundle = ProjectExporter(repo).download_project(source.id, 1)
    restorer = ProjectRestorer(repo)
    restorer.restore(source.workspace_id, base64.b64decode(bundle.archive_base64), 'same')
    changed = repack(bundle, lambda data: data.update({'README.txt': b'changed'}))
    with pytest.raises(CommerceFailure) as error:
        restorer.restore(source.workspace_id, changed, 'same')
    assert error.value.public.code == 'RESOURCE_CONFLICT'


def test_duplicate_zip_entry_and_oversize_archive_rejected_before_database(project):  # noqa: F811
    from muse.commerce.restore import ProjectRestorer
    repo, source = project
    output = io.BytesIO(exported(repo, source))
    with zipfile.ZipFile(output, 'a') as archive:
        archive.writestr('project.json', b'{}')
    with pytest.raises(CommerceFailure):
        ProjectRestorer(repo).restore(source.workspace_id, output.getvalue(), 'duplicate')
    with pytest.raises(CommerceFailure):
        ProjectRestorer(repo).restore(source.workspace_id, b'x' * (16 * 1024 * 1024 + 1), 'large')


def test_restore_remaps_clean_images_without_copying_connections_or_grants(project):  # noqa: F811
    from muse.commerce.media import MediaRepository
    from muse.commerce.restore import ProjectRestorer
    from tests.muse.commerce.test_product_media_api import picture
    repo, source = project
    media = MediaRepository(repo).upload(source.id, 'cup.png', 'image/png', picture(), 'image', 1)
    repo.import_products(source.id, 'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,10.00,USD,3,Cups,Ceramic,cup.png',
                         'image-batch', 1, media_ids=[media.id])
    result = ProjectRestorer(repo).restore(source.workspace_id, exported(repo, source), 'images')
    new_media = MediaRepository(repo).list(result.project.id)
    assert len(new_media) == 1 and new_media[0].id != media.id
    assert new_media[0].image.sha256 == media.image.sha256
    assert next(p for batch in repo.list_product_imports(result.project.id) for p in batch.result.drafts if p.sku == 'CUP').media_refs == [new_media[0].id]
    assert MediaRepository(repo).content(result.project.id, new_media[0].id)[1] == picture()
    assert result.project.environment_refs == [] and repo.list_plans(result.project.id) == []


def test_restore_preserves_exact_theme_bytes_as_unverified_source(project):  # noqa: F811
    from muse.commerce.models import CommercePlan, StoreSnapshot
    from muse.commerce.restore import ProjectRestorer
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.theme import build_site_archive
    repo, source = project
    blueprint = build_site_blueprint(source.brief, StoreSnapshot(project_id=source.id, environment='staging'))
    package, archive = build_site_archive(blueprint, [], code_revision='a' * 40)
    repo.save_plan(CommercePlan(id='theme', project_id=source.id, kind='build_site', blueprint=blueprint,
                              code_revision='a' * 40, content_hash=package.content_sha256), 0)
    result = ProjectRestorer(repo).restore(source.workspace_id, exported(repo, source), 'theme')
    captured = ProjectRestorer(repo).theme_source(result.project.id, result.theme_source_ids[0])
    assert captured.package == package and base64.b64decode(captured.archive_base64) == archive
    assert captured.deployment_verified is False
    with pytest.raises(CommerceFailure):
        ProjectRestorer(repo).theme_source(source.id, result.theme_source_ids[0])


def test_restore_api_is_authenticated_stream_bounded_and_creates_new_project(tmp_path):
    from fastapi.testclient import TestClient

    from muse.config import load_settings
    from muse.main import create_app
    settings = load_settings(data_dir=tmp_path / 'state', require_provider=False)
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + settings.access_token.get_secret_value()
        workspace = client.get('/api/workspaces').json()[0]['id']
        source = client.post('/api/commerce/projects', json={'workspace_id': workspace, 'client_request_id': 'shop',
                      'brief': {'brand_name': 'Shop', 'currency': 'USD', 'language': 'en'}}).json()
        bundle = client.get('/api/commerce/projects/' + source['id'] + '/export?revision=1').json()
        payload = base64.b64decode(bundle['archive_base64'])
        url = '/api/commerce/projects/restore'
        query = {'workspace_id': workspace, 'client_request_id': 'restore'}
        response = client.post(url, params=query, content=payload, headers={'Content-Type': 'application/zip'})
        assert response.status_code == 201, response.text
        restored = response.json()
        assert restored['project']['id'] != source['id'] and restored['project']['environment_refs'] == []
        assert client.post(url, params=query, content=payload, headers={'Content-Type': 'application/zip'}).json() == restored
        assert client.post(url, params=query, content=payload, headers={'Authorization': 'Bearer invalid'}).status_code == 401
        assert client.post(url, params=query, content=payload, headers={'Content-Type': 'text/plain'}).status_code == 422
        assert settings.access_token.get_secret_value() not in response.text


def test_restored_theme_survives_second_export_and_restore_without_active_plan(project):  # noqa: F811
    from muse.commerce.models import CommercePlan, StoreSnapshot
    from muse.commerce.restore import ProjectRestorer
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.theme import build_site_archive
    repo, source = project
    blueprint = build_site_blueprint(source.brief, StoreSnapshot(project_id=source.id, environment='staging'))
    package, archive = build_site_archive(blueprint, [], code_revision='a' * 40)
    repo.save_plan(CommercePlan(id='theme', project_id=source.id, kind='build_site', blueprint=blueprint,
                              code_revision='a' * 40, content_hash=package.content_sha256), 0)
    restorer = ProjectRestorer(repo)
    first = restorer.restore(source.workspace_id, exported(repo, source), 'first')
    second_bundle = ProjectExporter(repo).download_project(first.project.id, 1)
    second = restorer.restore(source.workspace_id, base64.b64decode(second_bundle.archive_base64), 'second')
    assert len(second.theme_source_ids) == 1
    recovered = restorer.theme_source(second.project.id, second.theme_source_ids[0])
    assert recovered.package == package and base64.b64decode(recovered.archive_base64) == archive
    assert repo.list_plans(second.project.id) == [] and second.project.environment_refs == []
