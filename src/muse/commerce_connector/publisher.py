"""Internal, default-disabled publisher. No CLI/API/Agent write route.

Trusted approval_lookup must load CURRENT persisted approval, changeset and
verification. Plugin-side atomic ownership/precondition/auth checks are still
required; preflight GET cannot close a remote TOCTOU race.
"""
import asyncio
import copy
import re
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from muse.commerce.context import normalize_snapshot, require_capabilities
from muse.commerce.environment import validate_lock
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    ApprovalGrant,
    ChangeOperation,
    ChangeSet,
    VerificationReport,
)
from muse.commerce.repository import digest
from muse.commerce_connector.operation_ledger import OperationRecord
from muse.commerce_connector.operations import operation_digest, validate_operation
from muse.commerce_connector.receipts import ReceiptReconciler
from muse.commerce_connector.wordpress import WordPressReader


@dataclass(frozen=True)
class ApprovedExecution:
    approval: ApprovalGrant
    changeset: ChangeSet
    verification: VerificationReport


def confirm_operation_receipt(ledger, local: OperationRecord, raw: bytes) -> OperationRecord:
    """Accept only a fully matching terminal wire receipt; no status-only failure."""
    try:
        remote = OperationRecord.model_validate_json(raw)
        if (any(getattr(remote, key) != getattr(local, key) for key in
                ('project_id', 'connection_id', 'environment', 'operation_id', 'operation_digest', 'resource_key'))
                or remote.state not in ('SUCCEEDED', 'FAILED')
                or (remote.fingerprint is not None and not re.fullmatch(r'[a-f0-9]{64}', remote.fingerprint))
                or (remote.state == 'SUCCEEDED' and remote.fingerprint is None)):
            raise ValueError()
    except (ValidationError, ValueError, TypeError):
        raise CommerceFailure('WRITE_OUTCOME_UNKNOWN') from None
    return ledger.confirm(local.project_id, local.connection_id, local.environment, local.operation_id,
                          operation_digest=remote.operation_digest, succeeded=remote.state == 'SUCCEEDED',
                          fingerprint=remote.fingerprint)


class WordPressPublisher:
    def __init__(self, connection, ledger, authority, *, approval_lookup, versions_lock,
                 execution_enabled=False, transport=None):
        self.connection, self.ledger, self.authority = connection, ledger, authority
        self.approval_lookup, self.lock = approval_lookup, copy.deepcopy(versions_lock)
        self.execution_enabled, self.transport = execution_enabled, transport

    async def _authorize(self, approval_id, token, operation):
        try:
            async with asyncio.timeout(10):
                context = copy.deepcopy(await self.approval_lookup(approval_id))
        except CommerceFailure:
            raise
        except Exception:  # noqa: BLE001 - trusted provider boundary must never expose storage/secret errors
            # asyncio cancellation derives from BaseException and propagates.
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503) from None
        if not isinstance(context, ApprovedExecution):
            raise CommerceFailure('APPROVAL_REQUIRED', 403)
        grant, changeset, report = context.approval, context.changeset, context.verification
        value = digest(changeset.model_dump(mode='json', exclude={'digest'}))
        if (grant.id != approval_id or changeset.digest != value or grant.changeset_digest != value
                or report.changeset_digest != value or grant.verification_hash != digest(report)
                or not report.passed or changeset.project_id != self.connection.project_id
                or changeset.environment != self.connection.environment
                or grant.resource_preconditions != changeset.resource_preconditions
                or not any(operation_digest(item) == operation_digest(operation) for item in changeset.operations)):
            raise CommerceFailure('REVIEW_STALE')
        self.authority.verify(token, grant, self.connection, operation)
        return context

    async def publish(self, approval_id: str, token: str, operation: ChangeOperation) -> OperationRecord:
        operation = validate_operation(operation)  # Freeze caller-owned mutable nested payload.
        connection = self.connection
        self.ledger.bind_target(connection.project_id, connection.connection_id, connection.environment, connection.base_url)
        scope = (connection.project_id, connection.connection_id, connection.environment, operation.operation_id)
        try:
            existing = self.ledger.get(*scope)
        except CommerceFailure as error:
            if error.public.code != 'NOT_FOUND':
                raise
            existing = None
        if existing is not None:
            if existing.operation_digest != operation_digest(operation):
                raise CommerceFailure('RESOURCE_CONFLICT')
            if existing.state in ('SUCCEEDED', 'FAILED'):
                return existing
            if existing.state == 'NEEDS_RECONCILIATION':
                return await ReceiptReconciler(connection, self.ledger, transport=self.transport).reconcile(operation.operation_id)
        if self.execution_enabled is not True:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        try:
            validate_lock(self.lock)
        except ValueError:
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422) from None
        context = await self._authorize(approval_id, token, operation)
        reader = WordPressReader(connection, transport=self.transport)
        capabilities = require_capabilities(await reader.read('capabilities', remaining_seconds=20), self.lock)
        if operation.kind not in capabilities.supported_operations:
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
        snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), connection.project_id, connection.environment)
        for key, expected in context.approval.resource_preconditions.items():
            if key.startswith(('sku:', 'page-slug:')):
                kind = 'create_product_draft' if key.startswith('sku:') else 'create_owned_page'
                matching = [item for item in context.changeset.operations
                            if item.kind == kind and item.resource_key == key]
                if len(matching) != 1:
                    raise CommerceFailure('REVIEW_STALE')
                product_operation = validate_operation(matching[0])
                if kind == 'create_product_draft':
                    proof = await reader.read_sku(product_operation.payload['product']['sku'], remaining_seconds=20)
                else:
                    proof = await reader.read_page_slug(product_operation.payload['slug'], remaining_seconds=20)
                if proof['resource_key'] != key or proof['fingerprint'] != expected:
                    raise CommerceFailure('REVIEW_STALE')
                continue
            snapshot_key = 'theme' if key == 'theme:muse-storefront' else key
            if snapshot.resource_fingerprints.get(snapshot_key) != expected:
                raise CommerceFailure('REVIEW_STALE')
        await self._authorize(approval_id, token, operation)
        local = self.ledger.prepare(*scope[:3], operation)
        if local.state != 'PREPARED':
            # Another instance may have sent/finished while preflight was reading.
            if local.state in ('SUCCEEDED', 'FAILED'):
                return local
            return await ReceiptReconciler(connection, self.ledger, transport=self.transport).reconcile(operation.operation_id)
        local = self.ledger.begin(*scope)  # FULL synchronous commit BEFORE the network boundary.
        try:
            await self._authorize(approval_id, token, operation)
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
                    if size > 16384:
                        raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
                    chunks.append(chunk)
                return confirm_operation_receipt(self.ledger, local, b''.join(chunks))
        except (TimeoutError, httpx.HTTPError):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN') from None
