import pytest
from sqlalchemy import text
from muse.commerce.repository import CommerceRepository, encode, digest
from muse.commerce.models import SiteBrief
from muse.commerce.errors import CommerceFailure


def empty_project(workflow):
    _, runtime, plan, _ = workflow
    repo = CommerceRepository(runtime)
    original = repo.get_project(plan.project_id)
    project = repo.create_project(original.workspace_id, SiteBrief(brand_name='Disposable', language='en-US', currency='USD'), 'disposable')
    return repo, project


def test_archive_restore_and_delete_isolated(workflow):
    repo, project = empty_project(workflow)
    original = repo.list_projects()[0]
    saved = repo.archive_project(project.id, project.revision)
    assert project.id not in [p.id for p in repo.list_projects()]
    assert repo.list_archived_projects()[0].id == project.id
    with pytest.raises(CommerceFailure):
        repo.get_project(project.id)
    restored = repo.restore_project(project.id, saved.revision)
    assert restored.revision > saved.revision
    with pytest.raises(CommerceFailure):
        repo.delete_project(project.id, restored.revision, 'wrong name')
    assert repo.get_project(project.id)
    repo.delete_project(project.id, restored.revision, 'Disposable')
    with pytest.raises(CommerceFailure):
        repo.get_project(project.id)
    assert repo.get_project(original.id)


def test_active_team_blocks_project_removal(workflow):
    _, runtime, plan, _ = workflow
    repo = CommerceRepository(runtime)
    project = repo.get_project(plan.project_id)
    for action in ('archive', 'delete'):
        with pytest.raises(CommerceFailure) as failure:
            if action == 'archive': repo.archive_project(project.id, project.revision)
            else: repo.delete_project(project.id, project.revision, project.brief.brand_name)
        assert failure.value.public.code == 'PROJECT_BUSY'
    assert repo.get_project(project.id)


@pytest.mark.parametrize('kind,value', [
    ('verification_job', {'state':'NEEDS_RECONCILIATION'}),
    ('follow_up_model_job', {'status':'QUEUED'}),
    ('local_apply_automation', {'status':'ARMED'}),
    ('reference_job', {'state':'READY'}),
])
def test_background_or_unknown_results_block_delete(workflow, kind, value):
    repo, project = empty_project(workflow)
    with repo.db.transaction() as conn:
        conn.execute(text('INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,:kind,:digest,:data)'),
                     {'id':'blocking', 'project':project.id, 'kind':kind, 'digest':digest(value), 'data':encode(value)})
    with pytest.raises(CommerceFailure) as failure:
        repo.delete_project(project.id, project.revision, project.brief.brand_name)
    assert failure.value.public.code == 'PROJECT_BUSY'


def test_stale_revision_does_not_remove_project(workflow):
    repo, project = empty_project(workflow)
    with pytest.raises(CommerceFailure):
        repo.delete_project(project.id, project.revision + 1, project.brief.brand_name)
    assert repo.get_project(project.id)


def test_verification_request_pointer_does_not_break_removal(workflow):
    repo, project = empty_project(workflow)
    with repo.db.transaction() as conn:
        conn.execute(text("INSERT INTO commerce_artifacts VALUES('pointer',:project,NULL,'verification_request','hash',:data)"),
                     {'project':project.id, 'data':'0123456789abcdef0123456789abcdef'})
    repo.delete_project(project.id, project.revision, project.brief.brand_name)
    assert repo.list_projects()[0].id != project.id


def test_delete_completed_project_cleans_business_records_preserves_task_logs(workflow):
    _, runtime, plan, _ = workflow
    repo = CommerceRepository(runtime)
    project = repo.get_project(plan.project_id)
    with repo.db.transaction() as conn:
        conn.execute(text("UPDATE tasks SET status='SUCCEEDED'"))
        value = repo.get_plan(plan.id, project_id=project.id).model_copy(update={'state':'SUCCEEDED'})
        conn.execute(text('UPDATE commerce_plans SET data=:data WHERE id=:id'), {'id':plan.id,'data':encode(value)})
        conn.execute(text("INSERT INTO commerce_changesets VALUES('changes',:plan,:project,'hash','{}',NULL)"), {'plan':plan.id,'project':project.id})
        conn.execute(text("INSERT INTO commerce_approvals VALUES('approval','changes','hash','revoked',0,'{}')"))
        conn.execute(text("INSERT INTO commerce_receipts VALUES('receipt','changes','hash','SUCCEEDED','{}',0)"))
    before = runtime.db.rows('SELECT id FROM tasks')
    repo.delete_project(project.id, project.revision, project.brief.brand_name)
    assert runtime.db.rows('SELECT id FROM tasks') == before
    for table in ('commerce_projects','commerce_plans','commerce_steps','commerce_snapshots','commerce_changesets',
                  'commerce_approvals','commerce_receipts','commerce_artifacts','commerce_events'):
        assert runtime.db.rows(f'SELECT * FROM {table}') == []

