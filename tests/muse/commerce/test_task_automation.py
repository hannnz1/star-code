import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.task_automation import ArmLocalApply, LocalApplyService
from tests.muse.commerce.test_code_integration import seal


def setup(workflow):
    service, tasks, plan, worker = workflow
    project = service.repo.get_project(plan.project_id)
    automation = LocalApplyService(service.repo, worker.settings.data_dir / 'commerce-source.git')
    body = ArmLocalApply(expected_plan_revision=plan.revision, expected_project_revision=project.revision,
                         expected_head_revision=0, client_request_id='arm-once')
    return service, tasks, plan, worker, project, automation, body


def test_one_shot_application_waits_for_seal_and_never_publishes(workflow):
    service, tasks, plan, worker, project, automation, body = setup(workflow)
    armed = automation.arm(project.id, plan.id, body)
    assert automation.arm(project.id, plan.id, body) == armed
    automation.process()
    assert automation.get(project.id, plan.id).status == 'ARMED'
    sealed = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    automation.process()
    assert automation.get(project.id, plan.id).status == 'APPLIED'
    with service.repo.db.transaction() as conn:
        assert automation.integration.head(conn, project.id).revision == 1
    automation.process()
    with service.repo.db.transaction() as conn:
        assert automation.integration.head(conn, project.id).revision == 1
    assert service.repo.get_plan(plan.id, project_id=project.id) == sealed
    assert tasks.db.rows('SELECT * FROM commerce_approvals') == []


@pytest.mark.parametrize('action', ['cancel', 'project_change', 'expired'])
def test_cancel_stale_and_expired_authorizations_never_apply(workflow, action):
    service, tasks, plan, worker, project, automation, body = setup(workflow)
    armed = automation.arm(project.id, plan.id, body)
    seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    if action == 'cancel':
        automation.cancel(project.id, plan.id, armed.revision)
    elif action == 'project_change':
        service.repo.update_brief(project.id, project.brief.model_copy(update={'style': 'Minimal'}), project.revision)
    else:
        with service.repo.db.transaction() as conn:
            automation._save(conn, armed.model_copy(update={'expires_at': 0}))
    automation.process()
    assert automation.get(project.id, plan.id).status in {'CANCELLED', 'BLOCKED'}
    with service.repo.db.transaction() as conn:
        assert automation.integration.head(conn, project.id) is None


def test_head_change_blocks_auto_apply_and_conflicting_request_ids_are_rejected(workflow):
    service, tasks, plan, worker, project, automation, body = setup(workflow)
    automation.arm(project.id, plan.id, body)
    with pytest.raises(CommerceFailure):
        automation.arm(project.id, plan.id, body.model_copy(update={'expected_head_revision': 1}))
    first = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    from muse.commerce.api import CodeIntegrationInput
    from tests.muse.commerce.test_code_integration import apply_body
    review = automation.integration.review(project.id, plan.id, first.revision)
    automation.integration.apply(project.id, plan.id, CodeIntegrationInput(**apply_body(review.model_dump(), 'manual-first')))
    automation.process()
    result = automation.get(project.id, plan.id)
    assert result.status == 'BLOCKED' and result.reason == 'baseline_changed'
    with service.repo.db.transaction() as conn:
        assert automation.integration.head(conn, project.id).revision == 1


def test_restart_after_apply_receipt_recovers_without_duplicate_baseline(workflow):
    service, tasks, plan, worker, project, automation, body = setup(workflow)
    armed = automation.arm(project.id, plan.id, body)
    sealed = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    from muse.commerce.api import CodeIntegrationInput
    from tests.muse.commerce.test_code_integration import apply_body
    review = automation.integration.review(project.id, plan.id, sealed.revision)
    request = apply_body(review.model_dump(), 'crashed-apply-receipt')
    applying = armed.model_copy(update={'status': 'APPLYING', 'revision': 2, 'apply_body': request, 'expires_at': 0})
    with service.repo.db.transaction() as conn:
        automation._save(conn, applying)
    automation.integration.apply(project.id, plan.id, CodeIntegrationInput(**request))
    LocalApplyService(service.repo, worker.settings.data_dir / 'commerce-source.git').process()
    assert automation.get(project.id, plan.id).status == 'APPLIED'
    with service.repo.db.transaction() as conn:
        assert automation.integration.head(conn, project.id).revision == 1


def test_restart_before_apply_cannot_create_receipt_after_authorization_expiry(workflow):
    service, tasks, plan, worker, project, automation, body = setup(workflow)
    armed = automation.arm(project.id, plan.id, body)
    sealed = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    from tests.muse.commerce.test_code_integration import apply_body
    review = automation.integration.review(project.id, plan.id, sealed.revision)
    request = apply_body(review.model_dump(), 'crashed-before-apply')
    with service.repo.db.transaction() as conn:
        automation._save(conn, armed.model_copy(update={'status': 'APPLYING', 'revision': 2, 'expires_at': 0, 'apply_body': request}))
    automation.process()
    assert automation.get(project.id, plan.id).status == 'BLOCKED'
    with service.repo.db.transaction() as conn:
        assert automation.integration.head(conn, project.id) is None


def test_oversize_merge_blocks_automation_without_stopping_other_jobs(workflow):
    service, tasks, plan, worker, project, automation, body = setup(workflow)
    from muse.commerce.api import CodeIntegrationInput
    from tests.muse.commerce.test_code_integration import apply_body
    first = seal(service, tasks, plan, worker, 'style.css', '/*' + 'a' * 300000 + '*/\n', prepend=True)
    second = service.create_workflow(project.id, 'build_site', 'Footer styling', 'large-parallel', project.revision)
    second = seal(service, tasks, second, worker, 'style.css', '\n/*' + 'b' * 300000 + '*/\n')
    review = automation.integration.review(project.id, first.id, first.revision)
    automation.integration.apply(project.id, first.id, CodeIntegrationInput(**apply_body(review.model_dump(), 'large-first')))
    automation.arm(project.id, second.id, body.model_copy(update={'expected_plan_revision': second.revision,
        'expected_head_revision': 1, 'client_request_id': 'large-second'}))
    third = service.create_workflow(project.id, 'build_site', 'Page styling', 'after-large-merge', project.revision)
    third = seal(service, tasks, third, worker, 'templates/index.html', '\n<!-- remaining job -->\n')
    automation.arm(project.id, third.id, body.model_copy(update={'expected_plan_revision': third.revision,
        'expected_head_revision': 1, 'client_request_id': 'remaining-job'}))
    automation.process()
    assert automation.get(project.id, second.id).status == 'BLOCKED'
    assert automation.get(project.id, second.id).reason == 'VERIFICATION_FAILED'
    assert automation.get(project.id, third.id).status == 'APPLIED'
    automation.process()
    with service.repo.db.transaction() as conn:
        assert automation.integration.head(conn, project.id).revision == 2
