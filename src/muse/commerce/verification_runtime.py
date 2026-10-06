"""Host-only fixed-stage polling. Collection never creates publication authority.

No API registration, arbitrary handlers or automatic unknown-result recovery.
The service owner must establish exclusive ownership before accounting claims
left RUNNING by a previous process with recover_interrupted.
"""
import asyncio
import math

from sqlalchemy import text

from muse.commerce.buyer_verification_stage import BuyerVerificationStage
from muse.commerce.errors import CommerceFailure
from muse.commerce.readback_verification_stage import ReadbackVerificationStage
from muse.commerce.reference_verification_stage import ReferenceVerificationStage
from muse.commerce.source_capture_stage import SourceCaptureStage
from muse.commerce.staging_verification_stage import StagingVerificationStage
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce.verification_worker import VerificationWorker


class VerificationRuntime:
    def __init__(self, jobs, *, reference, source_capture, staging, buyer, browser, facts, timeout=None):
        handlers = {'reference': reference, 'source_capture': source_capture, 'staging': staging,
                    'buyer': buyer, 'browser': browser, 'facts': facts}
        expected = {'reference': ReferenceVerificationStage, 'source_capture': SourceCaptureStage,
                    'staging': StagingVerificationStage, 'buyer': BuyerVerificationStage,
                    'browser': ReadbackVerificationStage, 'facts': ReadbackVerificationStage}
        if (type(jobs) is not VerificationJobRepository
                or any(type(handler) is not expected[name] or handler.jobs is not jobs
                       for name, handler in handlers.items())
                or reference.service is not source_capture.service
                or any(handler.source is not source_capture for handler in (staging, buyer, browser, facts))
                or browser.phase != 'browser' or facts.phase != 'facts'):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.jobs = jobs
        self.worker = VerificationWorker(jobs, handlers, timeout=timeout)

    async def run_once(self, project_id):
        """Advance at most one phase per queued job in a bounded journal page."""
        results = []
        for job in self.jobs.queued(project_id):
            try:
                result = await self.worker.run_step(project_id, job.id)
            except CommerceFailure:
                # Includes claim contention; never reset or repeat the handler.
                result = self.jobs.read(project_id, job.id)
            results.append(result)
        return results

    def recover_interrupted(self, project_id):
        """Account previous process claims only; caller must own the service."""
        recovered, after = [], 0
        while True:
            with self.jobs.db.transaction() as conn:
                self.jobs.repo._project(conn, project_id)
                rows = conn.execute(text("SELECT rowid AS position,id FROM commerce_artifacts "
                    "WHERE project_id=:project AND kind='verification_job' AND rowid>:after "
                    "ORDER BY rowid LIMIT 100"), {'project': project_id, 'after': after}).mappings().all()
                for row in rows:
                    after = row['position']
                    job = self.jobs._read(conn, project_id, row['id'])
                    if job.state == 'RUNNING':
                        recovered.append(self.jobs._write(conn, job, state='NEEDS_RECONCILIATION'))
                if not rows:
                    return recovered

    async def run(self, project_id, stop, *, poll_seconds=1):
        """Private host loop; unknown/collected jobs never enter its send queue."""
        if (not isinstance(stop, asyncio.Event) or type(poll_seconds) not in (int, float)
                or not math.isfinite(poll_seconds) or not 0 < poll_seconds <= 30):
            raise CommerceFailure('INPUT_INVALID', 422)
        while not stop.is_set():
            await self.run_once(project_id)
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
