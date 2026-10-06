import pytest

from muse.commerce.api import CodeDecisionInput, CodeIntegrationInput
from muse.commerce.code_integration import CommerceCodeIntegration
from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_code_integration import apply_body, seal


def test_dismiss_restore_and_apply_keep_original_plan_and_stale_review_is_rejected(workflow):
    service, tasks, plan, worker = workflow
    plan = seal(service, tasks, plan, worker, 'style.css', '\nbody { color: #111; }\n')
    integration = CommerceCodeIntegration(service.repo, worker.settings.data_dir / 'commerce-source.git')
    review = integration.review(plan.project_id, plan.id, plan.revision)
    decision = CodeDecisionInput(**apply_body(review.model_dump(), 'dismiss-one'), dismissed=True)
    dismissed = integration.disposition(plan.project_id, plan.id, decision)
    assert integration.disposition(plan.project_id, plan.id, decision) == dismissed
    assert dismissed.status == 'DISMISSED'
    current = integration.review(plan.project_id, plan.id, plan.revision)
    assert current.reason == 'dismissed' and not current.applicable
    with pytest.raises(CommerceFailure):
        integration.apply(plan.project_id, plan.id, CodeIntegrationInput(**apply_body(review.model_dump(), 'stale-apply')))
    with service.repo.db.transaction() as conn:
        assert integration.head(conn, plan.project_id) is None
    restored = integration.disposition(plan.project_id, plan.id,
        CodeDecisionInput(**apply_body(current.model_dump(), 'restore-one'), dismissed=False))
    assert restored.status == 'PENDING' and restored.revision == 2
    refreshed = integration.review(plan.project_id, plan.id, plan.revision)
    integration.apply(plan.project_id, plan.id, CodeIntegrationInput(**apply_body(refreshed.model_dump(), 'fresh-apply')))
    assert integration.dispositions(plan.project_id)[0].status == 'APPLIED'
    assert service.repo.get_plan(plan.id, project_id=plan.project_id) == plan
    assert tasks.db.rows('SELECT * FROM commerce_approvals') == []
