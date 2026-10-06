"""v4 source/image effects with the shared durable unknown-send accounting."""
from muse.commerce.merchant_steps import (
    project_merchant_step,
    validate_merchant_completion,
)
from muse.commerce.site_journal import SiteReleaseJournal


class MerchantReleaseJournal(SiteReleaseJournal):
    attempt_kind = 'merchant_release_attempt'
    maximum_steps = 155

    def _project(self, conn, intent, connection, index, history, snapshot, proofs):
        return project_merchant_step(intent, connection, self.approvals.frozen_code(intent, connection=conn),
            index, history, snapshot, proofs)

    def _completion(self, conn, intent, connection, history, snapshot, proofs):
        return validate_merchant_completion(intent, connection, self.approvals.frozen_code(intent, connection=conn),
            history, snapshot, proofs)
