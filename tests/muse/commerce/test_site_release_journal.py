import copy
from types import SimpleNamespace

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from tests.muse.commerce.test_release_approval import send_fence
from tests.muse.commerce.test_site_release_approval import (  # noqa: F401
    approve,
    site_review,
    store,
)
from tests.muse.commerce.test_site_release_steps import outcome


def proofs_for(intent):
    return {step.resource_ref: {'resource_key': step.resource_ref, 'fingerprint': intent.resource_preconditions[step.resource_ref],
        'state': {'slug': step.payload['slug'], 'exists': False} if step.kind == 'create_owned_page' else
                 {'sku': step.payload['product']['sku'].casefold(), 'exists': False}}
        for step in intent.steps if step.kind in {'create_owned_page', 'create_product_draft'}}


def journal(fixture, tmp_path):
    from muse.commerce.site_journal import SiteReleaseJournal
    from muse.commerce_connector.operation_ledger import OperationLedger
    repository = store(fixture)
    grant = approve(fixture)
    ledger = OperationLedger(tmp_path / 'site-operations.sqlite')
    connection = fixture[5]
    ledger.bind_target(connection.project_id, connection.connection_id, connection.environment, connection.base_url)
    return SiteReleaseJournal(repository, ledger), grant


def confirm(journal, attempt, connection, intent, code, snapshot, proofs):
    done, after = outcome(intent, connection, code, SimpleNamespace(operation=attempt.operation), snapshot, proofs)
    journal.ledger.confirm(connection.project_id, connection.connection_id, connection.environment, attempt.operation.operation_id,
                           operation_digest=done.receipt.operation_digest, succeeded=True, fingerprint=done.receipt.fingerprint)
    return done, after


def test_site_journal_all_steps_survive_restart_and_consume_root_without_replay(site_review, tmp_path):  # noqa: F811
    from muse.commerce.site_journal import SiteReleaseJournal
    repo, project, plan, intent, _, connection, _ = site_review
    execution, grant = journal(site_review, tmp_path)
    code = execution.approvals.frozen_code(intent)
    snapshot, proofs = intent.initial_snapshot, proofs_for(intent)
    for index in range(len(intent.steps)):
        attempt = execution.prepare(grant.id, connection, snapshot, proofs)
        assert attempt.index == index
        send_fence(execution, attempt, connection)
        done, snapshot = confirm(execution, attempt, connection, intent, code, snapshot, proofs)
        result = execution.record_success(attempt.id, connection, done, proofs)
        assert result.state == 'SUCCEEDED' and result.effect_verified
        execution = SiteReleaseJournal(store(site_review), execution.ledger)
    assert len(execution.history(grant.id, connection)) == 17
    assert execution.progress(grant.id, connection)['status'] == 'consumed'
    assert repo.get_plan(plan.id, project_id=project.id).state == 'SUCCEEDED'
    with pytest.raises(CommerceFailure): execution.prepare(grant.id, connection, snapshot, proofs)


@pytest.mark.parametrize('mode', ['unknown', 'revoked_late', 'cancel_late', 'effect_changed', 'ledger_crash_gap'])
def test_site_journal_stops_unknown_and_accounts_late_receipts_without_new_authority(site_review, tmp_path, mode):  # noqa: F811
    from muse.commerce.site_journal import SiteReleaseJournal
    repo, project, plan, intent, _, connection, _ = site_review
    execution, grant = journal(site_review, tmp_path)
    snapshot, proofs = intent.initial_snapshot, proofs_for(intent)
    code = execution.approvals.frozen_code(intent)
    attempt = execution.prepare(grant.id, connection, snapshot, proofs)
    if mode == 'ledger_crash_gap':
        execution.ledger.prepare(connection.project_id, connection.connection_id, connection.environment, attempt.operation)
        execution.ledger.begin(connection.project_id, connection.connection_id, connection.environment, attempt.operation.operation_id)
    else: send_fence(execution, attempt, connection)
    restarted = SiteReleaseJournal(store(site_review), execution.ledger)
    assert restarted.observe_send_fence(attempt.id, connection).state == 'NEEDS_RECONCILIATION'
    if mode in {'unknown', 'ledger_crash_gap'}:
        assert restarted.prepare(grant.id, connection, snapshot, proofs).state == 'NEEDS_RECONCILIATION'
        assert len(restarted.history(grant.id, connection)) == 0
        return
    if mode == 'revoked_late': restarted.approvals.revoke(grant.id, project_id=project.id)
    elif mode == 'cancel_late':
        current = repo.get_plan(plan.id, project_id=project.id)
        repo.save_plan(current.model_copy(update={'state': 'CANCELLED'}), current.revision)
    done, after = confirm(restarted, attempt, connection, intent, code, snapshot, proofs)
    if mode == 'effect_changed':
        done.snapshot = copy.deepcopy(done.snapshot)
        done.snapshot.settings['currency'] = 'EUR'
        done.snapshot.resource_fingerprints['settings'] = digest(done.snapshot.settings)
    result = restarted.record_success(attempt.id, connection, done, proofs)
    assert result.state == 'SUCCEEDED'
    assert result.effect_verified is (mode != 'effect_changed')
    with pytest.raises(CommerceFailure): restarted.prepare(grant.id, connection, after, proofs)
