"""Private preview permits are never verification or merchant live approval."""
from dataclasses import dataclass

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.merchant_authorization import MerchantReleaseAuthority
from muse.commerce_connector.site_authorization import SiteReleaseGrant


@dataclass(frozen=True)
class StagingReleaseGrant(SiteReleaseGrant):
    pass


class StagingReleaseAuthority(MerchantReleaseAuthority):
    grant_type = StagingReleaseGrant
    version = 5
    audience = 'muse-wp-staging-preview-v5'

    def _extra_claims(self, intent):
        return {**super()._extra_claims(intent), 'purpose': 'staging-preview'}

    def _claims(self, grant, intent, connection, code, index, history, snapshot, proofs):
        if connection.environment != 'staging' or intent.target.environment != 'staging' or grant.environment != 'staging':
            raise CommerceFailure('PERMISSION_DENIED', 403)
        return super()._claims(grant, intent, connection, code, index, history, snapshot, proofs)
