"""Website attempts with the shared durable UNKNOWN fence and late accounting.

Frozen source supports accounting after cancellation, but never grants another
send. Every prepare still loads current merchant approval and verifier evidence.
"""
from dataclasses import dataclass

from muse.commerce.models import ChangeOperation
from muse.commerce.release_journal import ProductReleaseJournal
from muse.commerce.site_steps import (
    CompletedSiteStep,
    project_site_step,
    validate_site_completion,
)


@dataclass(frozen=True)
class SiteReleaseAttempt:
    id: str
    grant_id: str
    index: int
    operation: ChangeOperation
    state: str
    effect_verified: bool


class SiteReleaseJournal(ProductReleaseJournal):
    attempt_kind = 'site_release_attempt'
    attempt_type = SiteReleaseAttempt
    completed_type = CompletedSiteStep
    maximum_steps = 55

    def _project(self, conn, intent, connection, index, history, snapshot, proofs):
        code = self.approvals.frozen_code(intent, connection=conn)
        return project_site_step(intent, connection, code, index, history, snapshot, proofs)

    def _completion(self, conn, intent, connection, history, snapshot, proofs):
        code = self.approvals.frozen_code(intent, connection=conn)
        return validate_site_completion(intent, connection, code, history, snapshot, proofs)

    def frozen_code(self, grant_id, connection):
        with self.db.transaction() as conn:
            intent = self._parent(conn, grant_id, connection)[2]
            return self.approvals.frozen_code(intent, connection=conn)
