"""Fixed private verifier dispatcher; production producers are wired separately.

It does not start a daemon, expose an Agent tool, construct reports or provide
fallback successful evidence. An interrupted claim requires explicit readback;
polling run_step can never repeat its handler.
"""
import asyncio
import math

from muse.commerce.errors import CommerceFailure
from muse.commerce.verification_jobs import PHASES, VerificationJobRepository


class VerificationWorker:
    def __init__(self, jobs, handlers, *, timeout=None):
        if not isinstance(jobs, VerificationJobRepository):
            raise TypeError('A private verification journal is required')
        if (not isinstance(handlers, dict) or set(handlers) != set(PHASES)
                or any(not callable(handler) for handler in handlers.values())
                or (timeout is not None and (type(timeout) not in (float, int)
                    or not math.isfinite(timeout) or not 0 < timeout <= 1800))):
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.jobs, self.handlers, self.timeout = jobs, dict(handlers), timeout
        # Staging performs a serial, independently read-back sequence of CMS
        # effects. Bound the whole phase separately from single HTTP requests;
        # cancellation still fences its claim and never renews the source grant.
        self.timeouts = {phase: timeout if timeout is not None else (600 if phase == 'staging' else 180)
                         for phase in PHASES}

    def _unknown(self, claimed):
        current = self.jobs.read(claimed.project_id, claimed.id)
        if current.state == 'RUNNING' and current.active == claimed.active:
            try:
                self.jobs.interrupt(current.project_id, current.id, current.revision)
            except CommerceFailure:
                # A concurrent cancellation/reconciliation owns the newer state.
                # Never revert it or create a new claim.
                return

    async def run_step(self, project_id, identity):
        job = self.jobs.read(project_id, identity)
        if job.state != 'QUEUED':
            raise CommerceFailure('RESOURCE_CONFLICT')
        phase = PHASES[len(job.completed)]
        claimed = self.jobs.claim(project_id, identity, job.revision, phase)
        try:
            evidence = await asyncio.wait_for(self.handlers[phase](claimed), timeout=self.timeouts[phase])
            return self.jobs.record(project_id, identity, claimed.active.token, evidence)
        except asyncio.CancelledError:
            self._unknown(claimed)
            raise
        except Exception:  # noqa: BLE001 - private adapter boundary preserves every uncertain effect
            # Adapter exceptions may contain private paths/remote credentials.
            # Preserve the fence and return only the stable public failure code.
            self._unknown(claimed)
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN') from None
