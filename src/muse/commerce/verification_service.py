"""Host service for fixed verification and safe status. No report upload."""
import asyncio
from typing import Literal

from pydantic import Field
from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Contract
from muse.commerce.release_approval import ProductReleaseApprovalRepository as Records
from muse.commerce.repository import digest, encode
from muse.commerce.trusted_verifier import TrustedMerchantVerifier
from muse.commerce.verification_runtime import VerificationRuntime
from muse.commerce_connector.wordpress import WordPressConnection


class VerificationStatus(Contract):
    id: str
    project_id: str
    plan_id: str
    plan_revision: int
    revision: int
    state: Literal['QUEUED', 'RUNNING', 'NEEDS_RECONCILIATION', 'CANCELLED', 'COLLECTED', 'REVIEW_REQUIRED']
    phase: str | None = None
    completed_phases: list[str]
    cancel_requested: bool
    error_code: str | None = Field(default=None, pattern=r'^[A-Z_]+$')


class VerificationStatusRepository:
    def __init__(self, jobs):
        self.jobs = jobs

    @staticmethod
    def _marker_id(job): return digest([job.id, 'verification_finalization'])

    def _marker(self, conn, job):
        key = self._marker_id(job)
        if not conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': key}).first():
            return None
        row, value = Records._read(conn, key, 'verification_finalization')
        if (row['project_id'] != job.project_id or row['plan_id'] != job.plan_id
                or set(value) != {'job_digest', 'source_binding', 'state', 'error_code'}
                or value['job_digest'] != digest(job) or value['source_binding'] != job.source_binding
                or value['state'] not in {'UNKNOWN', 'FAILED', 'REVIEW_REQUIRED'}):
            raise CommerceFailure('REVIEW_STALE')
        return value

    def _view(self, conn, job):
        marker = None if job.cancel_requested else self._marker(conn, job)
        state = job.state
        if marker:
            state = 'REVIEW_REQUIRED' if marker['state'] == 'REVIEW_REQUIRED' else 'NEEDS_RECONCILIATION'
        return VerificationStatus(id=job.id, project_id=job.project_id, plan_id=job.plan_id,
            plan_revision=job.plan_revision, revision=job.revision, state=state,
            phase=job.active.phase if job.active else ('report' if marker and marker['state'] != 'REVIEW_REQUIRED' else None),
            completed_phases=[receipt.phase for receipt in job.completed], cancel_requested=job.cancel_requested,
            error_code=marker['error_code'] if marker else None)

    def read(self, project_id, identity):
        with self.jobs.db.transaction() as conn:
            return self._view(conn, self.jobs._read(conn, project_id, identity))

    def list(self, project_id, plan_id):
        with self.jobs.db.transaction() as conn:
            ApprovalRepository._source(conn, project_id, plan_id)
            rows = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan "
                "AND kind='verification_job' ORDER BY rowid DESC LIMIT 100"),
                {'project': project_id, 'plan': plan_id}).scalars().all()
            return [self._view(conn, self.jobs._read(conn, project_id, identity)) for identity in rows]



class CommerceVerificationService(VerificationStatusRepository):
    def __init__(self, runtime, connections, *, transport=None):
        if (type(runtime) is not VerificationRuntime or not isinstance(connections, dict)
                or any(not isinstance(value, WordPressConnection) or key != value.connection_id
                       for key, value in connections.items())):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.runtime, self.jobs, self.connections = runtime, runtime.jobs, dict(connections)
        self.verifier = TrustedMerchantVerifier(runtime, transport=transport)

    def reserve(self, project_id, plan_id, revision, request_id):
        if (type(revision) is not int or revision < 1 or not isinstance(request_id, str)
                or not 1 <= len(request_id) <= 200):
            raise CommerceFailure('INPUT_INVALID', 422)
        key = digest([project_id, 'verification_start_request', request_id])
        fingerprint = digest([plan_id, revision, request_id])
        with self.jobs.db.transaction() as conn:
            if conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': key}).first():
                row, value = Records._read(conn, key, 'verification_start_request')
                if (row['project_id'] != project_id or row['plan_id'] != plan_id
                        or set(value) != {'fingerprint', 'job_id'} or value['fingerprint'] != fingerprint):
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return self._view(conn, self.jobs._read(conn, project_id, value['job_id']))
            _, plan = ApprovalRepository._source(conn, project_id, plan_id)
            if plan.revision != revision:
                raise CommerceFailure('REVIEW_STALE')
            if plan.state == 'BLOCKED' and plan.error_code == 'VERIFICATION_UNAVAILABLE':
                plan = plan.model_copy(update={'state': 'VERIFYING', 'error_code': None, 'revision': revision + 1})
                conn.execute(text('UPDATE commerce_plans SET revision=:revision,data=:data WHERE id=:id'),
                    {'id': plan.id, 'revision': plan.revision, 'data': encode(plan)})
            job = self.jobs._reserve(conn, project_id, plan_id, plan.revision, request_id)
            Records._insert(conn, key, project_id, plan_id, 'verification_start_request',
                {'fingerprint': fingerprint, 'job_id': job.id})
            return self._view(conn, job)

    def cancel(self, project_id, identity, revision):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if type(revision) is not int or job.revision != revision:
                raise CommerceFailure('RESOURCE_CONFLICT')
            if job.cancel_requested: return self._view(conn, job)
            state = 'CANCELLED' if job.active is None else 'NEEDS_RECONCILIATION'
            job = self.jobs._write(conn, job, state=state, cancel_requested=True)
            self.jobs.repo.event(conn, project_id, 'verification_cancelled', {'job_id': job.id})
            return self._view(conn, job)

    async def reconcile(self, project_id, identity, revision):
        from muse.commerce.trusted_verifier import reviewed_source
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if type(revision) is not int or job.revision != revision or job.cancel_requested:
                raise CommerceFailure('RESOURCE_CONFLICT')
            marker = self._marker(conn, job)
            if marker:
                if marker['state'] == 'REVIEW_REQUIRED':
                    return self._view(conn, job)
                # Account an already committed review only. Never rerun report
                # reads, renew an expired source, or fabricate a missing anchor.
                reviewed_source(conn, self.jobs, job)
                marker.update(state='REVIEW_REQUIRED', error_code=None)
                conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                    {'id': self._marker_id(job), 'data': encode(marker), 'digest': digest(marker)})
                return self._view(conn, job)
            if job.state != 'NEEDS_RECONCILIATION' or job.active is None:
                raise CommerceFailure('RESOURCE_CONFLICT')
            phase = job.active.phase
        await self.runtime.worker.handlers[phase].reconcile(project_id, identity)
        return self.read(project_id, identity)

    async def resume_staging(self, project_id, identity, revision):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (type(revision) is not int or job.revision != revision or job.cancel_requested
                    or job.state != 'NEEDS_RECONCILIATION' or job.active is None or job.active.phase != 'staging'
                    or self._marker(conn, job) is not None):
                raise CommerceFailure('RESOURCE_CONFLICT')
        await self.runtime.worker.handlers['staging'].resume(project_id, identity, revision)
        return self.read(project_id, identity)

    def _connection(self, job):
        with self.jobs.db.transaction() as conn:
            project, _ = ApprovalRepository._source(conn, job.project_id, job.plan_id)
        candidates = []
        for target in project.environment_refs:
            connection = self.connections.get(target.connector_ref)
            if (connection and connection.project_id == job.project_id and connection.environment == target.environment
                    and connection.base_url == target.public_url):
                candidates.append(connection)
        live = [value for value in candidates if value.environment == 'live']
        candidates = live or candidates
        if len(candidates) != 1: raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        return candidates[0]

    async def _finalize_once(self, job):
        with self.jobs.db.transaction() as conn:
            current = self.jobs._read(conn, job.project_id, job.id)
            if current != job or job.state != 'COLLECTED' or job.cancel_requested or self._marker(conn, job): return
            value = {'job_digest': digest(job), 'source_binding': job.source_binding, 'state': 'UNKNOWN', 'error_code': None}
            Records._insert(conn, self._marker_id(job), job.project_id, job.plan_id, 'verification_finalization', value)
        try:
            await self.verifier.request_review(job.project_id, job.id, connection=self._connection(job))
        except asyncio.CancelledError:
            raise  # Persisted UNKNOWN survives shutdown; polling cannot replay.
        except CommerceFailure as error:
            value.update(state='FAILED', error_code=error.public.code)
        except Exception:  # noqa: BLE001 - never expose private exception text
            value.update(state='UNKNOWN', error_code='VERIFICATION_UNAVAILABLE')
        else:
            value.update(state='REVIEW_REQUIRED')
        with self.jobs.db.transaction() as conn:
            conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                {'id': self._marker_id(job), 'data': encode(value), 'digest': digest(value)})

    async def run_once(self, project_id):
        await self.runtime.run_once(project_id)
        with self.jobs.db.transaction() as conn:
            self.jobs.repo._project(conn, project_id)
            rows = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project "
                "AND kind='verification_job' ORDER BY rowid DESC LIMIT 100"), {'project': project_id}).scalars().all()
            jobs = [self.jobs._read(conn, project_id, identity) for identity in rows]
        for job in jobs:
            if job.state == 'COLLECTED' and not job.cancel_requested:
                await self._finalize_once(job)
        return [self.read(project_id, job.id) for job in jobs]

    def recover_owned(self):
        lease = getattr(self, 'host_lease', None)
        if lease is None or lease.fd is None:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        after = ''
        while True:
            with self.jobs.db.engine.connect() as conn:
                projects = conn.execute(text("SELECT DISTINCT project_id FROM commerce_artifacts "
                    "WHERE kind='verification_job' AND project_id>:after ORDER BY project_id LIMIT 100"),
                    {'after': after}).scalars().all()
            if not projects:
                return
            for project_id in projects:
                self.runtime.recover_interrupted(project_id)
                after = project_id

    async def run(self, stop):
        if not isinstance(stop, asyncio.Event): raise CommerceFailure('INPUT_INVALID', 422)
        after = ''
        while not stop.is_set():
            with self.jobs.db.engine.connect() as conn:
                projects = conn.execute(text("SELECT DISTINCT project_id FROM commerce_artifacts "
                    "WHERE kind='verification_job' AND project_id>:after ORDER BY project_id LIMIT 100"),
                    {'after': after}).scalars().all()
            for project_id in projects:
                if stop.is_set(): break
                await self.run_once(project_id)
                after = project_id
            if not projects: after = ''
            try: await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError: pass
