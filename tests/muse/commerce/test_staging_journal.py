from types import SimpleNamespace

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.operation_ledger import OperationLedger
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_release_approval import send_fence
from tests.muse.commerce.test_site_release_steps import outcome
from tests.muse.commerce.test_staging_source import (  # noqa: F401
    ExplicitFixtureSession,
    staging_source_inputs,
)


async def prepare(inputs, tmp_path):
    from muse.commerce.staging_journal import StagingReleaseJournal
    from muse.commerce.staging_source import StagingSourceRepository
    repo, project, plan, intent, connection, clock, _ = inputs
    sources = StagingSourceRepository(repo, clock=lambda: clock[0])
    grant = await sources.authorize(intent, connection=connection, expected_plan_revision=plan.revision,
        boundary=ExplicitFixtureSession(tmp_path / 'boundary'))
    ledger = OperationLedger(tmp_path / 'staging-ledger.sqlite')
    ledger.bind_target(project.id, connection.connection_id, connection.environment, connection.base_url)
    return StagingReleaseJournal(sources, ledger), grant


def test_staging_journal_rejects_merchant_approval_namespace(staging_source_inputs, tmp_path):  # noqa: F811
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    from muse.commerce.staging_journal import StagingReleaseJournal
    with pytest.raises(CommerceFailure):
        StagingReleaseJournal(MerchantReleaseApprovalRepository(staging_source_inputs[0]), OperationLedger(tmp_path / 'wrong.sqlite'))


@pytest.mark.asyncio
async def test_staging_eighteen_effects_do_not_approve_publish_or_complete_merchant_plan(staging_source_inputs, tmp_path):  # noqa: F811
    journal, grant = await prepare(staging_source_inputs, tmp_path)
    repo, project, plan, intent, connection, _, proofs = staging_source_inputs
    with pytest.raises(CommerceFailure): journal.approvals.verification_source(grant.id, connection)
    code = journal.approvals.frozen_code(intent); snapshot = intent.initial_snapshot
    for index in range(len(intent.steps)):
        attempt = journal.prepare(grant.id, connection, snapshot, proofs)
        assert attempt.index == index
        send_fence(journal, attempt, connection)
        done, snapshot = outcome(intent, connection, code, SimpleNamespace(operation=attempt.operation), snapshot, proofs)
        journal.ledger.confirm(project.id, connection.connection_id, connection.environment, attempt.operation.operation_id,
            operation_digest=done.receipt.operation_digest, succeeded=True, fingerprint=done.receipt.fingerprint)
        assert journal.record_success(attempt.id, connection, done, proofs).effect_verified
    assert journal.progress(grant.id, connection)['status'] == 'consumed'
    assert journal.progress(grant.id, connection)['phase'] == 'STAGED'
    frozen, history = journal.approvals.verification_source(grant.id, connection)
    assert frozen == intent and len(history) == len(intent.steps)
    with repo.db.transaction() as conn:
        assert journal.approvals._verification_source(conn, grant.id, connection, fresh=True)[0] == intent
    staging_source_inputs[5][0] = grant.expires_at
    with repo.db.transaction() as conn, pytest.raises(CommerceFailure):
        journal.approvals._verification_source(conn, grant.id, connection, fresh=True)
    assert journal.approvals.verification_source(grant.id, connection)[0] == intent
    assert repo.get_plan(plan.id, project_id=project.id).state == 'VERIFYING'
    assert repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'") == []
    assert repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'") == []
    with pytest.raises(CommerceFailure): journal.approvals.load(grant.id, connection)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['expired', 'revoked', 'cancelled'])
async def test_staging_unknown_is_accounted_after_stop_but_next_send_is_forbidden(staging_source_inputs, tmp_path, mode):  # noqa: F811
    journal, grant = await prepare(staging_source_inputs, tmp_path)
    repo, project, plan, intent, connection, clock, proofs = staging_source_inputs
    attempt = journal.prepare(grant.id, connection, intent.initial_snapshot, proofs)
    send_fence(journal, attempt, connection)
    if mode == 'expired': clock[0] = grant.expires_at
    elif mode == 'revoked': journal.approvals.revoke(grant.id, project_id=project.id)
    else:
        root = next(step.task_id for step in plan.steps if step.role == 'store_manager')
        task = repo.runtime.get(root); repo.runtime.control(root, 'cancel', expected_revision=task.revision)
    done, snapshot = outcome(intent, connection, journal.approvals.frozen_code(intent),
        SimpleNamespace(operation=attempt.operation), intent.initial_snapshot, proofs)
    journal.ledger.confirm(project.id, connection.connection_id, connection.environment, attempt.operation.operation_id,
        operation_digest=done.receipt.operation_digest, succeeded=True, fingerprint=done.receipt.fingerprint)
    assert journal.record_success(attempt.id, connection, done, proofs).effect_verified
    with pytest.raises(CommerceFailure): journal.prepare(grant.id, connection, snapshot, proofs)
    assert repo.get_plan(plan.id, project_id=project.id).state == 'VERIFYING'
