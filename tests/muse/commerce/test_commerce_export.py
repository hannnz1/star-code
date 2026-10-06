import base64
import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.export import ProjectExporter
from muse.commerce.models import CommercePlan, SiteBrief, StoreSnapshot
from muse.commerce.repository import CommerceRepository
from muse.commerce.site import build_site_blueprint
from muse.commerce.theme import build_site_archive
from muse.config import load_settings
from muse.main import create_app
from muse.tasks.repository import TaskRepository


@pytest.fixture
def project(tmp_path):
    runtime = TaskRepository(tmp_path / 'state.sqlite3')
    root = tmp_path / 'workspace'
    root.mkdir()
    repo = CommerceRepository(runtime)
    value = repo.create_project(runtime.register_workspace(str(root))['id'],
                                SiteBrief(brand_name='Shop', language='en', currency='USD'), 'request')
    repo.create_site_blueprint(value.id, 'blueprint', value.revision)
    repo.import_products(value.id, 'sku,name,price,currency,stock,category,description,image_names\nSKU1,Cup,19.99,USD,3,Cups,Ceramic cup.,',
                         'products', value.revision)
    return repo, value


def files(bundle):
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(bundle.archive_base64))) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_export_preserves_facts_and_checksums_without_changing_database(project):
    repo, value = project
    before = repo.events(value.id)
    bundle = ProjectExporter(repo).download_project(value.id, value.revision)
    data = files(bundle)
    assert {'project.json', 'plans.json', 'products.json', 'manifest.json', 'README.txt'} <= set(data)
    assert json.loads(data['project.json'])['brief']['brand_name'] == 'Shop'
    product = json.loads(data['products.json'])[0]['drafts'][0]
    assert (product['sku'], product['price'], product['stock']) == ('SKU1', '19.99', 3)
    assert len(json.loads(data['plans.json'])[0]['blueprint']['pages']) == 7
    for record in bundle.manifest.files_manifest:
        assert hashlib.sha256(data[record['path']]).hexdigest() == record['sha256']
        assert len(data[record['path']]) == record['bytes']
    assert json.loads(data['manifest.json']) == bundle.manifest.model_dump(mode='json')
    assert repo.events(value.id) == before
    assert bundle == ProjectExporter(repo).download_project(value.id, value.revision)


def test_export_does_not_read_secret_customer_or_order_artifacts(project):
    repo, value = project
    with repo.db.transaction() as conn:
        for name in ('secret', 'customer', 'order', 'store_context'):
            conn.execute(text('INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,:kind,:digest,:data)'),
                         {'id': name, 'project': value.id, 'kind': name, 'digest': 'a' * 64,
                          'data': '{"password":"DO-NOT-EXPORT","email":"PRIVATE-CUSTOMER"}'})
    raw = b''.join(files(ProjectExporter(repo).download_project(value.id, value.revision)).values())
    assert b'DO-NOT-EXPORT' not in raw and b'PRIVATE-CUSTOMER' not in raw


def test_export_rejects_old_project_revision_and_unknown_project(project):
    repo, value = project
    repo.update_brief(value.id, value.brief.model_copy(update={'style': 'New'}), value.revision)
    with pytest.raises(CommerceFailure) as error:
        ProjectExporter(repo).download_project(value.id, value.revision)
    assert error.value.public.code == 'RESOURCE_CONFLICT'
    with pytest.raises(CommerceFailure) as error:
        ProjectExporter(repo).download_project('unknown', 1)
    assert error.value.public.code == 'NOT_FOUND'


def test_corrupted_import_identity_cannot_export_another_projects_data(project):
    repo, value = project
    with repo.db.transaction() as conn:
        row = conn.execute(text("SELECT id,data FROM commerce_artifacts WHERE kind='product_import'")).mappings().first()
        record = json.loads(row['data'])
        record['project_id'] = 'other-project'
        conn.execute(text('UPDATE commerce_artifacts SET data=:data WHERE id=:id'),
                     {'id': row['id'], 'data': json.dumps(record)})
    with pytest.raises(CommerceFailure) as error:
        ProjectExporter(repo).download_project(value.id, value.revision)
    assert error.value.public.code == 'RESOURCE_CONFLICT'


def test_export_record_limit_rejects_large_history(project):
    repo, value = project
    for index in range(100):
        repo.save_plan(CommercePlan(id=f'plan-{index}', project_id=value.id, kind='build_site'), 0)
    with pytest.raises(CommerceFailure) as error:
        ProjectExporter(repo).download_project(value.id, value.revision)
    assert error.value.public.code == 'INPUT_INVALID'


def test_export_separates_projects_and_excludes_stale_imports(project):
    repo, value = project
    other = repo.create_project(value.workspace_id, value.brief.model_copy(update={'brand_name': 'Other'}), 'other')
    assert json.loads(files(ProjectExporter(repo).download_project(other.id, 1))['products.json']) == []
    changed = repo.update_brief(value.id, value.brief.model_copy(update={'style': 'New'}), value.revision)
    assert json.loads(files(ProjectExporter(repo).download_project(value.id, changed.revision))['products.json']) == []


def test_export_theme_is_bound_to_exact_frozen_plan_and_uses_fixed_paths(project):
    repo, value = project
    blueprint = build_site_blueprint(value.brief, StoreSnapshot(project_id=value.id, environment='staging'))
    package, archive = build_site_archive(blueprint, [], code_revision='a' * 40)
    repo.save_plan(CommercePlan(id='../../private', project_id=value.id, kind='build_site', blueprint=blueprint,
                               state='REVIEW_REQUIRED', code_revision='a' * 40, content_hash=package.content_sha256), 0)
    data = files(ProjectExporter(repo).download_project(value.id, 1))
    assert data['themes/0001.zip'] == archive
    assert all(not name.startswith('/') and '..' not in name for name in data)
    metadata = json.loads(data['themes/0001.json'])
    assert metadata['plan_id'] == '../../private'
    assert metadata['verified_for_deployment'] is False


@pytest.mark.parametrize('change', ['content', 'code'])
def test_export_does_not_package_inconsistent_theme_source(project, change):
    repo, value = project
    blueprint = build_site_blueprint(value.brief, StoreSnapshot(project_id=value.id, environment='staging'))
    plan = CommercePlan(id='theme', project_id=value.id, kind='build_site', blueprint=blueprint,
                        code_revision='unknown' if change == 'code' else 'a' * 40, content_hash='b' * 64)
    repo.save_plan(plan, 0)
    with pytest.raises(CommerceFailure):
        ProjectExporter(repo).download_project(value.id, 1)


def test_export_api_requires_auth_and_returns_revision_bound_bundle(tmp_path):
    settings = load_settings(data_dir=tmp_path / 'state', require_provider=False)
    app = create_app(settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + settings.access_token.get_secret_value()
        workspace = client.get('/api/workspaces').json()[0]['id']
        created = client.post('/api/commerce/projects', json={'workspace_id': workspace, 'client_request_id': 'shop',
                              'brief': {'brand_name': 'Shop', 'currency': 'USD', 'language': 'en'}}).json()
        url = '/api/commerce/projects/' + created['id'] + '/export?revision=1'
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()['manifest']['revision'] == 1
        assert client.get(url, headers={'Authorization': 'Bearer invalid'}).status_code == 401
        assert client.get(url.replace('revision=1', 'revision=2')).status_code == 409
        assert settings.access_token.get_secret_value() not in response.text
