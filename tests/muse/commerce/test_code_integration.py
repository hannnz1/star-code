import base64
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from muse.commerce.code_bridge import ThemeCodeBridge
from muse.commerce.code_integration import CommerceCodeIntegration, merge_lines, source_files
from muse.commerce.errors import CommerceFailure
from muse.commerce.restore import ProjectRestorer
from muse.main import create_app
from muse.tools.context import ExecutionContext


def seal(service, tasks, plan, worker, name, extra, *, prepend=False):
    task = tasks.claim_next('manager-' + plan.id)
    ctx = ExecutionContext(worker.settings, tasks, task, 'manager-' + plan.id, enforce_budgets=True)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'blueprint-' + plan.id)
    service.dispatch_step(ctx, next(step.id for step in plan.steps if step.role == 'site_developer'))
    child = tasks.claim_next('developer-' + plan.id)
    bridge = ThemeCodeBridge(ExecutionContext(worker.settings, tasks, child, 'developer-' + plan.id, enforce_budgets=True))
    original = bridge.read(name)
    content = extra + original['content'] if prepend else original['content'] + extra
    changed = bridge.write(name, content, original['draft_hash'])
    bridge.seal(changed['draft_hash'])
    return service.repo.get_plan(plan.id, project_id=plan.project_id)


def apply_body(review, request_id):
    return {'expected_plan_revision': review['plan_revision'], 'expected_head_revision': review['head_revision'],
            'review_digest': review['review_digest'], 'client_request_id': request_id}


@pytest.mark.parametrize('base,current,candidate,expected', [
    ('a\nb\nc\n', 'A\nb\nc\n', 'a\nb\nC\n', 'A\nb\nC\n'),
    ('a\nb\nc\n', 'b\nc\n', 'a\nb\nC\n', 'b\nC\n'),
    ('a\nb\nc\n', 'a\ninsert\nb\nc\n', 'a\nb\nC\n', 'a\ninsert\nb\nC\n'),
    ('a\nb\n', 'A\nb\n', 'OTHER\nb\n', None),
    ('a\nb\n', 'a\nfirst\nb\n', 'a\nsecond\nb\n', None),
    ('a\nb\n', 'A\nb\n', 'a\ninsert\nb\n', None),
    ('a\nb\nc\n', 'A\nb\nc\n', 'A\nb\nC\n', 'A\nb\nC\n'),
    ('甲\r\n乙\r\n尾', '首\r\n乙\r\n尾', '甲\r\n乙\r\n末', '首\r\n乙\r\n末'),
])
def test_line_merge_preserves_disjoint_changes_and_rejects_ambiguity(base, current, candidate, expected):
    result = merge_lines(base.encode(), current.encode(), candidate.encode())
    assert result == (expected.encode() if expected is not None else None)
    assert merge_lines(base.encode(), candidate.encode(), current.encode()) == result


def test_parallel_file_changes_merge_locally_with_stale_review_and_retry_protection(workflow):
    service, tasks, plan, worker = workflow
    first = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    project = service.repo.get_project(plan.project_id)
    second = service.create_workflow(project.id, 'build_site', 'Adjust page', 'parallel-page', project.revision)
    second = seal(service, tasks, second, worker, 'templates/index.html', '\n<!-- reviewed parallel page -->\n')
    with TestClient(create_app(worker.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['Authorization'] = 'Bearer ' + worker.settings.access_token.get_secret_value()
        draft_path = f'/api/commerce/projects/{project.id}/task-drafts'
        draft_body = {'kind': 'build_site', 'title': 'Review baseline', 'prompt': 'Continue the storefront',
                      'expected_project_revision': project.revision, 'client_request_id': 'pre-integration-draft', 'max_requests': 8}
        draft = client.post(draft_path, json=draft_body).json()
        assert draft['code_base_revision'] == 0
        first_path = f'/api/commerce/projects/{project.id}/plans/{first.id}/code-integration'
        second_path = f'/api/commerce/projects/{project.id}/plans/{second.id}/code-integration'
        first_review = client.get(first_path, params={'revision': first.revision}).json()
        stale_second = client.get(second_path, params={'revision': second.revision}).json()
        assert first_review['applicable'] and first_review['changed_files'] == ['style.css']
        assert stale_second['head_revision'] == 0
        body = apply_body(first_review, 'first-apply')
        applied = client.post(first_path, json=body)
        assert applied.status_code == 200, applied.text
        assert applied.json()['revision'] == 1
        assert client.post(first_path, json=body).json() == applied.json()
        count_before_start = len(tasks.list())
        assert client.post(draft_path + '/' + draft['id'] + '/start', json={
            'expected_revision': draft['revision'], 'expected_project_revision': project.revision}).status_code == 409
        assert len(tasks.list()) == count_before_start
        refreshed_draft = client.put(draft_path + '/' + draft['id'], json={
            key: value for key, value in {**draft_body, 'expected_revision': draft['revision']}.items()
            if key != 'client_request_id'})
        assert refreshed_draft.status_code == 200, refreshed_draft.text
        assert refreshed_draft.json()['code_base_revision'] == 1
        assert client.post(second_path, json=apply_body(stale_second, 'stale-second')).status_code == 409
        second_review = client.get(second_path, params={'revision': second.revision}).json()
        assert second_review['head_revision'] == 1 and second_review['conflict_files'] == []
        merged = client.post(second_path, json=apply_body(second_review, 'second-apply'))
        assert merged.status_code == 200, merged.text
        assert merged.json()['revision'] == 2
        with service.repo.db.transaction() as conn:
            head = CommerceCodeIntegration.head(conn, project.id)
            source, _ = ProjectRestorer._theme_source(conn, project.id, head.source_id)
            files = source_files(source)
            assert b'body { color: #111; }' in files['style.css']
            assert b'reviewed parallel page' in files['templates/index.html']
        assert service.repo.get_plan(first.id, project_id=project.id) == first
        assert service.repo.get_plan(second.id, project_id=project.id) == second
        assert tasks.db.rows('SELECT * FROM commerce_approvals') == []
        from muse.commerce.export import ProjectExporter
        exported = ProjectExporter(service.repo).download_project(project.id, project.revision)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported.archive_base64))) as archive:
            source_meta = [name for name in archive.namelist() if name.startswith('themes/') and name.endswith('.json')
                           and json.loads(archive.read(name)).get('source_id') == head.source_id]
            assert len(source_meta) == 1
            assert archive.read(source_meta[0].replace('.json', '.zip')) == base64.b64decode(source.archive_base64)
        next_plan = service.create_workflow(project.id, 'build_site', 'Continue', 'next-head', project.revision)
        assert next_plan.blueprint.required_settings['restored_theme_source']['id'] == head.source_id
        assert next_plan.blueprint.required_settings['local_code_base_revision'] == 2


def test_same_file_disjoint_changes_apply_and_survive_sealed_source(workflow):
    service, tasks, plan, worker = workflow
    first = seal(service, tasks, plan, worker, 'assets/storefront.css', '\nfooter { color: #333; }\n')
    project = service.repo.get_project(plan.project_id)
    second = service.create_workflow(project.id, 'build_site', 'Header styling', 'parallel-header', project.revision)
    second = seal(service, tasks, second, worker, 'assets/storefront.css', '/* Header review */\n', prepend=True)
    integration = CommerceCodeIntegration(service.repo, worker.settings.data_dir / 'commerce-source.git')
    from muse.commerce.api import CodeIntegrationInput
    for item in (first, second):
        review = integration.review(project.id, item.id, item.revision)
        assert review.applicable and review.conflict_files == []
        integration.apply(project.id, item.id, CodeIntegrationInput(**apply_body(review.model_dump(), 'apply-' + item.id)))
    with service.repo.db.transaction() as conn:
        head = integration.head(conn, project.id)
        source, _ = ProjectRestorer._theme_source(conn, project.id, head.source_id)
        content = source_files(source)['assets/storefront.css']
    assert head.revision == 2
    assert content.startswith(b'/* Header review */\n')
    assert content.endswith(b'\nfooter { color: #333; }\n')
    assert service.repo.get_plan(first.id, project_id=project.id) == first
    assert service.repo.get_plan(second.id, project_id=project.id) == second


def test_same_file_conflicts_and_stale_project_never_apply(workflow):
    service, tasks, plan, worker = workflow
    first = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    project = service.repo.get_project(plan.project_id)
    second = service.create_workflow(project.id, 'build_site', 'Other color', 'parallel-color', project.revision)
    second = seal(service, tasks, second, worker, 'style.css', '\nbody { color: #222; }\n')
    integration = CommerceCodeIntegration(service.repo, worker.settings.data_dir / 'commerce-source.git')
    from muse.commerce.api import CodeIntegrationInput
    initial = integration.review(project.id, first.id, first.revision)
    integration.apply(project.id, first.id, CodeIntegrationInput(**apply_body(initial.model_dump(), 'apply-first')))
    conflict = integration.review(project.id, second.id, second.revision)
    assert conflict.conflict_files == ['style.css'] and not conflict.applicable and conflict.reason == 'conflicts'
    with pytest.raises(CommerceFailure):
        integration.apply(project.id, second.id, CodeIntegrationInput(**apply_body(conflict.model_dump(), 'blocked')))
    root = tasks.get(next(step.task_id for step in first.steps if step.role == 'store_manager'))
    tasks.control(root.id, 'cancel', expected_revision=root.revision)
    assert integration.review(project.id, first.id, first.revision).reason == 'plan_ineligible'
    service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'New brief'}), project.revision)
    with pytest.raises(CommerceFailure):
        integration.review(project.id, first.id, first.revision)
