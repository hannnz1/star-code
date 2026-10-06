import io
import zipfile

import pytest

from muse.commerce.errors import CommerceFailure
from muse.tools.context import ExecutionContext
from muse.tools.registry import ToolRegistry


def developer(workflow):
    service, repo, plan, worker = workflow
    manager_task = repo.claim_next('manager')
    manager = ExecutionContext(worker.settings, repo, manager_task, 'manager', enforce_budgets=True)
    service.submit(manager, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'manager-output')
    service.dispatch_step(manager, next(s.id for s in plan.steps if s.role == 'site_developer'))
    child = repo.claim_next('developer')
    return ExecutionContext(worker.settings, repo, child, 'developer', enforce_budgets=True)


def test_real_code_edit_diff_seal_and_restart_preserve_exact_bytes(workflow):
    from muse.commerce.code_bridge import ThemeCodeBridge
    ctx = developer(workflow)
    bridge = ThemeCodeBridge(ctx)
    original = bridge.read('style.css')
    changed = original['content'] + '\nbody { border: 1px solid #000; }\n'
    saved = bridge.write('style.css', changed, original['draft_hash'])
    assert saved['draft_hash'] != original['draft_hash']
    assert '+body { border: 1px solid #000; }' in bridge.diff()['diff']
    sealed = bridge.seal(saved['draft_hash'])
    artifact = ThemeCodeBridge(ctx).captured()
    with zipfile.ZipFile(io.BytesIO(artifact.archive)) as archive:
        assert archive.read('muse-storefront/style.css') == changed.encode()
    assert sealed['code_revision'] == artifact.package.code_revision
    assert len(sealed['code_revision']) == 40
    plan = bridge.service.repo.get_plan(artifact.plan_id, project_id=artifact.project_id)
    assert plan.code_revision == sealed['code_revision']
    assert plan.state == 'BUILDING'
    assert bridge.seal(saved['draft_hash']) == sealed
    assert ctx.repo.db.rows('SELECT * FROM commerce_approvals') == []


@pytest.mark.parametrize('name,content', [('../secret', 'oops'), ('functions.php', '<?php evil();'),
    ('style.css', 'body { background: url(https://evil.test/tracker); }')])
def test_code_bridge_rejects_traversal_php_and_active_external_content(workflow, name, content):
    from muse.commerce.code_bridge import ThemeCodeBridge
    bridge = ThemeCodeBridge(developer(workflow))
    original = bridge.read('style.css')
    with pytest.raises(CommerceFailure):
        bridge.write(name, content, original['draft_hash'])
    assert bridge.read('style.css') == original


def test_stale_write_sealed_write_and_cancellation_are_rejected(workflow):
    from muse.commerce.code_bridge import ThemeCodeBridge
    bridge = ThemeCodeBridge(developer(workflow))
    original = bridge.read('style.css')
    saved = bridge.write('style.css', original['content'] + '\nbody { color: #000; }', original['draft_hash'])
    with pytest.raises(CommerceFailure):
        bridge.write('style.css', original['content'], original['draft_hash'])
    bridge.seal(saved['draft_hash'])
    with pytest.raises(CommerceFailure):
        bridge.write('style.css', original['content'], saved['draft_hash'])
    current = bridge.ctx.repo.get(bridge.ctx.task_id)
    bridge.ctx.repo.control(current.id, 'cancel', expected_revision=current.revision)
    with pytest.raises((CommerceFailure, ValueError)):
        bridge.read('style.css')


def test_developer_gets_fixed_code_tools_but_manager_does_not(workflow):
    ctx = developer(workflow)
    names = {t.name for t in ToolRegistry(ctx).definitions()}
    expected = {'read_theme_file', 'write_theme_file', 'show_theme_diff', 'seal_theme_code'}
    assert expected <= names
    assert not names & {'run_command', 'write_file', 'mcp_call'}
    _service, repo, plan, worker = workflow
    manager = repo.get(next(s.task_id for s in plan.steps if s.role == 'store_manager'))
    names = {t.name for t in ToolRegistry(ExecutionContext(worker.settings, repo, manager, 'manager')).definitions()}
    assert not names & expected


async def test_runtime_requires_sealed_current_code_without_claiming_site_verification(workflow):
    from muse.agent.loop import AgentRunner
    from muse.contracts import ToolCall
    from muse.tools.context import ApprovalRequired, TaskControl
    ctx = developer(workflow)
    registry = ToolRegistry(ctx)
    from muse.commerce.code_bridge import ThemeCodeBridge
    bridge = ThemeCodeBridge(ctx)
    original = bridge.read('style.css')
    async def approved(call):
        nonlocal ctx, registry, bridge
        try:
            return await registry.execute(call)
        except ApprovalRequired:
            approval = ctx.repo.approvals(ctx.task_id)[-1]
            ctx.repo.decide_approval(approval['id'], True, approval['action_digest'])
            task = ctx.repo.claim_next('developer')
            ctx = ExecutionContext(ctx.settings, ctx.repo, task, 'developer', enforce_budgets=True)
            registry, bridge = ToolRegistry(ctx), ThemeCodeBridge(ctx)
            return await registry.execute(call)
    result = await approved(ToolCall(id='edit', name='write_theme_file', arguments={
        'name': 'style.css', 'content': original['content'] + '\nbody { color: #000; }', 'expected_hash': original['draft_hash']}))
    assert result.status == 'success'
    with pytest.raises(TaskControl):
        AgentRunner._verified_result(ctx, 'Done')
    saved = bridge.read('style.css')
    result = await approved(ToolCall(id='seal', name='seal_theme_code', arguments={'expected_hash': saved['draft_hash']}))
    assert result.status == 'success'
    prepared = AgentRunner._verified_result(ctx, 'Static code prepared, site verification pending')
    assert prepared.status == 'SUCCEEDED'
    assert prepared.verification['site_verified'] is False
    assert prepared.verification['code_revision'] == bridge.captured().package.code_revision


def test_trusted_capture_read_remains_valid_after_developer_submission(workflow):
    from muse.commerce.code_bridge import ThemeCodeBridge, load_captured_code
    ctx = developer(workflow)
    bridge = ThemeCodeBridge(ctx)
    sealed = bridge.seal(bridge.read('style.css')['draft_hash'])
    plan = bridge.service.repo.get_plan(ctx.cp['commerce']['plan_id'], project_id=ctx.cp['commerce']['project_id'])
    bridge.service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'output')
    plan = bridge.service.repo.get_plan(plan.id, project_id=plan.project_id)
    assert load_captured_code(bridge.service.repo, plan).package.code_revision == sealed['code_revision']


def test_project_export_contains_sealed_custom_code_not_regenerated_seed(workflow):
    import base64

    from muse.commerce.code_bridge import ThemeCodeBridge
    from muse.commerce.export import ProjectExporter
    bridge = ThemeCodeBridge(developer(workflow))
    original = bridge.read('style.css')
    changed = original['content'] + '\nbody { outline: 2px solid #123456; }\n'
    saved = bridge.write('style.css', changed, original['draft_hash'])
    bridge.seal(saved['draft_hash'])
    project = bridge.service.repo.get_project(bridge.ctx.cp['commerce']['project_id'])
    exported = ProjectExporter(bridge.service.repo).download_project(project.id, project.revision)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported.archive_base64))) as archive:
        packed = archive.read('themes/0001.zip')
    with zipfile.ZipFile(io.BytesIO(packed)) as theme:
        assert theme.read('muse-storefront/style.css') == changed.encode()


def test_authenticated_code_review_api_shows_actual_diff_and_enforces_plan_scope(workflow):
    from fastapi.testclient import TestClient

    from muse.commerce.code_bridge import ThemeCodeBridge
    from muse.main import create_app
    bridge = ThemeCodeBridge(developer(workflow))
    original = bridge.read('style.css')
    saved = bridge.write('style.css', original['content'] + '\nbody { color: #123456; }\n', original['draft_hash'])
    sealed = bridge.seal(saved['draft_hash'])
    project_id, plan_id = bridge.ctx.cp['commerce']['project_id'], bridge.ctx.cp['commerce']['plan_id']
    plan = bridge.service.repo.get_plan(plan_id, project_id=project_id)
    app = create_app(bridge.ctx.settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        path = f'/api/commerce/projects/{project_id}/plans/{plan_id}/code?revision={plan.revision}'
        assert client.get(path).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + bridge.ctx.settings.access_token.get_secret_value()
        response = client.get(path)
        assert response.status_code == 200
        review = response.json()
        assert '+body { color: #123456; }' in review['diff']
        assert review['code_revision'] == sealed['code_revision']
        assert review['site_verified'] is False and review['published'] is False
        assert client.get(path.replace(project_id, 'other-project')).status_code == 404
        assert client.get(path.replace(f'revision={plan.revision}', 'revision=999')).status_code == 409
        assert bridge.ctx.settings.provider.api_key.get_secret_value() not in response.text


async def test_actual_agent_runtime_can_edit_seal_and_submit_without_host_shell(workflow):
    from test_agent_loop import ScriptedProvider

    from muse.commerce.code_bridge import ThemeCodeBridge, load_captured_code
    from muse.commerce.theme import render_site_files
    from muse.contracts import ModelEvent, ToolCall
    service, repo, plan, worker = workflow
    manager_task = repo.claim_next('manager')
    manager = ExecutionContext(worker.settings, repo, manager_task, 'manager', enforce_budgets=True)
    service.submit(manager, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'manager-output')
    child = service.dispatch_step(manager, next(s.id for s in plan.steps if s.role == 'site_developer'))
    files = render_site_files(plan.blueprint, plan.products)
    original_hash = ThemeCodeBridge._hash(files)
    files['style.css'] += b'\nbody { color: #000; }\n'
    provider = ScriptedProvider([
        [ModelEvent(type='call', call=ToolCall(id='edit-runtime', name='write_theme_file', arguments={
            'name': 'style.css', 'content': files['style.css'].decode(), 'expected_hash': original_hash}))],
        [ModelEvent(type='call', call=ToolCall(id='seal-runtime', name='seal_theme_code', arguments={'expected_hash': ThemeCodeBridge._hash(files)}))],
        [ModelEvent(type='call', call=ToolCall(id='submit-runtime', name='submit_blueprint', arguments={'candidate': plan.blueprint.model_dump(mode='json')}))],
        [ModelEvent(type='text', text='Static code captured; site verification and publication pending.')],
    ])
    worker.runner.provider = provider
    for _ in range(4):
        await worker.run_once()
        task = repo.get(child.id)
        if task.status == 'WAITING_APPROVAL':
            approval = next(a for a in repo.approvals(child.id) if a['status'] == 'PENDING')
            repo.decide_approval(approval['id'], True, approval['action_digest'])
        elif task.status == 'SUCCEEDED':
            break
    result = repo.get(child.id)
    assert result.status == 'SUCCEEDED'
    assert result.checkpoint['verification']['site_verified'] is False
    actual = service.repo.get_plan(plan.id, project_id=plan.project_id)
    assert load_captured_code(service.repo, actual).package.code_revision == result.checkpoint['verification']['code_revision']
    assert len(provider.requests) == 4
    assert {call['name'] for call in repo.calls(child.id)} == {'write_theme_file', 'seal_theme_code', 'submit_blueprint'}
    assert repo.db.rows('SELECT * FROM commerce_approvals') == []


def restored_seed(workflow):
    import base64

    from sqlalchemy import text

    from muse.commerce.repository import digest, encode
    from muse.commerce.theme import build_file_archive, render_site_files
    service, repo, old, _worker = workflow
    project = service.repo.get_project(old.project_id)
    files = render_site_files(old.blueprint, old.products)
    files['assets/storefront.css'] += b'\nbody { padding: 2px; }\n'
    package, archive = build_file_archive(files, code_revision='a' * 40, content_hash=old.content_hash)
    identity = digest([project.id, 'restored-theme-fixture'])
    value = {'package': package.model_dump(mode='json'), 'archive_base64': base64.b64encode(archive).decode(),
             'deployment_verified': False}
    with repo.db.transaction() as conn:
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'restored_theme_source',:digest,:data)"),
                     {'id': identity, 'project': project.id, 'digest': digest(value), 'data': encode(value)})
    task = repo.get(old.steps[0].task_id)
    repo.control(task.id, 'cancel', expected_revision=task.revision)
    return project, identity, value, files


def test_new_workflow_developer_continues_exact_restored_theme_and_seals_fresh_source(workflow):
    from muse.commerce.code_bridge import ThemeCodeBridge, load_captured_code
    service, repo, _old, worker = workflow
    project, identity, value, files = restored_seed(workflow)
    plan = service.create_workflow(project.id, 'build_site', 'Continue restored theme', 'restored', project.revision,
                                   theme_source_id=identity)
    bridge = ThemeCodeBridge(developer((service, repo, plan, worker)))
    read = bridge.read('assets/storefront.css')
    assert read['content'].encode() == files['assets/storefront.css']
    sealed = bridge.seal(read['draft_hash'])
    current = service.repo.get_plan(plan.id, project_id=project.id)
    captured = load_captured_code(service.repo, current)
    with zipfile.ZipFile(io.BytesIO(captured.archive)) as archive:
        assert archive.read('muse-storefront/assets/storefront.css') == files['assets/storefront.css']
    assert sealed['code_revision'] != value['package']['code_revision']
    assert current.state == 'BUILDING' and repo.db.rows('SELECT * FROM commerce_approvals') == []


def test_restored_theme_source_change_or_cross_project_cannot_seed_or_continue(workflow):
    from sqlalchemy import text

    from muse.commerce.code_bridge import ThemeCodeBridge
    from muse.commerce.repository import digest, encode
    service, repo, _old, worker = workflow
    project, identity, value, _files = restored_seed(workflow)
    with pytest.raises(CommerceFailure):
        service.create_workflow(project.id, 'build_site', 'Invalid source', 'bad', project.revision,
                                theme_source_id='missing')
    plan = service.create_workflow(project.id, 'build_site', 'Continue theme', 'restored', project.revision,
                                   theme_source_id=identity)
    ctx = developer((service, repo, plan, worker))
    bridge = ThemeCodeBridge(ctx)
    read = bridge.read('style.css')
    value['package']['content_sha256'] = 'f' * 64
    with repo.db.transaction() as conn:
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                     {'id': identity, 'data': encode(value), 'digest': digest(value)})
    with pytest.raises(CommerceFailure):
        bridge.seal(read['draft_hash'])
