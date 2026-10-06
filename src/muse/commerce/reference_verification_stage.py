"""Host-only reference stage for the fixed verifier worker.

No configured URL, password, script or model request comes from the job. The
existing reference service owns its fixed port pool/offline assets/runner.
Unknown results reconcile by verify only; resources are never re-provisioned.
"""
from muse.commerce.approval import ApprovalRepository
from muse.commerce.errors import CommerceFailure
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.repository import digest
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce.verification_target import VerificationTargetRepository
from muse.commerce_connector.reference_service import ReferenceEnvironmentService


class ReferenceVerificationStage:
    def __init__(self, jobs, service):
        if (not isinstance(jobs, VerificationJobRepository) or not isinstance(service, ReferenceEnvironmentService)
                or service.jobs.db is not jobs.db):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.jobs, self.service, self.targets = jobs, service, VerificationTargetRepository(jobs)

    def _current(self, project_id, identity, *, token=None, state='RUNNING'):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (job.state != state or job.cancel_requested or job.active is None or job.active.phase != 'reference'
                    or (token is not None and job.active.token != token)
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            return job

    def _binding(self, job):
        with self.jobs.db.transaction() as conn:
            binding = self.targets._read(conn, job.project_id, self.targets._id(job.id))
            if (binding.plan_id != job.plan_id or binding.source_binding != job.source_binding
                    or binding.claim_token != job.active.token):
                raise CommerceFailure('REVIEW_STALE')
            ref = ReferenceJobRepository._read(conn, job.project_id, binding.reference_id)
            if ref.asset_digest != self.service.bundle.source_digest:
                raise CommerceFailure('REVIEW_STALE')
            return binding, ref

    def _evidence(self, job):
        binding, ref = self._binding(job)
        if ref.state != 'READY':
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        return digest([binding.model_dump(mode='json'), ref.evidence])

    async def __call__(self, claimed):
        job = self._current(claimed.project_id, claimed.id, token=claimed.active.token)
        with self.jobs.db.transaction() as conn:
            project, _ = ApprovalRepository._source(conn, job.project_id, job.plan_id)
        ref = self.service.reserve(job.project_id, project.revision, 'verification-' + job.id)
        self.targets.attach(job.project_id, job.id, job.active.token, ref.id)
        self._current(job.project_id, job.id, token=job.active.token)
        await self.service.execute(job.project_id, ref.id, ref.revision, 'provision',
            _before_bootstrap=lambda: self._current(job.project_id, job.id, token=job.active.token))
        current = self._current(job.project_id, job.id, token=job.active.token)
        return self._evidence(current)

    async def reconcile(self, project_id, identity):
        job = self._current(project_id, identity, state='NEEDS_RECONCILIATION')
        _, ref = self._binding(job)
        if ref.state not in {'UNKNOWN', 'READY'}:
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        # No reserve, prepare, bootstrap, creation, deletion or credential rotation.
        await self.service.execute(project_id, ref.id, ref.revision, 'verify')
        current = self._current(project_id, identity, token=job.active.token, state='NEEDS_RECONCILIATION')
        return self.jobs.record(project_id, identity, current.active.token, self._evidence(current))
