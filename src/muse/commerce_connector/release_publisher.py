"""Default-disabled v2 product broker. No public or Agent write route.

Requires current private merchant approval, trusted verifier artifact, immutable
source, verified platform lock, and durable send fences. Recovery is GET-only.
"""
import asyncio
import copy

import httpx

from muse.commerce.context import normalize_snapshot, require_capabilities
from muse.commerce.environment import validate_lock
from muse.commerce.errors import CommerceFailure
from muse.commerce.release_steps import CompletedProductStep
from muse.commerce_connector.publisher import confirm_operation_receipt
from muse.commerce_connector.receipts import ReceiptReconciler
from muse.commerce_connector.wordpress import WordPressReader


class ProductReleasePublisher:
    required_operations = frozenset({'create_product_draft', 'publish_product'})
    completed_type = CompletedProductStep

    def __init__(self, connection, journal, authority, *, versions_lock, execution_enabled=False, transport=None):
        self.connection, self.journal, self.authority = connection, journal, authority
        self.ledger, self.approvals = journal.ledger, journal.approvals
        self.lock, self.execution_enabled, self.transport = copy.deepcopy(versions_lock), execution_enabled, transport

    @staticmethod
    async def _store(action, *args):
        try:
            return await asyncio.to_thread(action, *args)
        except CommerceFailure:
            raise
        except Exception:  # noqa: BLE001 - trusted storage errors must not expose private paths
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503) from None

    async def _bind(self):
        connection = self.connection
        await self._store(self.ledger.bind_target, connection.project_id, connection.connection_id,
                          connection.environment, connection.base_url)

    async def _read_context(self, intent):
        connection = self.connection
        reader = WordPressReader(connection, transport=self.transport)
        snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), connection.project_id, connection.environment)
        proofs = {}
        for step in intent.steps[::2]:
            proof = await reader.read_sku(step.product.sku, remaining_seconds=20)
            if proof['resource_key'] != step.resource_ref:
                raise CommerceFailure('REVIEW_STALE')
            proofs[step.resource_ref] = proof
        return snapshot, proofs

    async def _issue_permit(self, execution, attempt, history, snapshot, proofs):
        return self.authority.issue(execution.grant, execution.intent, self.connection, attempt.index, history, snapshot, proofs)

    async def _check_permit(self, token, execution, attempt, history, snapshot, proofs):
        return self.authority.verify(token, execution.grant, execution.intent, self.connection, attempt.index, history, snapshot, proofs)

    async def _account(self, attempt, receipt):
        if receipt.state == 'FAILED':
            return await self._store(self.journal.record_failure, attempt.id, self.connection)
        if receipt.state != 'SUCCEEDED':
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        intent = await self._store(self.journal.frozen_intent, attempt.grant_id, self.connection)
        snapshot, proofs = await self._read_context(intent)
        outcome = self.completed_type(attempt.operation, receipt, snapshot, proofs.get(intent.steps[attempt.index].resource_ref, {}))
        return await self._store(self.journal.record_success, attempt.id, self.connection, outcome, proofs)

    async def reconcile_attempt(self, attempt_id):
        await self._bind()
        attempt = await self._store(self.journal.observe_send_fence, attempt_id, self.connection)
        if attempt.state in {'SUCCEEDED', 'FAILED'}:
            return attempt
        if attempt.state != 'NEEDS_RECONCILIATION':
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        receipt = await ReceiptReconciler(self.connection, self.ledger, transport=self.transport).reconcile(attempt.operation.operation_id)
        return await self._account(attempt, receipt)

    async def publish_next(self, grant_id):
        await self._bind()
        pending = await self._store(self.journal.pending, grant_id, self.connection)
        if pending is not None:
            pending = await self._store(self.journal.observe_send_fence, pending.id, self.connection)
            if pending.state == 'NEEDS_RECONCILIATION':
                return await self.reconcile_attempt(pending.id)
            if pending.state in {'SUCCEEDED', 'FAILED'}:
                return pending
        progress = await self._store(self.journal.progress, grant_id, self.connection)
        if progress['status'] == 'consumed' and progress['last_attempt'] is not None:
            return progress['last_attempt']
        if self.execution_enabled is not True:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        try:
            validate_lock(self.lock)
        except ValueError:
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422) from None
        execution = await self._store(self.approvals.load, grant_id, self.connection)
        reader = WordPressReader(self.connection, transport=self.transport)
        capabilities = require_capabilities(await reader.read('capabilities', remaining_seconds=20), self.lock)
        if not self.required_operations <= set(capabilities.supported_operations):
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
        snapshot, proofs = await self._read_context(execution.intent)
        attempt = await self._store(self.journal.prepare, grant_id, self.connection, snapshot, proofs)
        if attempt.state != 'PREPARED':
            return await self.reconcile_attempt(attempt.id)
        history = await self._store(self.journal.history, grant_id, self.connection)
        execution = await self._store(self.approvals.load, grant_id, self.connection)
        token = await self._issue_permit(execution, attempt, history, snapshot, proofs)
        projected = await self._check_permit(token, execution, attempt, history, snapshot, proofs)
        if projected.operation != attempt.operation:
            raise CommerceFailure('REVIEW_STALE')
        connection, operation = self.connection, attempt.operation
        scope = connection.project_id, connection.connection_id, connection.environment
        local = await self._store(self.ledger.prepare, *scope, operation)
        if local.state != 'PREPARED':
            return await self.reconcile_attempt(attempt.id)
        local = await self._store(self.ledger.begin, *scope, operation.operation_id)
        await self._store(self.journal.mark_sent, attempt.id, connection)
        execution = await self._store(self.approvals.load, grant_id, connection)
        await self._check_permit(token, execution, attempt, history, snapshot, proofs)
        try:
            async with (
                asyncio.timeout(20),
                httpx.AsyncClient(transport=self.transport, follow_redirects=False, trust_env=False,
                    auth=(connection.username, connection.application_password), timeout=10,
                    headers={'Accept-Encoding': 'identity'}) as client,
                client.stream('POST', connection.base_url.rstrip('/') + '/wp-json/muse/v1/operations',
                    json={'operation': operation.model_dump(mode='json'), 'execution_authorization': token}) as response,
            ):
                if response.status_code != 200 or response.headers.get('Content-Encoding', 'identity').strip().lower() != 'identity':
                    raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 16384: raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
                    chunks.append(chunk)
                receipt = await self._store(confirm_operation_receipt, self.ledger, local, b''.join(chunks))
        except (TimeoutError, httpx.HTTPError):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN') from None
        return await self._account(attempt, receipt)
