"""Host-only source capture for an owned verification reference environment.

Reads fixed CMS identities, captures the exact sealed theme in the existing
Docker boundary and persists staging authorization. It cannot publish, create
a merchant report or retry a missing capture during reconciliation.
"""
import time
from dataclasses import asdict

from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.media import MediaRepository
from muse.commerce.repository import digest
from muse.commerce.staging_source import StagingSourceRepository
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce.verification_target import VerificationTargetRepository
from muse.commerce_connector.media import MediaPayload, prepare_media_operation
from muse.commerce_connector.reference_service import ReferenceEnvironmentService
from muse.commerce_connector.wordpress import WordPressConnection, WordPressReader


class SourceCaptureStage:
    def __init__(self, jobs, service, boundary_factory, *, transport=None, clock=time.time):
        if (not isinstance(jobs, VerificationJobRepository)
                or not isinstance(service, ReferenceEnvironmentService) or service.jobs.db is not jobs.db
                or not callable(boundary_factory) or not callable(clock)):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.jobs, self.service, self.boundary_factory = jobs, service, boundary_factory
        self.targets = VerificationTargetRepository(jobs)
        self.sources = StagingSourceRepository(jobs.repo, clock=clock)
        self.transport, self.clock = transport, clock

    def _current(self, project_id, identity, *, token=None, state='RUNNING'):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (job.state != state or job.cancel_requested or job.active is None
                    or job.active.phase != 'source_capture' or (token is not None and job.active.token != token)
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            return job

    def _connection(self, job):
        target = self.targets.target(job.project_id, job.plan_id)
        connection = self.service.resolve_connection(target.connector_ref, job.project_id)
        if (not isinstance(connection, WordPressConnection) or connection.project_id != job.project_id
                or connection.connection_id != target.connector_ref or connection.environment != 'staging'
                or connection.base_url != target.public_url):
            raise CommerceFailure('REVIEW_STALE')
        return connection

    def source(self, project_id, identity, *, staged=False, accounting=False):
        """Read exactly one still-current authorization; never renew or create it."""
        job = self.jobs.read(project_id, identity)
        connection = self._connection(job)
        with self.jobs.db.transaction() as conn:
            rows = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='staging_source'"),
                {'project': project_id, 'plan': job.plan_id}).mappings().all()
            matches = []
            for row in rows:
                _, value = self.sources._read(conn, row['id'], 'staging_source')
                if value['intent']['target']['connector_ref'] == connection.connection_id:
                    matches.append(self.sources.grant_type(**value['grant']))
        if len(matches) != 1:
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        grant = matches[0]
        receipt = next((item for item in job.completed if item.phase == 'source_capture'), None)
        if receipt is not None and receipt.evidence_digest != digest(asdict(grant)):
            raise CommerceFailure('REVIEW_STALE')
        if staged:
            self.sources.verification_source(grant.id, connection)
            return grant
        if accounting:
            return grant  # Identity only; cannot authorize a new write.
        return self.sources.load(grant.id, connection).grant

    async def __call__(self, claimed):
        job = self._current(claimed.project_id, claimed.id, token=claimed.active.token)
        connection = self._connection(job)
        reader = WordPressReader(connection, transport=self.transport)
        deadline = time.monotonic() + 180

        def remaining():
            self._current(job.project_id, job.id, token=job.active.token)
            budget = deadline - time.monotonic()
            if budget <= 0:
                raise CommerceFailure('READ_TEMPORARY_FAILURE', 503)
            return budget

        snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=remaining()), job.project_id, 'staging')
        with self.jobs.db.transaction() as conn:
            _, plan = ApprovalRepository._source(conn, job.project_id, job.plan_id)
        proofs = {}
        for page in plan.blueprint.pages:
            if page.kind != 'product':
                proof = await reader.read_page_slug(page.slug, remaining_seconds=remaining())
                proofs[proof['resource_key']] = proof
        from muse.commerce.merchant_release import preview_category_products
        for product in [*plan.products,*preview_category_products('build_site',plan.blueprint,plan.products)]:
            proof = await reader.read_sku(product.sku, remaining_seconds=remaining())
            proofs[proof['resource_key']] = proof
        images = []
        from muse.commerce.design_resources import source_media_refs
        refs = source_media_refs(plan.blueprint, plan.products)
        for ref in refs:
            record, _ = MediaRepository(self.jobs.repo).content(job.project_id, ref)
            proof = await reader.read_media_sha256(record.image.sha256, remaining_seconds=remaining())
            proofs[proof['resource_key']] = proof
            operation = prepare_media_operation(self.jobs.repo, job.project_id, ref, proof, 'capture-' + job.id)
            images.append(MediaPayload.model_validate(operation.payload))
        remaining()
        intent = self.targets.prepare_source(job.project_id, job.plan_id, snapshot, proofs, images, connection=connection)
        grant = await self.sources.authorize(intent, connection=connection, expected_plan_revision=job.plan_revision,
            boundary=self.boundary_factory())
        self._current(job.project_id, job.id, token=job.active.token)
        return digest(asdict(grant))

    async def reconcile(self, project_id, identity):
        job = self._current(project_id, identity, state='NEEDS_RECONCILIATION')
        grant = self.source(project_id, identity)
        current = self._current(project_id, identity, token=job.active.token, state='NEEDS_RECONCILIATION')
        return self.jobs.record(project_id, identity, current.active.token, digest(asdict(grant)))
