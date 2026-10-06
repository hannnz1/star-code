"""Private v4 review reuses current source, cancellation and expiry fences."""
import base64
from dataclasses import dataclass

from muse.commerce.errors import CommerceFailure
from muse.commerce.media import MediaRepository
from muse.commerce.merchant_release import (
    MerchantReleaseIntent,
    validate_merchant_release,
)
from muse.commerce.models import VerificationReport
from muse.commerce.site_approval import SiteReleaseApprovalRepository
from muse.commerce_connector.merchant_authorization import MerchantReleaseGrant


@dataclass(frozen=True)
class ApprovedMerchantRelease:
    intent: MerchantReleaseIntent
    grant: MerchantReleaseGrant
    verification: VerificationReport


class MerchantReleaseApprovalRepository(SiteReleaseApprovalRepository):
    intent_type = MerchantReleaseIntent
    grant_type = MerchantReleaseGrant
    approved_type = ApprovedMerchantRelease
    validate_intent = staticmethod(validate_merchant_release)
    review_kind = 'merchant_release_review'
    grant_kind = 'merchant_release_grant'
    verification_kind = 'trusted_merchant_verification'
    event_prefix = 'merchant_release'

    def _verify(self, conn, intent, proof_id, project, plan, connection):
        report = super()._verify(conn, intent, proof_id, project, plan, connection)
        if report.id.startswith('verification-'):
            from muse.commerce.trusted_verifier import validate_provenance
            validate_provenance(conn, report, intent, clock=self.clock)
        for image in intent.images:
            record, content = MediaRepository._read(conn, intent.project_id, image.media_ref)
            if (base64.b64encode(content).decode('ascii') != image.content_base64
                    or record.width != image.image.width or record.height != image.image.height
                    or record.image.sha256 != image.image.sha256 or record.image.mime_type != image.image.mime_type
                    or record.image.byte_size != image.image.byte_size):
                raise CommerceFailure('REVIEW_STALE')
        return report
