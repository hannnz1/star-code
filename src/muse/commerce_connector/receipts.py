"""Explicit, bounded receipt lookup. Never issues or retries a store write."""
import asyncio

import httpx
from pydantic import ValidationError

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.operation_ledger import OperationLedger, OperationRecord
from muse.commerce_connector.wordpress import WordPressConnection


class ReceiptReconciler:
    def __init__(self, connection: WordPressConnection, ledger: OperationLedger, *, transport=None):
        self.connection, self.ledger, self.transport = connection, ledger, transport

    async def reconcile(self, operation_id: str) -> OperationRecord:
        connection = self.connection
        self.ledger.bind_target(connection.project_id, connection.connection_id, connection.environment, connection.base_url)
        scope = (connection.project_id, connection.connection_id, connection.environment, operation_id)
        local = self.ledger.get(*scope)  # Validates identity before constructing any URL.
        if local.state in ('SUCCEEDED', 'FAILED'):
            return local
        if local.state != 'NEEDS_RECONCILIATION':
            raise CommerceFailure('RESOURCE_CONFLICT')
        url = connection.base_url.rstrip('/') + '/wp-json/muse/v1/receipts/' + operation_id
        try:
            async with (
                asyncio.timeout(20),
                httpx.AsyncClient(transport=self.transport, follow_redirects=False, trust_env=False,
                                 auth=(connection.username, connection.application_password), timeout=10,
                                 headers={'Accept-Encoding': 'identity'}) as client,
                client.stream('GET', url) as response,
            ):
                if response.status_code == 401:
                    raise CommerceFailure('AUTH_REQUIRED', 502)
                if response.status_code == 403 or 300 <= response.status_code < 400:
                    raise CommerceFailure('PERMISSION_DENIED', 502)
                if response.status_code != 200:
                    raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
                if response.headers.get('Content-Encoding', 'identity').strip().lower() != 'identity':
                    raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 16384:
                        raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
                    chunks.append(chunk)
                remote = OperationRecord.model_validate_json(b''.join(chunks))
        except (TimeoutError, httpx.HTTPError, ValidationError, ValueError):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN') from None
        if (any(getattr(remote, key) != getattr(local, key) for key in
                ('project_id', 'connection_id', 'environment', 'operation_id', 'operation_digest', 'resource_key'))
                or remote.state not in ('SUCCEEDED', 'FAILED')):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        return self.ledger.confirm(*scope, operation_digest=remote.operation_digest,
                                   succeeded=remote.state == 'SUCCEEDED', fingerprint=remote.fingerprint)
