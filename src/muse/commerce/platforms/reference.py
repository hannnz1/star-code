"""Fixed host reference commands; the main backend never reads CMS secrets."""
import asyncio
import json
import re

import httpx

from muse.commerce.errors import CommerceFailure
from muse.commerce.reference_jobs import ReferenceJob


class ConnectorReferenceService:
    def __init__(self, jobs, config, *, transport=None):
        self.jobs, self.config, self.transport = jobs, config, transport

    async def _request(self, project_id, body, *, job_id=None):
        if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,200}', project_id)
                or job_id is not None and not re.fullmatch(r'[a-f0-9]{32}', job_id)):
            raise CommerceFailure('INPUT_INVALID', 422)
        target = self.config.service_url + '/v1/reference-jobs' + ('/' + job_id if job_id else '')
        try:
            async with (
                asyncio.timeout(660),
                httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=650,
                    headers={'Authorization': 'Bearer ' + self.config.token.get_secret_value(), 'Accept-Encoding': 'identity'}) as client,
                client.stream('POST', target, json={'project_id': project_id, **body}) as response,
            ):
                if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                    raise CommerceFailure('WRITE_OUTCOME_UNKNOWN', 502)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise CommerceFailure('WRITE_OUTCOME_UNKNOWN', 502)
                if response.status_code != 200:
                    code = 'PERMISSION_DENIED' if 300 <= response.status_code < 400 else 'WRITE_OUTCOME_UNKNOWN'
                    if response.status_code in {409, 422, 503}:
                        try:
                            remote = json.loads(data).get('error', {}).get('code')
                            if remote in {'RESOURCE_CONFLICT', 'INPUT_INVALID', 'EXECUTION_BOUNDARY_UNAVAILABLE', 'VERIFICATION_FAILED'}:
                                code = remote
                        except (ValueError, TypeError, AttributeError):
                            pass
                    raise CommerceFailure(code, 503 if response.status_code == 503 else 409)
                if body.get('action') == 'recover':
                    value = json.loads(data)
                    local = self.jobs.read(project_id, job_id)
                    if (set(value) != {'job_id', 'job_revision', 'site_ready', 'absent_names', 'present_names', 'absent_resources', 'present_resources'}
                            or value['job_id'] != job_id or value['job_revision'] != local.revision
                            or value['site_ready'] is not False or not isinstance(value['absent_names'], list)
                            or not isinstance(value['present_names'], list)
                            or not isinstance(value['absent_resources'], list) or not isinstance(value['present_resources'], list)
                            or set(value['absent_resources']) & set(value['present_resources'])
                            or len(value['absent_resources']) + len(value['present_resources']) != len(local.resource_names)
                            or set(value['absent_resources']) | set(value['present_resources']) != set(local.resource_names)
                            or value['absent_names'] != [local.resource_names[key] for key in value['absent_resources']]
                            or value['present_names'] != [local.resource_names[key] for key in value['present_resources']]):
                        raise ValueError()
                    return value
                job = ReferenceJob.model_validate_json(data)
                if job.project_id != project_id or job_id is not None and job.id != job_id:
                    raise ValueError()
                if self.jobs.read(project_id, job.id) != job:
                    raise ValueError()
                return job
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError, UnicodeError):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN', 503) from None

    async def reserve(self, project_id, project_revision, request_id):
        project = self.jobs.repo.get_project(project_id)
        if project.revision != project_revision:
            raise CommerceFailure('RESOURCE_CONFLICT')
        return await self._request(project_id, {'expected_revision': project_revision, 'client_request_id': request_id})

    async def execute(self, project_id, job_id, revision, action):
        job = self.jobs.read(project_id, job_id)
        if job.revision != revision:
            raise CommerceFailure('RESOURCE_CONFLICT')
        if action not in {'provision', 'verify', 'recover', 'cleanup'}:
            raise CommerceFailure('INPUT_INVALID', 422)
        return await self._request(project_id, {'expected_revision': revision, 'action': action}, job_id=job_id)
