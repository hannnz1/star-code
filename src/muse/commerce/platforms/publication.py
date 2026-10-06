"""Fixed publication commands to the connector; no WordPress secret or permit."""
import asyncio
import json
import re

import httpx
from pydantic import ValidationError

from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_journal import MerchantReleaseJournal
from muse.commerce.merchant_review import (
    MerchantReleaseReview,
    MerchantReviewRepository,
)

MAX_REVIEW_BYTES = 4 * 1024 * 1024
FIXED_FIELDS = {'project_id', 'plan_id', 'intent_digest', 'workflow', 'target', 'source_digest', 'code_revision',
    'package_sha256', 'source_snapshot_hash', 'target_snapshot_hash', 'products', 'images', 'steps', 'checks', 'total_steps'}
ERRORS = {'AUTH_REQUIRED', 'PERMISSION_DENIED', 'RESOURCE_CONFLICT', 'REVIEW_STALE', 'APPROVAL_REQUIRED',
    'APPROVAL_EXPIRED', 'READ_TEMPORARY_FAILURE', 'VERIFICATION_UNAVAILABLE', 'VERIFICATION_FAILED',
    'EXECUTION_BOUNDARY_UNAVAILABLE', 'UNSUPPORTED_CAPABILITY', 'WRITE_OUTCOME_UNKNOWN', 'PARTIAL_APPLY'}


class ConnectorPublicationService:
    def __init__(self, approvals, config, *, transport=None):
        self.reviews, self.config, self.transport = MerchantReviewRepository(approvals), config, transport

    async def _request(self, project_id, plan_id, intent_digest, revision, action):
        local = await asyncio.to_thread(self.reviews.read, project_id, plan_id, intent_digest, revision)
        connection_id = local.target.connector_ref
        if (not all(re.fullmatch(r'[a-zA-Z0-9_-]{1,200}', value) for value in (project_id, plan_id, connection_id))
                or not re.fullmatch(r'[a-f0-9]{64}', intent_digest) or action not in {'read', 'publish', 'reconcile'}):
            raise CommerceFailure('INPUT_INVALID', 422)
        url = self.config.service_url + f'/v1/connections/{connection_id}/publication/{plan_id}/{intent_digest}'
        writing = action != 'read'
        unknown = 'WRITE_OUTCOME_UNKNOWN' if writing else 'READ_TEMPORARY_FAILURE'
        arguments = ({'json': {'project_id': project_id, 'expected_revision': revision, 'action': action}}
            if writing else {'params': {'project_id': project_id, 'revision': revision}})
        try:
            async with (
                asyncio.timeout(660 if writing else 25),
                httpx.AsyncClient(transport=self.transport, follow_redirects=False, trust_env=False,
                    headers={'Authorization': 'Bearer ' + self.config.token.get_secret_value(), 'Accept-Encoding': 'identity'},
                    timeout=650 if writing else 20) as client,
                client.stream('POST' if writing else 'GET', url, **arguments) as response,
            ):
                if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                    raise CommerceFailure(unknown, 502)
                content = bytearray(); limit = MAX_REVIEW_BYTES if response.status_code == 200 else 16384
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > limit:
                        raise CommerceFailure(unknown, 502)
                if response.status_code != 200:
                    code = 'PERMISSION_DENIED' if 300 <= response.status_code < 400 else unknown
                    if response.status_code == 404: code = 'VERIFICATION_UNAVAILABLE'
                    elif response.status_code == 401: code = 'AUTH_REQUIRED'
                    elif response.status_code == 403: code = 'PERMISSION_DENIED'
                    elif response.status_code in {409, 422, 502, 503}:
                        try:
                            remote_code = json.loads(content).get('error', {}).get('code')
                            if isinstance(remote_code, str) and remote_code in ERRORS: code = remote_code
                        except (ValueError, TypeError, AttributeError):
                            pass
                    raise CommerceFailure(code, 503 if response.status_code in {404, 503} else 409, project_id=project_id)
                view = MerchantReleaseReview.model_validate_json(content)
                if (view.model_dump(mode='json', include=FIXED_FIELDS) != local.model_dump(mode='json', include=FIXED_FIELDS)
                        or view.completed_steps > view.total_steps or view.plan_revision < revision
                        or (not writing and view.plan_revision != revision)):
                    raise CommerceFailure(unknown, 502)
                # Only the shared trusted DB journal can establish progress.
                # This read does not open the connector's secret/ledger files.
                plan = await asyncio.to_thread(self.reviews.commerce.get_plan, plan_id, project_id=project_id)
                journal = MerchantReleaseJournal(self.reviews.approvals, None)
                current = await asyncio.to_thread(self.reviews.read, project_id, plan_id, intent_digest, plan.revision, journal=journal)
                if current != view:
                    raise CommerceFailure(unknown, 502)
                return current
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, UnicodeError, ValidationError):
            raise CommerceFailure(unknown, 503, project_id=project_id) from None

    async def review(self, project_id, plan_id, intent_digest, expected_revision):
        return await self._request(project_id, plan_id, intent_digest, expected_revision, 'read')

    async def execute(self, project_id, plan_id, intent_digest, expected_revision, *, reconcile_only):
        return await self._request(project_id, plan_id, intent_digest, expected_revision, 'reconcile' if reconcile_only else 'publish')
