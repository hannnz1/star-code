"""Private per-verification reference ownership. Never mutates store settings.

Attach before provisioning, require READY plus its accounted receipt before
materialization. A derived staging target does not register a business target,
renew a grant or provide publication authority.
"""
from pydantic import Field
from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Contract, EnvironmentRef
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.repository import digest, encode
from muse.commerce.verification_jobs import VerificationJobRepository


class VerificationReference(Contract):
    verification_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    project_id: str
    plan_id: str
    source_binding: str = Field(pattern=r'^[a-f0-9]{64}$')
    claim_token: str = Field(pattern=r'^[a-f0-9]{32}$')
    reference_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class VerificationTargetRepository:
    def __init__(self, jobs):
        if not isinstance(jobs, VerificationJobRepository):
            raise TypeError('A private verification journal is required')
        self.jobs, self.repo, self.db = jobs, jobs.repo, jobs.db

    @staticmethod
    def _id(verification_id):
        return digest([verification_id, 'verification_reference'])

    @staticmethod
    def _owner(reference_id):
        return digest([reference_id, 'verification_reference_owner'])

    @classmethod
    def _read(cls, conn, project_id, identity):
        row = conn.execute(text("SELECT plan_id,data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='verification_reference'"),
            {'id': identity, 'project': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            binding = VerificationReference.model_validate_json(row['data'])
            owner = conn.execute(text("SELECT project_id,plan_id,data,digest FROM commerce_artifacts WHERE id=:id AND kind='verification_reference_owner'"),
                {'id': cls._owner(binding.reference_id)}).mappings().first()
            if (binding.project_id != project_id or binding.plan_id != row['plan_id']
                    or cls._id(binding.verification_id) != identity or digest(binding) != row['digest']
                    or not owner or owner['project_id'] != project_id or owner['plan_id'] != binding.plan_id
                    or owner['data'] != encode(binding) or owner['digest'] != digest(binding)):
                raise ValueError()
            return binding
        except (ValueError, TypeError):
            raise CommerceFailure('RESOURCE_CONFLICT') from None

    def attach(self, project_id, verification_id, claim_token, reference_id):
        with self.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, verification_id)
            if (job.state != 'RUNNING' or job.active.phase != 'reference' or job.active.token != claim_token
                    or job.cancel_requested or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            identity = self._id(verification_id)
            if conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': identity}).first():
                old = self._read(conn, project_id, identity)
                if old.claim_token != claim_token or old.reference_id != reference_id:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return old
            ref = ReferenceJobRepository._read(conn, project_id, reference_id)
            project = self.repo._project(conn, project_id)
            if (ref.state != 'RESERVED' or ref.project_revision != project.revision or ref.project_hash != digest(project)
                    or any(target.connector_ref == 'ref-' + ref.id for target in project.environment_refs)
                    or conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': self._owner(reference_id)}).first()):
                raise CommerceFailure('RESOURCE_CONFLICT')
            binding = VerificationReference(verification_id=job.id, project_id=project_id, plan_id=job.plan_id,
                source_binding=job.source_binding, claim_token=claim_token, reference_id=ref.id)
            for key, kind in [(identity, 'verification_reference'), (self._owner(ref.id), 'verification_reference_owner')]:
                conn.execute(text('INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,:kind,:digest,:data)'),
                    {'id': key, 'project': project_id, 'plan': job.plan_id, 'kind': kind,
                     'digest': digest(binding), 'data': encode(binding)})
            return binding

    def _target(self, conn, project_id, plan_id):
        project, plan = ApprovalRepository._source(conn, project_id, plan_id)
        rows = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='verification_reference'"),
            {'project': project_id, 'plan': plan_id}).mappings().all()
        if not rows:
            return None
        candidates = []
        for row in rows:
            binding = self._read(conn, project_id, row['id'])
            job = self.jobs._read(conn, project_id, binding.verification_id)
            if job.plan_revision != plan.revision:
                if plan.state == 'VERIFYING':
                    continue  # Earlier sources cannot displace a newer verification.
                from muse.commerce.trusted_verifier import reviewed_source
                reviewed_source(conn, self.jobs, job)
                source_binding = self.jobs._source_binding(conn, project, plan, job.plan_revision)
            else:
                source_binding = self.jobs._source(conn, project_id, plan_id, job.plan_revision)
            if (job.plan_id != plan_id or job.cancel_requested or job.state == 'CANCELLED'
                    or binding.source_binding != job.source_binding
                    or source_binding != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            ref = ReferenceJobRepository._read(conn, project_id, binding.reference_id)
            if (ref.state != 'READY' or ref.project_hash != digest(project) or ref.project_revision != project.revision
                    or not job.completed or job.completed[0].phase != 'reference'
                    or job.completed[0].token != binding.claim_token
                    or job.completed[0].evidence_digest != digest([binding.model_dump(mode='json'), ref.evidence])):
                raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
            candidates.append(EnvironmentRef(id='verification-' + job.id, project_id=project_id, environment='staging',
                connector_ref='ref-' + ref.id, public_url='http://127.0.0.1:' + str(ref.port)))
        if len(candidates) != 1:
            raise CommerceFailure('REVIEW_STALE')
        return candidates[0]

    def target(self, project_id, plan_id):
        with self.db.transaction() as conn:
            target = self._target(conn, project_id, plan_id)
            if target is None:
                raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
            return target

    def prepare_source(self, project_id, plan_id, snapshot, absence_proofs, images, *, connection):
        from muse.commerce.staging_source import prepare_staging_source
        with self.db.transaction() as conn:
            target = self._target(conn, project_id, plan_id)
            if target is None:
                raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
            project, plan = ApprovalRepository._source(conn, project_id, plan_id)
            code = load_captured_code(self.repo, plan, connection=conn)
            # Adapt the pure declaration builder only. This copy is never saved
            # and gives no CMS/merchant permission; authorization reads binding.
            scoped = project.model_copy(update={'environment_refs': [*project.environment_refs, target]})
            return prepare_staging_source(scoped, plan, target, snapshot, code, absence_proofs, images, connection=connection)
