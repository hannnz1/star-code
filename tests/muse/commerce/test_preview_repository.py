import base64
import hashlib
import io
import json
from dataclasses import replace

import pytest
from PIL import Image
from sqlalchemy import text

from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.preview import PreviewFrame, StagePreviewCapture
from muse.commerce.repository import digest, encode
from tests.muse.commerce.test_release_approval import product_review  # noqa: F401


def capture_fixture(fixture):
    repo, _project, plan, _intent, _report, connection, _clock = fixture
    code = load_captured_code(repo, plan)
    output = io.BytesIO(); Image.new('RGB', (390, 900), 'white').save(output, format='PNG')
    content = output.getvalue()
    frame = PreviewFrame('home', 390, 900, hashlib.sha256(content).hexdigest(), content)
    return StagePreviewCapture(code.source_digest, 'f' * 64, connection.connection_id, connection.base_url, (frame,),
        {'pages': False, 'layout_desktop': False, 'layout_tablet': False, 'layout_mobile': True, 'links': False},
        ('PAGE_CAPTURE_FAILED:shop:1440',), False)


def test_diagnostic_preview_survives_restart_with_scoped_source_and_exact_png_without_approval(product_review):  # noqa: F811
    from muse.commerce.preview_repository import PreviewRepository
    repo, project, plan, *_ = product_review
    capture = capture_fixture(product_review)
    saved = PreviewRepository(repo).save(project.id, plan.id, plan.revision, capture)
    assert saved.site_verified is False and saved.passed is False
    assert saved.frames[0].kind == 'home' and saved.frames[0].width == 390
    restarted = PreviewRepository(repo)
    assert restarted.latest(project.id, plan.id, plan.revision) == saved
    png = restarted.image(project.id, plan.id, saved.id, saved.frames[0].id, plan.revision)
    assert base64.b64decode(png.png_base64) == capture.frames[0].content
    assert repo.db.rows('SELECT * FROM commerce_approvals') == []
    assert repo.get_plan(plan.id, project_id=project.id).state == 'REVIEW_REQUIRED'


@pytest.mark.parametrize('attack', ['source', 'target', 'connection', 'image_sha', 'dimensions', 'site_verified', 'passed', 'revision'])
def test_preview_refuses_inconsistent_capture_before_any_storage(product_review, attack):  # noqa: F811
    from muse.commerce.preview_repository import PreviewRepository
    repo, project, plan, *_ = product_review
    capture = capture_fixture(product_review)
    revision = plan.revision
    if attack == 'source': capture = replace(capture, source_digest='e' * 64)
    elif attack == 'target': capture = replace(capture, target_url='https://other.test')
    elif attack == 'connection': capture = replace(capture, connection_id='other')
    elif attack == 'image_sha': capture = replace(capture, frames=(replace(capture.frames[0], sha256='e' * 64),))
    elif attack == 'dimensions': capture = replace(capture, frames=(replace(capture.frames[0], width=1440),))
    elif attack == 'site_verified': capture = replace(capture, site_verified=True)
    elif attack == 'passed': capture = replace(capture, passed=True)
    else: revision += 1
    with pytest.raises(CommerceFailure):
        PreviewRepository(repo).save(project.id, plan.id, revision, capture)
    assert not repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind LIKE 'commerce_preview%'")


def test_preview_cannot_be_loaded_across_project_or_after_source_changed_or_image_corrupted(product_review):  # noqa: F811
    from muse.commerce.preview_repository import PreviewRepository
    repo, project, plan, *_ = product_review
    store = PreviewRepository(repo)
    saved = store.save(project.id, plan.id, plan.revision, capture_fixture(product_review))
    with pytest.raises(CommerceFailure):
        store.latest('other', plan.id, plan.revision)
    with repo.db.transaction() as conn:
        conn.execute(text('UPDATE commerce_artifacts SET digest=:bad WHERE id=:id'),
                     {'bad': 'e' * 64, 'id': saved.frames[0].id})
    with pytest.raises(CommerceFailure):
        store.image(project.id, plan.id, saved.id, saved.frames[0].id, plan.revision)
    changed = plan.model_copy(deep=True); changed.products[0].title = 'Different source'
    changed = repo.save_plan(changed, plan.revision)
    with pytest.raises(CommerceFailure):
        store.latest(project.id, plan.id, changed.revision)


def test_preview_api_requires_local_auth_and_current_plan_scope_and_has_no_upload_or_approval(product_review, workflow):  # noqa: F811
    from fastapi.testclient import TestClient

    from muse.commerce.preview_repository import PreviewRepository
    from muse.main import create_app
    repo, project, plan, *_ = product_review
    saved = PreviewRepository(repo).save(project.id, plan.id, plan.revision, capture_fixture(product_review))
    settings = workflow[3].settings
    app = create_app(settings)
    path = f'/api/commerce/projects/{project.id}/plans/{plan.id}/preview'
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        assert client.get(path, params={'revision': plan.revision}).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + settings.access_token.get_secret_value()
        response = client.get(path, params={'revision': plan.revision})
        assert response.status_code == 200 and response.json()['site_verified'] is False
        image = client.get(path + '/' + saved.id + '/frames/' + saved.frames[0].id, params={'revision': plan.revision})
        assert image.status_code == 200 and image.json()['frame']['sha256'] == saved.frames[0].sha256
        assert client.get(path.replace(project.id, 'other'), params={'revision': plan.revision}).status_code == 404
        assert client.get(path, params={'revision': 999}).status_code == 409
        assert client.post(path, json={'passed': True}).status_code == 405


def test_rehashed_changed_preview_summary_cannot_reuse_original_capture_identity(product_review):  # noqa: F811
    from muse.commerce.preview_repository import PreviewRepository
    repo, project, plan, *_ = product_review
    store = PreviewRepository(repo)
    saved = store.save(project.id, plan.id, plan.revision, capture_fixture(product_review))
    with repo.db.transaction() as conn:
        value = json.loads(conn.execute(text('SELECT data FROM commerce_artifacts WHERE id=:id'), {'id': saved.id}).scalar())
        value['report']['passed'] = True
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                     {'id': saved.id, 'data': encode(value), 'digest': digest(value)})
    with pytest.raises(CommerceFailure):
        store.latest(project.id, plan.id, plan.revision)
