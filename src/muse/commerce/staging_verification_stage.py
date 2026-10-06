"""Fixed preview deployment stage using the existing v5 broker and journals.

This stage cannot produce merchant verification or live authorization. A lost
reply stops the phase; explicit reconciliation only reads/accounts a pending
operation and cannot deploy the remaining steps.
"""
from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce.source_capture_stage import SourceCaptureStage
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce_connector.staging_publisher import StagingReleasePublisher


class StagingVerificationStage:
    def __init__(self, jobs, source, publisher_factory):
        if (not isinstance(jobs, VerificationJobRepository) or not isinstance(source, SourceCaptureStage)
                or source.jobs is not jobs or not callable(publisher_factory)):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.jobs, self.source, self.publisher_factory = jobs, source, publisher_factory

    def _current(self, project_id, identity, *, token=None, state='RUNNING'):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (job.state != state or job.cancel_requested or job.active is None or job.active.phase != 'staging'
                    or (token is not None and job.active.token != token)
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            return job

    def _publisher(self, job):
        connection = self.source._connection(job)
        publisher = self.publisher_factory(connection)
        if (not isinstance(publisher, StagingReleasePublisher) or publisher.connection != connection
                or publisher.approvals is not self.source.sources):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        return publisher

    def _evidence(self, job, publisher, grant):
        intent, history = self.source.sources.verification_source(grant.id, publisher.connection)
        if not history or len(history) != len(intent.steps):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        # The source repository independently validates every persisted effect.
        return digest([job.source_binding, intent.digest, grant.id,
            [item.receipt.model_dump(mode='json') for item in history]])

    async def __call__(self, claimed):
        job = self._current(claimed.project_id, claimed.id, token=claimed.active.token)
        grant = self.source.source(job.project_id, job.id)
        publisher = self._publisher(job)
        progress = publisher.journal.progress(grant.id, publisher.connection)
        if progress['completed_steps'] != 0 or publisher.journal.pending(grant.id, publisher.connection) is not None:
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        return await self._send_remaining(job, publisher, grant, 0, progress['total_steps'])

    async def _send_remaining(self, job, publisher, grant, start, total):
        for index in range(start, total):
            self._current(job.project_id, job.id, token=job.active.token)
            if publisher.journal.pending(grant.id, publisher.connection) is not None:
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            result = await publisher.publish_next(grant.id)
            if (result.index != index or result.state != 'SUCCEEDED' or not result.effect_verified
                    or publisher.journal.progress(grant.id, publisher.connection)['completed_steps'] != index + 1):
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        self._current(job.project_id, job.id, token=job.active.token)
        return self._evidence(job, publisher, grant)

    async def reconcile(self, project_id, identity):
        job = self._current(project_id, identity, state='NEEDS_RECONCILIATION')
        grant = self.source.source(project_id, identity, accounting=True)
        publisher = self._publisher(job)
        pending = publisher.journal.pending(grant.id, publisher.connection)
        if pending is not None:
            await publisher.reconcile_attempt(pending.id)
        # Incomplete known progress remains fenced; no publish_next here.
        evidence = self._evidence(job, publisher, grant)
        current = self._current(project_id, identity, token=job.active.token, state='NEEDS_RECONCILIATION')
        return self.jobs.record(project_id, identity, current.active.token, evidence)

    async def resume(self, project_id, identity, revision):
        job = self._current(project_id, identity, state='NEEDS_RECONCILIATION')
        if type(revision) is not int or job.revision != revision:
            raise CommerceFailure('RESOURCE_CONFLICT')
        publisher = self._publisher(job)
        grant = self.source.source(project_id, identity)  # Original expiry and source, no renewal.
        if publisher.journal.pending(grant.id, publisher.connection) is not None:
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        history = publisher.journal.history(grant.id, publisher.connection)
        progress = publisher.journal.progress(grant.id, publisher.connection)
        start, total = progress['completed_steps'], progress['total_steps']
        if len(history) != start or not 0 <= start < total:
            raise CommerceFailure('RESOURCE_CONFLICT')
        with self.jobs.db.transaction() as conn:
            current = self.jobs._read(conn, project_id, identity)
            if current != job or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding:
                raise CommerceFailure('REVIEW_STALE')
            claimed = self.jobs._write(conn, current, state='RUNNING')
            self.jobs.repo.event(conn, project_id, 'verification_staging_resumed', {'job_id': job.id, 'next_index': start})
        try:
            evidence = await self._send_remaining(claimed, publisher, grant, start, total)
            return self.jobs.record(project_id, identity, claimed.active.token, evidence)
        except BaseException:
            with self.jobs.db.transaction() as conn:
                current = self.jobs._read(conn, project_id, identity)
                if current.state == 'RUNNING' and current.active == claimed.active:
                    self.jobs._write(conn, current, state='NEEDS_RECONCILIATION')
            raise
