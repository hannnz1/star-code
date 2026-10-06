"""Remote operation safety: no automatic retry after a durable send marker."""
import concurrent.futures

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation
from muse.commerce_connector.operation_ledger import OperationLedger


def operation(identifier='op-1', title='About', resource='page:12'):
    return ChangeOperation(operation_id=identifier, kind='update_owned_page', resource_key=resource,
                           expected_fingerprint='a' * 64, payload={'title': title})


def test_restart_preserves_uncertain_send_and_blocks_same_resource(tmp_path):
    path = tmp_path / 'operations.sqlite'
    ledger = OperationLedger(path)
    ledger.prepare('project', 'connection', 'staging', operation())
    ledger.begin('project', 'connection', 'staging', 'op-1')
    restarted = OperationLedger(path)
    assert restarted.get('project', 'connection', 'staging', 'op-1').state == 'NEEDS_RECONCILIATION'
    with pytest.raises(CommerceFailure) as error:
        restarted.begin('project', 'connection', 'staging', 'op-1')
    assert error.value.public.code == 'WRITE_OUTCOME_UNKNOWN'
    with pytest.raises(CommerceFailure):
        restarted.prepare('project', 'connection', 'staging', operation('op-2'))
    assert restarted.prepare('project', 'connection', 'staging', operation('op-3', resource='page:13')).state == 'PREPARED'


def test_idempotency_payload_conflict_and_terminal_receipt_survive_restart(tmp_path):
    path = tmp_path / 'operations.sqlite'
    ledger = OperationLedger(path)
    original = ledger.prepare('project', 'connection', 'staging', operation())
    assert ledger.prepare('project', 'connection', 'staging', operation()) == original
    with pytest.raises(CommerceFailure):
        ledger.prepare('project', 'connection', 'staging', operation(title='Changed'))
    ledger.begin('project', 'connection', 'staging', 'op-1')
    final = ledger.confirm('project', 'connection', 'staging', 'op-1',
                           operation_digest=original.operation_digest, succeeded=True, fingerprint='b' * 64)
    assert final.state == 'SUCCEEDED'
    assert OperationLedger(path).prepare('project', 'connection', 'staging', operation()) == final
    ledger.prepare('project', 'connection', 'staging', operation('op-2'))
    with pytest.raises(CommerceFailure):
        ledger.begin('project', 'connection', 'staging', 'op-1')


def test_mismatched_receipt_cannot_unlock_resource(tmp_path):
    ledger = OperationLedger(tmp_path / 'operations.sqlite')
    ledger.prepare('project', 'connection', 'staging', operation())
    ledger.begin('project', 'connection', 'staging', 'op-1')
    with pytest.raises(CommerceFailure):
        ledger.confirm('project', 'connection', 'staging', 'op-1', operation_digest='c' * 64,
                       succeeded=True, fingerprint='b' * 64)
    with pytest.raises(CommerceFailure):
        ledger.prepare('project', 'connection', 'staging', operation('op-2'))
    with pytest.raises(CommerceFailure):
        ledger.get('other-project', 'connection', 'staging', 'op-1')


def test_competing_instances_get_only_one_send_permission(tmp_path):
    path = tmp_path / 'operations.sqlite'
    ledger = OperationLedger(path)
    ledger.prepare('project', 'connection', 'staging', operation())
    instances = [OperationLedger(path), OperationLedger(path)]
    def send(instance):
        try:
            instance.begin('project', 'connection', 'staging', 'op-1')
            return True
        except CommerceFailure:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(send, instances)) == [False, True]


@pytest.mark.parametrize('identifier', ['../escape', '', 'x' * 101])
def test_invalid_operation_identity_is_rejected_before_persistence(tmp_path, identifier):
    ledger = OperationLedger(tmp_path / 'operations.sqlite')
    with pytest.raises(CommerceFailure):
        ledger.prepare('project', 'connection', 'staging', operation(identifier))


def test_target_binding_survives_restart_and_rejects_legacy_origin_guess(tmp_path):
    path = tmp_path / 'ledger.sqlite'
    ledger = OperationLedger(path)
    ledger.bind_target('project', 'connection', 'staging', 'https://store.example/')
    restarted = OperationLedger(path)
    restarted.bind_target('project', 'connection', 'staging', 'https://store.example')
    with pytest.raises(CommerceFailure):
        restarted.bind_target('project', 'connection', 'staging', 'https://another.example')
    with pytest.raises(CommerceFailure):
        restarted.bind_target('another', 'connection', 'staging', 'https://store.example')
    old = OperationLedger(tmp_path / 'legacy.sqlite')
    old.prepare('project', 'connection', 'staging', operation())
    with pytest.raises(CommerceFailure):
        old.bind_target('project', 'connection', 'staging', 'https://store.example')
