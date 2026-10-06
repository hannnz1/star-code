"""Fixed buyer stage; a bound independent order readback is not final approval."""
from muse.commerce.buyer_sender import SyntheticBuyer
from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce.source_capture_stage import SourceCaptureStage
from muse.commerce.verification_jobs import VerificationJobRepository


class BuyerVerificationStage:
    def __init__(self, jobs, source, sender):
        if (not isinstance(jobs, VerificationJobRepository) or not isinstance(source, SourceCaptureStage)
                or source.jobs is not jobs or not isinstance(sender, SyntheticBuyer)
                or sender.sources is not source.sources or sender.jobs is not source.service.jobs
                or sender.runner is not source.service.runner or sender.probes.db is not jobs.db):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.jobs, self.source, self.sender = jobs, source, sender

    def _current(self, project_id, identity, *, token=None, state='RUNNING'):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (job.state != state or job.cancel_requested or job.active is None or job.active.phase != 'buyer'
                    or (token is not None and job.active.token != token)
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            return job

    def _input(self, job):
        grant = self.source.source(job.project_id, job.id, staged=True)
        connection = self.source._connection(job)
        intent, history = self.source.sources.verification_source(grant.id, connection)
        staging = next((item for item in job.completed if item.phase == 'staging'), None)
        expected = digest([job.source_binding, intent.digest, grant.id,
            [item.receipt.model_dump(mode='json') for item in history]])
        if staging is None or staging.evidence_digest != expected:
            raise CommerceFailure('REVIEW_STALE')
        candidates = [product for product in intent.products if product.stock >= 1]
        if candidates:
            sku = candidates[0].sku
        else:
            from muse.commerce.buyer_fixture import BuyerFixtureRepository
            with self.jobs.db.transaction() as conn:
                sku = BuyerFixtureRepository.read(conn, self.jobs, job.project_id, job.plan_id,
                    connection.connection_id[4:], intent).draft.sku
        return grant, connection.connection_id[4:], sku, intent

    async def _prepare_fixture(self, job):
        from sqlalchemy import text

        from muse.commerce.buyer_fixture import BuyerFixtureRepository
        from muse.commerce.release_approval import (
            ProductReleaseApprovalRepository as Records,
        )
        grant = self.source.source(job.project_id, job.id, staged=True)
        connection = self.source._connection(job)
        intent, _ = self.source.sources.verification_source(grant.id, connection)
        if any(product.stock >= 1 for product in intent.products):
            return
        product = await self.sender.disposable_product(job.project_id, connection.connection_id[4:],
            currency=intent.blueprint.required_settings['currency'])
        proof = {'job_id': product.job_id, 'project_id': product.project_id, 'connection_id': product.connection_id,
            'product_id': product.product_id, 'sku': product.draft.sku, 'title': product.draft.title,
            'price': str(product.draft.price), 'currency': product.draft.currency, 'stock_quantity': product.draft.stock,
            'status': 'publish', 'catalog_visibility': 'hidden', 'fixture_only': True}
        with self.jobs.db.transaction() as conn:
            current = self.jobs._read(conn, job.project_id, job.id)
            frozen, history = self.source.sources._verification_source(conn, grant.id, connection, fresh=True)
            staging = next((receipt for receipt in job.completed if receipt.phase == 'staging'), None)
            if (current != job or job.cancel_requested or frozen != intent or staging is None
                    or staging.evidence_digest != digest([job.source_binding, intent.digest, grant.id,
                        [item.receipt.model_dump(mode='json') for item in history]])
                    or self.jobs._source(conn, job.project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            value = {'verification_job_id': job.id, 'source_binding': job.source_binding,
                'staging_intent': intent.digest, 'proof': proof}
            key = BuyerFixtureRepository.key(job.project_id, job.plan_id, product.job_id)
            if conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': key}).first():
                _, old = Records._read(conn, key, 'buyer_fixture_binding')
                if old != value: raise CommerceFailure('RESOURCE_CONFLICT')
            else:
                Records._insert(conn, key, job.project_id, job.plan_id, 'buyer_fixture_binding', value)
            BuyerFixtureRepository.read(conn, self.jobs, job.project_id, job.plan_id, product.job_id, intent)

    @staticmethod
    def _evidence(job, intent, reference_id, sku, saved):
        if (saved.project_id != job.project_id or saved.plan_id != job.plan_id
                or saved.source.job_id != reference_id or saved.source.sku != sku
                or saved.source.source_digest != intent.source_digest
                or saved.source.staging_intent_digest != intent.digest):
            raise CommerceFailure('REVIEW_STALE')
        return digest(saved)

    async def __call__(self, claimed):
        job = self._current(claimed.project_id, claimed.id, token=claimed.active.token)
        await self._prepare_fixture(job)
        grant, reference_id, sku, intent = self._input(job)
        saved = await self.sender.send(job.project_id, job.plan_id, reference_id, grant.id, sku)
        self._current(job.project_id, job.id, token=job.active.token)
        return self._evidence(job, intent, reference_id, sku, saved)

    async def reconcile(self, project_id, identity):
        job = self._current(project_id, identity, state='NEEDS_RECONCILIATION')
        _grant, reference_id, sku, intent = self._input(job)
        probe_id = digest([project_id, job.plan_id, 'buyer_probe', reference_id])
        saved = await self.sender.reconcile(project_id, job.plan_id, probe_id)
        current = self._current(project_id, identity, token=job.active.token, state='NEEDS_RECONCILIATION')
        return self.jobs.record(project_id, identity, current.active.token,
            self._evidence(current, intent, reference_id, sku, saved))
