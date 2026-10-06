"""Durable preview effects cannot consume or approve a merchant business plan."""
from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_journal import MerchantReleaseJournal
from muse.commerce.staging_source import StagingSourceRepository


class StagingReleaseJournal(MerchantReleaseJournal):
    attempt_kind = 'staging_release_attempt'

    def __init__(self, approvals, ledger):
        if not isinstance(approvals, StagingSourceRepository):
            raise CommerceFailure('PERMISSION_DENIED', 403)
        super().__init__(approvals, ledger)

    def _transition(self, conn, parent, value, intent, state, error, status):
        # A known late result is recorded even after source cancellation or
        # revocation. Only the source loader can authorize another fresh send.
        value['phase'] = 'STAGING' if state == 'PUBLISHING' else ('STAGED' if state == 'SUCCEEDED' else state)
        value['status'] = status if value['status'] == 'approved' else value['status']
        self.approvals._write(conn, parent, value)
