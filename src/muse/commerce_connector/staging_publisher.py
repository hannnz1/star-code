"""Default-disabled preview broker with v5 staging-only permits and journals."""
from muse.commerce.errors import CommerceFailure
from muse.commerce.staging_journal import StagingReleaseJournal
from muse.commerce_connector.merchant_publisher import MerchantReleasePublisher
from muse.commerce_connector.staging_authorization import StagingReleaseAuthority


class StagingReleasePublisher(MerchantReleasePublisher):
    def __init__(self, connection, journal, authority, **kwargs):
        if (connection.environment != 'staging' or not isinstance(journal, StagingReleaseJournal)
                or not isinstance(authority, StagingReleaseAuthority)):
            raise CommerceFailure('PERMISSION_DENIED', 403)
        super().__init__(connection, journal, authority, **kwargs)
