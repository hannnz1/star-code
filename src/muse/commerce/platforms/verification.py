"""Fixed verification controls; shared journal validates every connector reply."""
import asyncio
import json
import re

import httpx

from muse.commerce.errors import CommerceFailure
from muse.commerce.verification_service import (
    VerificationStatus,
    VerificationStatusRepository,
)


class ConnectorVerificationService:
    def __init__(self, jobs, config, *, transport=None):
        self.jobs, self.config, self.transport = jobs, config, transport
        self.status = VerificationStatusRepository(jobs)

    async def _request(self, project_id, body, *, job_id=None):
        if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,200}', project_id)
                or job_id is not None and not re.fullmatch(r'[a-f0-9]{32}', job_id)):
            raise CommerceFailure('INPUT_INVALID', 422)
        target = self.config.service_url + '/v1/verification-jobs' + ('/' + job_id if job_id else '')
        timeout = 660 if body.get('action') in {'resume_staging', 'reconcile'} else 30
        try:
            async with (
                asyncio.timeout(timeout),
                httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=timeout - 5,
                    headers={'Authorization': 'Bearer ' + self.config.token.get_secret_value(), 'Accept-Encoding': 'identity'}) as client,
                client.stream('POST', target, json={'project_id': project_id, **body}) as response,
            ):
                if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                    raise ValueError()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536: raise ValueError()
                if response.status_code != 200:
                    code = 'WRITE_OUTCOME_UNKNOWN'
                    if response.status_code in {409, 422, 503}:
                        remote = json.loads(data).get('error', {}).get('code')
                        if remote in {'RESOURCE_CONFLICT', 'INPUT_INVALID', 'VERIFICATION_UNAVAILABLE',
                                      'EXECUTION_BOUNDARY_UNAVAILABLE', 'REVIEW_STALE'}:
                            code = remote
                    raise CommerceFailure(code, 503 if response.status_code == 503 else 409)
                value = VerificationStatus.model_validate_json(data)
                if (value.project_id != project_id or job_id is not None and value.id != job_id
                        or body.get('plan_id', value.plan_id) != value.plan_id
                        or self.status.read(project_id, value.id) != value):
                    raise ValueError()
                return value
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError, AttributeError):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN', 503) from None

    async def reserve(self, project_id, plan_id, revision, request_id):
        return await self._request(project_id, {'plan_id': plan_id, 'expected_revision': revision,
            'client_request_id': request_id})

    async def cancel(self, project_id, job_id, revision):
        return await self._request(project_id, {'expected_revision': revision, 'action': 'cancel'}, job_id=job_id)

    async def reconcile(self, project_id, job_id, revision):
        return await self._request(project_id, {'expected_revision': revision, 'action': 'reconcile'}, job_id=job_id)

    async def resume_staging(self, project_id, job_id, revision):
        return await self._request(project_id, {'expected_revision': revision, 'action': 'resume_staging'}, job_id=job_id)
