"""Independent host service for fixed reference jobs; never a model tool."""
import re

import httpx

from muse.commerce.errors import CommerceFailure
from muse.commerce.reference_environment import ReferenceAssetBundle


class ReferenceEnvironmentService:
    def __init__(self, jobs, runner, bundle, *, ports):
        if (not isinstance(bundle, ReferenceAssetBundle) or not isinstance(ports, tuple)
                or not 1 <= len(ports) <= 32 or len(set(ports)) != len(ports)
                or any(type(port) is not int or not 1024 <= port <= 65535 for port in ports)):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        self.jobs, self.runner, self.bundle, self.ports = jobs, runner, bundle, ports

    def reserve(self, project_id, project_revision, request_id):
        # The authenticated caller never supplies a target URL, image or port.
        self.jobs.repo.get_project(project_id)
        for port in self.ports:
            try:
                return self.jobs.reserve(project_id, project_revision, request_id, self.bundle.source_digest, port)
            except CommerceFailure as error:
                if error.public.code != 'RESOURCE_CONFLICT':
                    raise
        raise CommerceFailure('RESOURCE_CONFLICT')

    def read(self, project_id, job_id):
        return self.jobs.read(project_id, job_id)

    def resolve_connection(self, connection_id, project_id):
        if not isinstance(connection_id, str) or not re.fullmatch(r'ref-[a-f0-9]{32}', connection_id):
            raise CommerceFailure('NOT_FOUND', 404)
        job = self.jobs.read(project_id, connection_id[4:])
        if job.state != 'READY' or job.asset_digest != self.bundle.source_digest:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            return self.runner._connection(job)
        except (ValueError, TypeError, KeyError, OSError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    async def execute(self, project_id, job_id, revision, action, *, _before_bootstrap=None, _code=None):
        job = self.jobs.read(project_id, job_id)
        if job.revision != revision:
            raise CommerceFailure('RESOURCE_CONFLICT')
        if action not in {'provision', 'verify', 'recover', 'cleanup'}:
            raise CommerceFailure('INPUT_INVALID', 422)
        if _before_bootstrap is not None and (action != 'provision' or not callable(_before_bootstrap)):
            raise CommerceFailure('INPUT_INVALID', 422)
        if _code is not None and action != 'verify':
            raise CommerceFailure('INPUT_INVALID', 422)
        try:
            if action == 'provision':
                if job.state != 'RESERVED':
                    raise CommerceFailure('RESOURCE_CONFLICT')
                project = self.jobs.repo.get_project(project_id)
                await self.runner.prepare(job, self.bundle)
                if _before_bootstrap is not None:
                    _before_bootstrap()  # Private verifier cancellation/source fence; never API input.
                current = self.jobs.read(project_id, job_id)
                await self.runner.bootstrap(current, self.bundle, currency=project.brief.currency, language=project.brief.language)
            elif action == 'verify':
                if _code is None:
                    await self.runner.verify(job, self.bundle)
                else:
                    await self.runner.verify(job, self.bundle, _code=_code)
            elif action == 'recover':
                # Inventory only, not approval or CMS readiness evidence.
                return await self.runner.recover(job)
            else:
                await self.runner.cleanup(job)
            return self.jobs.read(project_id, job_id)
        except (OSError, TimeoutError, ValueError, TypeError, httpx.HTTPError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
