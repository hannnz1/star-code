"""Durable product attempt/history journal; no HTTP, signing, or resend.

Unknown sends remain fenced by BOTH this journal and OperationLedger. Late
authenticated receipts may be accounted after revocation without authorizing
another action. Only verified effect history can supply follow-up resource IDs.
"""
from dataclasses import dataclass

from muse.commerce.approval import ApprovalRepository
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation, StoreSnapshot
from muse.commerce.release import (
    release_source_hash,
)
from muse.commerce.release_steps import (
    CompletedProductStep,
    project_product_step,
    validate_product_completion,
)
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest, validate_operation


@dataclass(frozen=True)
class ProductReleaseAttempt:
    id: str
    grant_id: str
    index: int
    operation: ChangeOperation
    state: str
    effect_verified: bool


class ProductReleaseJournal:
    attempt_kind = 'product_release_attempt'
    attempt_type = ProductReleaseAttempt
    completed_type = CompletedProductStep
    maximum_steps = 40

    def _project(self, conn, intent, connection, index, history, snapshot, proofs):
        return project_product_step(intent, connection, index, history, snapshot, proofs)

    def _completion(self, conn, intent, connection, history, snapshot, proofs):
        return validate_product_completion(intent, connection, history, snapshot, proofs)

    def __init__(self, approvals, ledger):
        self.approvals, self.ledger = approvals, ledger
        self.db = approvals.db

    def _parent(self, conn, grant_id, connection):
        _, grant = self.approvals._read(conn, self.approvals._id(self.approvals.grant_kind, grant_id), self.approvals.grant_kind)
        row, value = self.approvals._read(conn, self.approvals._id(self.approvals.review_kind, grant['intent_digest']), self.approvals.review_kind)
        intent = self.approvals.validate_intent(self.approvals.intent_type.model_validate(value['intent']), connection=connection)
        if (grant_id != grant['id'] or value['grant'] != grant or grant['project_id'] != connection.project_id
                or grant['connection_id'] != connection.connection_id or grant['environment'] != connection.environment
                or grant['target_url'] != connection.base_url or grant['intent_digest'] != intent.digest
                or row['project_id'] != intent.project_id or row['plan_id'] != intent.plan_id):
            raise CommerceFailure('PERMISSION_DENIED', 403)
        return row, value, intent

    def _attempt(self, conn, identity, connection):
        row, data = self.approvals._read(conn, identity, self.attempt_kind)
        try:
            parent, value, intent = self._parent(conn, data['grant_id'], connection)
            if (type(data['index']) is not int or not 0 <= data['index'] < len(intent.steps)
                    or row['id'] != self.approvals._id(self.attempt_kind, [data['grant_id'], data['index']])
                    or row['project_id'] != intent.project_id or row['plan_id'] != intent.plan_id
                    or data['root_digest'] != intent.digest or data['state'] not in {'PREPARED', 'NEEDS_RECONCILIATION', 'SUCCEEDED', 'FAILED'}):
                raise ValueError()
            validate_operation(ChangeOperation.model_validate(data['operation']))
            return row, data, parent, value, intent
        except (ValueError, TypeError, KeyError):
            raise CommerceFailure('REVIEW_STALE') from None

    def _view(self, row, data):
        return self.attempt_type(row['id'], data['grant_id'], data['index'],
            validate_operation(ChangeOperation.model_validate(data['operation'])), data['state'], data['effect_verified'])

    def _history(self, conn, grant_id, connection, value):
        count = value.get('history_count', 0)
        if type(count) is not int or not 0 <= count <= self.maximum_steps:
            raise CommerceFailure('REVIEW_STALE')
        result = []
        for index in range(count):
            _, data, _, _, _ = self._attempt(conn, self.approvals._id(self.attempt_kind, [grant_id, index]), connection)
            if data['state'] != 'SUCCEEDED' or data['effect_verified'] is not True:
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            try:
                saved = data['outcome']
                result.append(self.completed_type(ChangeOperation.model_validate(saved['operation']),
                    OperationRecord.model_validate(saved['receipt']), StoreSnapshot.model_validate(saved['snapshot']), saved['proof']))
            except (ValueError, TypeError, KeyError):
                raise CommerceFailure('REVIEW_STALE') from None
        return result

    def history(self, grant_id, connection):
        with self.db.transaction() as conn:
            _, value, _ = self._parent(conn, grant_id, connection)
            return self._history(conn, grant_id, connection, value)

    def get_attempt(self, attempt_id, connection):
        with self.db.transaction() as conn:
            row, data, _, _, _ = self._attempt(conn, attempt_id, connection)
            return self._view(row, data)

    def frozen_intent(self, grant_id, connection):
        with self.db.transaction() as conn:
            return self._parent(conn, grant_id, connection)[2]

    def pending(self, grant_id, connection):
        with self.db.transaction() as conn:
            _, value, intent = self._parent(conn, grant_id, connection)
            count = value.get('history_count', 0)
            if type(count) is not int or not 0 <= count <= len(intent.steps):
                raise CommerceFailure('REVIEW_STALE')
            if count == len(intent.steps): return None
            try:
                row, data, _, _, _ = self._attempt(conn, self.approvals._id(self.attempt_kind, [grant_id, count]), connection)
            except CommerceFailure as error:
                if error.public.code == 'NOT_FOUND': return None
                raise
            return self._view(row, data)

    def progress(self, grant_id, connection):
        with self.db.transaction() as conn:
            _, value, intent = self._parent(conn, grant_id, connection)
            count = value.get('history_count', 0)
            if type(count) is not int or not 0 <= count <= len(intent.steps):
                raise CommerceFailure('REVIEW_STALE')
            last = None
            for index in range(min(count + 1, len(intent.steps))):
                try:
                    row, data, _, _, _ = self._attempt(conn, self.approvals._id(self.attempt_kind, [grant_id, index]), connection)
                except CommerceFailure as error:
                    if error.public.code == 'NOT_FOUND': continue
                    raise
                last = self._view(row, data)
            return {'phase': value['phase'], 'status': value['status'], 'completed_steps': count,
                    'total_steps': len(intent.steps), 'last_attempt': last}

    def observe_send_fence(self, attempt_id, connection):
        """Repair only the accounting gap after durable begin; never grants resend."""
        with self.db.transaction() as conn:
            row, data, _, _, _ = self._attempt(conn, attempt_id, connection)
            operation = validate_operation(ChangeOperation.model_validate(data['operation']))
            try:
                local = self._local(connection, operation)
            except CommerceFailure as error:
                if error.public.code == 'NOT_FOUND': return self._view(row, data)
                raise
            if data['state'] == 'PREPARED' and local.state != 'PREPARED':
                data['state'] = 'NEEDS_RECONCILIATION'
                self.approvals._write(conn, row, data)
            return self._view(row, data)

    def prepare(self, grant_id, connection, snapshot, sku_proofs):
        self.approvals.start(grant_id, connection)
        with self.db.transaction() as conn:
            execution, _, value, _ = self.approvals._load(conn, grant_id, connection)
            history = self._history(conn, grant_id, connection, value)
            index = len(history)
            identity = self.approvals._id(self.attempt_kind, [grant_id, index])
            try:
                row, data, _, _, _ = self._attempt(conn, identity, connection)
            except CommerceFailure as error:
                if error.public.code != 'NOT_FOUND': raise
                row = data = None
            if data is not None and data['state'] != 'PREPARED':
                # A changed post-send snapshot must not prevent read-only recovery.
                return self._view(row, data)
            projected = self._project(conn, execution.intent, connection, index, history, snapshot, sku_proofs)
            if data is not None:
                if data['operation'] != projected.operation.model_dump(mode='json') or data['preconditions'] != projected.preconditions:
                    raise CommerceFailure('REVIEW_STALE')
                return self._view(row, data)
            data = {'grant_id': grant_id, 'root_digest': execution.intent.digest, 'index': index,
                'operation': projected.operation.model_dump(mode='json'), 'preconditions': projected.preconditions,
                'snapshot': snapshot.model_dump(mode='json'), 'sku_proofs': sku_proofs,
                'state': 'PREPARED', 'effect_verified': False, 'outcome': None}
            self.approvals._insert(conn, identity, execution.intent.project_id, execution.intent.plan_id, self.attempt_kind, data)
            row, _ = self.approvals._read(conn, identity, self.attempt_kind)
            return self._view(row, data)

    def _local(self, connection, operation):
        record = self.ledger.get(connection.project_id, connection.connection_id, connection.environment, operation.operation_id)
        if record.operation_digest != operation_digest(operation) or record.resource_key != operation.resource_key:
            raise CommerceFailure('RESOURCE_CONFLICT')
        return record

    def mark_sent(self, attempt_id, connection):
        self.approvals.expire_due()
        with self.db.transaction() as conn:
            row, data, _, value, _ = self._attempt(conn, attempt_id, connection)
            self.approvals._load(conn, data['grant_id'], connection)
            operation = validate_operation(ChangeOperation.model_validate(data['operation']))
            if (data['state'] != 'PREPARED' or data['index'] != value.get('history_count', 0)
                    or self._local(connection, operation).state != 'NEEDS_RECONCILIATION'):
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            data['state'] = 'NEEDS_RECONCILIATION'
            self.approvals._write(conn, row, data)
            return self._view(row, data)

    def _transition(self, conn, parent, value, intent, state, error, status):
        project, plan = ApprovalRepository._source(conn, intent.project_id, intent.plan_id)
        if (plan.revision == value['plan_revision'] and plan.state == value['phase'] and plan.state == 'PUBLISHING'
                and release_source_hash(plan) == intent.plan_source_hash and digest(project) == value['project_hash']
                and value['status'] == 'approved'):
            plan = plan.model_copy(update={'state': state, 'revision': plan.revision + 1, 'error_code': error})
            self.approvals._plan(conn, plan)
            value.update({'phase': state, 'plan_revision': plan.revision, 'status': status})
        elif state != 'PUBLISHING' and value['status'] == 'approved':
            value['status'] = 'blocked'  # Never overwrite a newer/cancelled plan.
        self.approvals._write(conn, parent, value)

    def record_success(self, attempt_id, connection, outcome, sku_proofs):
        self.approvals.expire_due()
        if not isinstance(outcome, self.completed_type):
            raise CommerceFailure('INPUT_INVALID', 422)
        with self.db.transaction() as conn:
            row, data, parent, value, intent = self._attempt(conn, attempt_id, connection)
            operation = validate_operation(ChangeOperation.model_validate(data['operation']))
            local = self._local(connection, operation)
            if (local.state != 'SUCCEEDED' or local != outcome.receipt
                    or operation_digest(outcome.operation) != operation_digest(operation)):
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            saved = {'operation': outcome.operation.model_dump(mode='json'), 'receipt': outcome.receipt.model_dump(mode='json'),
                     'snapshot': outcome.snapshot.model_dump(mode='json'), 'proof': outcome.proof, 'sku_proofs': sku_proofs}
            if data['state'] == 'SUCCEEDED':
                if data['outcome'] != saved: raise CommerceFailure('RESOURCE_CONFLICT')
                return self._view(row, data)
            if data['state'] != 'NEEDS_RECONCILIATION' or data['index'] != value.get('history_count', 0):
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            history = self._history(conn, data['grant_id'], connection, value)
            original = self._project(conn, intent, connection, data['index'], history,
                StoreSnapshot.model_validate(data['snapshot']), data['sku_proofs'])
            if original.operation != operation or original.preconditions != data['preconditions']:
                raise CommerceFailure('REVIEW_STALE')
            completed = len(history) + 1 == len(intent.steps)
            candidate = history + [outcome]
            try:
                if completed: self._completion(conn, intent, connection, candidate, outcome.snapshot, sku_proofs)
                else: self._project(conn, intent, connection, len(candidate), candidate, outcome.snapshot, sku_proofs)
            except CommerceFailure:
                # The wire receipt is known successful, even if effect validation
                # fails. Preserve it and block; do not relabel or authorize resend.
                data.update({'state': 'SUCCEEDED', 'effect_verified': False, 'outcome': saved})
                self.approvals._write(conn, row, data)
                self._transition(conn, parent, value, intent, 'STALE', 'REVIEW_STALE', 'blocked')
                return self._view(row, data)
            data.update({'state': 'SUCCEEDED', 'effect_verified': True, 'outcome': saved})
            value['history_count'] = len(candidate)
            self.approvals._write(conn, row, data)
            self._transition(conn, parent, value, intent, 'SUCCEEDED' if completed else 'PUBLISHING', None,
                             'consumed' if completed else 'approved')
            self.approvals.commerce.event(conn, intent.project_id, self.approvals.event_prefix + '_step_recorded',
                {'grant_id': data['grant_id'], 'index': data['index'], 'operation_id': operation.operation_id})
            return self._view(row, data)

    def record_failure(self, attempt_id, connection):
        """Only a matched terminal local receipt; never infer failure from timeout."""
        self.approvals.expire_due()
        with self.db.transaction() as conn:
            row, data, parent, value, intent = self._attempt(conn, attempt_id, connection)
            operation = validate_operation(ChangeOperation.model_validate(data['operation']))
            local = self._local(connection, operation)
            if local.state != 'FAILED':
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            saved = {'operation': operation.model_dump(mode='json'), 'receipt': local.model_dump(mode='json')}
            if data['state'] == 'FAILED':
                if data['outcome'] != saved: raise CommerceFailure('RESOURCE_CONFLICT')
                return self._view(row, data)
            if data['state'] != 'NEEDS_RECONCILIATION' or data['index'] != value.get('history_count', 0):
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            data.update({'state': 'FAILED', 'effect_verified': False, 'outcome': saved})
            self.approvals._write(conn, row, data)
            partial = data['index'] > 0
            self._transition(conn, parent, value, intent, 'PARTIAL' if partial else 'FAILED',
                             'PARTIAL_APPLY' if partial else 'RESOURCE_CONFLICT', 'consumed')
            self.approvals.commerce.event(conn, intent.project_id, self.approvals.event_prefix + '_step_failed',
                {'grant_id': data['grant_id'], 'index': data['index'], 'operation_id': operation.operation_id})
            return self._view(row, data)
