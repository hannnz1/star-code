"""Host-only browser/facts stages with immutable, claim-bound readback evidence."""
import json

from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.code_bridge import load_captured_code
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.preview import capture_staging_preview
from muse.commerce.preview_repository import PreviewRepository
from muse.commerce.repository import digest, encode
from muse.commerce.source_capture_stage import SourceCaptureStage
from muse.commerce.verification import verify_staging_facts
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce_connector.wordpress import WordPressReader


class ReadbackVerificationStage:
    def __init__(self, jobs, source, phase, *, transport=None):
        if (not isinstance(jobs, VerificationJobRepository) or not isinstance(source, SourceCaptureStage)
                or source.jobs is not jobs or phase not in {'browser', 'facts'}):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.jobs, self.source, self.phase, self.transport = jobs, source, phase, transport

    def _current(self, project_id, identity, *, token=None, state='RUNNING'):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (job.state != state or job.cancel_requested or job.active is None or job.active.phase != self.phase
                    or (token is not None and job.active.token != token)
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            return job

    def evidence(self, project_id, identity):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (job.cancel_requested or job.state == 'CANCELLED'
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            receipt = next((item for item in job.completed if item.phase == self.phase), None)
            token = receipt.token if receipt else (job.active.token if job.active and job.active.phase == self.phase else None)
            key = digest([job.id, self.phase, token, 'readback'])
            row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='verification_readback'"),
                {'id': key, 'project': project_id, 'plan': job.plan_id}).mappings().first()
            if row is None:
                raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
            try:
                value = json.loads(row['data'])
                if (digest(value) != row['digest'] or value['source_binding'] != job.source_binding
                        or value['claim_token'] != token or value['phase'] != self.phase
                        or (receipt and receipt.evidence_digest != row['digest'])):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise CommerceFailure('REVIEW_STALE') from None
            previews = PreviewRepository(self.jobs.repo)
            preview = previews._report(conn, project_id, job.plan_id, job.plan_revision, value['preview_id'])
            if not preview.passed or preview.snapshot_hash != value['snapshot_hash']:
                raise CommerceFailure('REVIEW_STALE')
        # Re-read each PNG through its independent integrity/geometry checks.
        for frame in preview.frames:
            previews.image(project_id, job.plan_id, preview.id, frame.id, job.plan_revision)
        with self.jobs.db.transaction() as conn:
            current = self.jobs._read(conn, project_id, identity)
            if (current != job or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            return value

    async def __call__(self, claimed):
        job = self._current(claimed.project_id, claimed.id, token=claimed.active.token)
        grant = self.source.source(job.project_id, job.id, staged=True)
        connection = self.source._connection(job)
        intent, history = self.source.sources.verification_source(grant.id, connection)
        prior = next((item for item in job.completed if item.phase == 'staging'), None)
        if prior is None or prior.evidence_digest != digest([job.source_binding, intent.digest, grant.id,
                [item.receipt.model_dump(mode='json') for item in history]]):
            raise CommerceFailure('REVIEW_STALE')
        reader = WordPressReader(connection, transport=self.transport)
        raw = await reader.read('snapshot', remaining_seconds=30)
        snapshot = normalize_snapshot(raw, job.project_id, 'staging')
        media_proofs = {}
        for image in intent.images:
            self._current(job.project_id, job.id, token=job.active.token)
            proof = await reader.read_media_sha256(image.image.sha256, remaining_seconds=20)
            media_proofs[proof['resource_key']] = proof
        with self.jobs.db.transaction() as conn:
            _, plan = ApprovalRepository._source(conn, job.project_id, job.plan_id)
            code = load_captured_code(self.jobs.repo, plan, connection=conn)
        facts = verify_staging_facts(plan, code, snapshot, connection=connection,
            images=intent.images, media_proofs=media_proofs)
        value = {'phase': self.phase, 'claim_token': job.active.token, 'source_binding': job.source_binding,
            'staging_intent': intent.digest, 'snapshot_hash': digest(snapshot), 'facts': facts}
        fixture = None
        if not any(product.stock >= 1 for product in intent.products):
            from muse.commerce.buyer_fixture import BuyerFixtureRepository
            with self.jobs.db.transaction() as conn:
                fixture = BuyerFixtureRepository.read(conn, self.jobs, job.project_id, job.plan_id,
                    connection.connection_id[4:], intent)
        if self.phase == 'browser':
            capture = await capture_staging_preview(plan, code, snapshot, connection,
                images=intent.images, media_proofs=media_proofs, fixture=fixture)
            self._current(job.project_id, job.id, token=job.active.token)
            if capture.snapshot_hash != digest(snapshot):
                raise CommerceFailure('REVIEW_STALE')
            preview = PreviewRepository(self.jobs.repo).save(job.project_id, job.plan_id, job.plan_revision, capture)
            if not preview.passed:
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            value['preview_id'] = preview.id
        else:
            browser = ReadbackVerificationStage(self.jobs, self.source, 'browser').evidence(job.project_id, job.id)
            if browser['snapshot_hash'] != digest(snapshot) or browser['staging_intent'] != intent.digest:
                raise CommerceFailure('REVIEW_STALE')
            value['preview_id'] = browser['preview_id']
        self._current(job.project_id, job.id, token=job.active.token)
        with self.jobs.db.transaction() as conn:
            current = self.jobs._read(conn, job.project_id, job.id)
            if (current != job or self.jobs._source(conn, job.project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            key = digest([job.id, self.phase, job.active.token, 'readback'])
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'verification_readback',:digest,:data)"),
                {'id': key, 'project': job.project_id, 'plan': job.plan_id, 'digest': digest(value), 'data': encode(value)})
        return digest(value)

    async def reconcile(self, project_id, identity):
        job = self._current(project_id, identity, state='NEEDS_RECONCILIATION')
        value = self.evidence(project_id, identity)
        current = self._current(project_id, identity, token=job.active.token, state='NEEDS_RECONCILIATION')
        return self.jobs.record(project_id, identity, current.active.token, digest(value))
