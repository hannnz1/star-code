"""Private durable verifier journal. Receipt collection is not approval.

Claims commit before effects and never expire into a new send. Recovery may
account an existing claim, but cannot repeat it. Only digests are retained;
the actual fixed producers and independent report builder supply evidence.
This module has no HTTP endpoint, CMS write permission or report constructor.
"""
import uuid
from typing import Literal

from pydantic import Field, ValidationError
from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.media import MediaRepository
from muse.commerce.models import Contract
from muse.commerce.release import release_source_hash
from muse.commerce.release_approval import ProductReleaseApprovalRepository
from muse.commerce.repository import digest, encode

PHASES = ('reference', 'source_capture', 'staging', 'buyer', 'browser', 'facts')
Phase = Literal['reference', 'source_capture', 'staging', 'buyer', 'browser', 'facts']


class VerificationClaim(Contract):
    phase: Phase
    token: str = Field(pattern=r'^[a-f0-9]{32}$')


class VerificationReceipt(VerificationClaim):
    evidence_digest: str = Field(pattern=r'^[a-f0-9]{64}$')


class VerificationJob(Contract):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    project_id: str
    plan_id: str
    plan_revision: int = Field(ge=1, strict=True)
    revision: int = Field(ge=1, strict=True)
    source_binding: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['QUEUED', 'RUNNING', 'NEEDS_RECONCILIATION', 'CANCELLED', 'COLLECTED']
    cancel_requested: bool = False
    active: VerificationClaim | None = None
    completed: list[VerificationReceipt] = Field(default_factory=list, max_length=len(PHASES))


class VerificationJobRepository:
    def __init__(self, repo):
        self.repo, self.db = repo, repo.db

    def _source(self, conn, project_id, plan_id, revision):
        project, plan = ApprovalRepository._source(conn, project_id, plan_id)
        ProductReleaseApprovalRepository._not_cancelled(conn, plan)
        if (type(revision) is not int or plan.revision != revision or plan.state != 'VERIFYING'
                or not plan.steps or any(step.status != 'SUCCEEDED' or not step.output_hash for step in plan.steps)):
            raise CommerceFailure('REVIEW_STALE')
        return self._source_binding(conn, project, plan, revision)

    def _source_binding(self, conn, project, plan, revision):
        """Pure source hash; callers separately fence phase and authority."""
        code = load_captured_code(self.repo, plan, connection=conn)
        media = {}
        from muse.commerce.design_resources import source_media_refs
        for identity in source_media_refs(plan.blueprint, plan.products):
            record, _ = MediaRepository._read(conn, project.id, identity)
            media[identity] = digest(record)
        return digest([digest(project), revision, release_source_hash(plan), code.source_digest,
            code.package.package_sha256, media])

    @staticmethod
    def _read(conn, project_id, identity):
        row = conn.execute(text("SELECT plan_id,data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='verification_job'"),
            {'id': identity, 'project': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            job = VerificationJob.model_validate_json(row['data'])
            completed = [receipt.phase for receipt in job.completed]
            if (job.id != identity or job.project_id != project_id or job.plan_id != row['plan_id']
                    or digest(job) != row['digest'] or completed != list(PHASES[:len(completed)])
                    or len({receipt.token for receipt in job.completed}) != len(job.completed)
                    or (job.active and (len(completed) == len(PHASES) or job.active.phase != PHASES[len(completed)]
                        or job.active.token in {receipt.token for receipt in job.completed}))
                    or (job.state in {'RUNNING', 'NEEDS_RECONCILIATION'}) != (job.active is not None)
                    or (job.state == 'COLLECTED' and (len(completed) != len(PHASES) or job.cancel_requested))
                    or (job.state == 'QUEUED' and (len(completed) == len(PHASES) or job.cancel_requested))
                    or (job.state == 'CANCELLED' and not job.cancel_requested)):
                raise ValueError()
            return job
        except (ValueError, TypeError):
            raise CommerceFailure('RESOURCE_CONFLICT') from None

    @staticmethod
    def _write(conn, job, **updates):
        saved = job.model_copy(update={'revision': job.revision + 1, **updates})
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
            {'id': job.id, 'data': encode(saved), 'digest': digest(saved)})
        return saved

    def read(self, project_id, identity):
        with self.db.engine.connect() as conn:
            return self._read(conn, project_id, identity)

    def queued(self, project_id):
        with self.db.engine.connect() as conn:
            self.repo._project(conn, project_id)
            queued, after = [], 0
            while len(queued) < 100:
                rows = conn.execute(text("SELECT rowid AS position,id FROM commerce_artifacts WHERE project_id=:project AND kind='verification_job' AND rowid>:after ORDER BY rowid LIMIT 100"),
                    {'project': project_id, 'after': after}).mappings().all()
                if not rows:
                    break
                for row in rows:
                    after = row['position']
                    job = self._read(conn, project_id, row['id'])
                    if job.state == 'QUEUED':
                        queued.append(job)
                    if len(queued) == 100:
                        break
            return queued

    def reserve(self, project_id, plan_id, plan_revision, request_id):
        with self.db.transaction() as conn:
            return self._reserve(conn, project_id, plan_id, plan_revision, request_id)

    def _reserve(self, conn, project_id, plan_id, plan_revision, request_id):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
            raise CommerceFailure('INPUT_INVALID', 422)
        request = digest([project_id, 'verification_request', request_id])
        binding = self._source(conn, project_id, plan_id, plan_revision)
        fingerprint = digest([plan_id, plan_revision, binding])
        old = conn.execute(text("SELECT plan_id,data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='verification_request'"),
            {'id': request, 'project': project_id, 'plan': plan_id}).mappings().first()
        if old:
            if old['plan_id'] != plan_id or old['digest'] != fingerprint:
                raise CommerceFailure('RESOURCE_CONFLICT')
            return self._read(conn, project_id, old['data'])
        # A new request identifier cannot create another buyer environment
        # for the same immutable source while its original job still exists.
        for row in conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='verification_job'"),
                {'project': project_id, 'plan': plan_id}).mappings():
            if self._read(conn, project_id, row['id']).source_binding == binding:
                raise CommerceFailure('RESOURCE_CONFLICT')
        job = VerificationJob(id=uuid.uuid4().hex, project_id=project_id, plan_id=plan_id,
            plan_revision=plan_revision, revision=1, source_binding=binding, state='QUEUED')
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'verification_job',:digest,:data)"),
            {'id': job.id, 'project': project_id, 'plan': plan_id, 'digest': digest(job), 'data': encode(job)})
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'verification_request',:digest,:data)"),
            {'id': request, 'project': project_id, 'plan': plan_id, 'digest': fingerprint, 'data': job.id})
        self.repo.event(conn, project_id, 'verification_reserved', {'job_id': job.id, 'plan_id': plan_id})
        return job

    def claim(self, project_id, identity, expected_revision, phase):
        with self.db.transaction() as conn:
            job = self._read(conn, project_id, identity)
            if (type(expected_revision) is not int or job.revision != expected_revision or job.state != 'QUEUED'
                    or phase != PHASES[len(job.completed)]):
                raise CommerceFailure('RESOURCE_CONFLICT')
            if self._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding:
                raise CommerceFailure('REVIEW_STALE')
            return self._write(conn, job, state='RUNNING', active=VerificationClaim(phase=phase, token=uuid.uuid4().hex))

    def record(self, project_id, identity, token, evidence_digest):
        try:
            receipt = VerificationReceipt(phase='reference', token=token, evidence_digest=evidence_digest)
        except ValidationError:
            raise CommerceFailure('INPUT_INVALID', 422) from None
        with self.db.transaction() as conn:
            job = self._read(conn, project_id, identity)
            prior = next((item for item in job.completed if item.token == token), None)
            if prior:
                if prior.evidence_digest != evidence_digest:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return job
            if job.active is None or job.active.token != token:
                raise CommerceFailure('RESOURCE_CONFLICT')
            # Late effect accounting is allowed after source changes/cancellation.
            # The next claim rechecks source; a receipt never renews permission.
            completed = [*job.completed, receipt.model_copy(update={'phase': job.active.phase})]
            state = 'CANCELLED' if job.cancel_requested else ('COLLECTED' if len(completed) == len(PHASES) else 'QUEUED')
            return self._write(conn, job, state=state, active=None, completed=completed)

    def interrupt(self, project_id, identity, expected_revision):
        with self.db.transaction() as conn:
            job = self._read(conn, project_id, identity)
            if type(expected_revision) is not int or job.revision != expected_revision or job.state != 'RUNNING':
                raise CommerceFailure('RESOURCE_CONFLICT')
            return self._write(conn, job, state='NEEDS_RECONCILIATION')

    def cancel(self, project_id, identity, expected_revision):
        with self.db.transaction() as conn:
            job = self._read(conn, project_id, identity)
            if type(expected_revision) is not int or job.revision != expected_revision or job.state in {'CANCELLED', 'COLLECTED'}:
                raise CommerceFailure('RESOURCE_CONFLICT')
            return self._write(conn, job, cancel_requested=True,
                state='NEEDS_RECONCILIATION' if job.active else 'CANCELLED')
