import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan, SiteBrief
from muse.commerce.repository import CommerceRepository
from muse.tasks.repository import TaskRepository


def repository(tmp_path):
    runtime = TaskRepository(tmp_path / 'state.sqlite3')
    root = tmp_path / 'workspace'
    root.mkdir()
    ws = runtime.register_workspace(str(root))
    repo = CommerceRepository(runtime)
    brief = SiteBrief(brand_name='A', language='en', currency='USD')
    a = repo.create_project(ws['id'], brief, 'a')
    b = repo.create_project(ws['id'], brief.model_copy(update={'brand_name': 'B'}), 'b')
    return repo, a, b


def test_plan_is_revision_bound_and_cannot_move_between_projects(tmp_path):
    repo, a, b = repository(tmp_path)
    plan = CommercePlan(id='plan-a', project_id=a.id, kind='build_site')
    saved = repo.save_plan(plan, expected_revision=0)
    assert saved.revision == 1
    with pytest.raises(CommerceFailure):
        repo.get_plan(saved.id, project_id=b.id)
    with pytest.raises(CommerceFailure):
        repo.save_plan(plan.model_copy(update={'project_id': b.id}), expected_revision=1)
    updated = repo.save_plan(plan.model_copy(update={'state': 'BUILDING'}), expected_revision=1)
    assert updated.revision == 2
    with pytest.raises(CommerceFailure):
        repo.save_plan(plan.model_copy(update={'state': 'FAILED'}), expected_revision=1)
    assert repo.get_plan(plan.id, project_id=a.id).state == 'BUILDING'


def test_brief_change_invalidates_plan_and_preserves_history(tmp_path):
    repo, a, _ = repository(tmp_path)
    repo.save_plan(CommercePlan(id='plan', project_id=a.id, kind='build_site', state='REVIEW_REQUIRED'), expected_revision=0)
    repo.update_brief(a.id, a.brief.model_copy(update={'style': 'Changed'}), 1)
    assert repo.get_plan('plan', project_id=a.id).state == 'STALE'
    assert repo.get_plan('plan', project_id=a.id).revision == 2
    assert [e['kind'] for e in repo.events(a.id)] == ['project_created', 'plan_saved', 'brief_updated']
