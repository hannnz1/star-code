"""Private persistent v3 approval. A real trusted verifier must produce evidence.

There is no public report upload or endpoint granting approval in this module.
The product journal's atomic expiry/revocation/source rules remain shared.
"""
import base64
from dataclasses import dataclass

from muse.commerce.code_bridge import load_captured_code
from muse.commerce.coding import CodingArtifact, verify_coding_artifact
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import VerificationReport
from muse.commerce.release_approval import CHECKS, ProductReleaseApprovalRepository
from muse.commerce.site_release import SiteReleaseIntent, validate_site_release
from muse.commerce_connector.site_authorization import SiteReleaseGrant


@dataclass(frozen=True)
class ApprovedSiteRelease:
    intent: SiteReleaseIntent
    grant: SiteReleaseGrant
    verification: VerificationReport


class SiteReleaseApprovalRepository(ProductReleaseApprovalRepository):
    intent_type = SiteReleaseIntent
    grant_type = SiteReleaseGrant
    approved_type = ApprovedSiteRelease
    validate_intent = staticmethod(validate_site_release)
    review_kind = 'site_release_review'
    grant_kind = 'site_release_grant'
    verification_kind = 'trusted_site_verification'
    event_prefix = 'site_release'
    check_names = CHECKS | {'layout_tablet'}

    def _check_source_code(self, intent, code):
        if intent.package != code.package or intent.source_digest != code.source_digest:
            raise CommerceFailure('REVIEW_STALE')

    def _review_extra(self, conn, intent, plan):
        code = load_captured_code(self.commerce, plan, connection=conn)
        self._check_source_code(intent, code)
        return {'source_archive': base64.b64encode(code.archive).decode('ascii')}

    def frozen_code(self, intent, *, connection=None):
        from contextlib import nullcontext
        with nullcontext(connection) if connection is not None else self.db.transaction() as conn:
            _, value = self._read(conn, self._id(self.review_kind, intent.digest), self.review_kind)
            try:
                code = CodingArtifact(intent.project_id, intent.plan_id, intent.snapshot_hash, intent.source_digest,
                                      intent.package, base64.b64decode(value['source_archive'], validate=True))
                verify_coding_artifact(code)
                self._check_source_code(intent, code)
                return code
            except (ValueError, TypeError, KeyError):
                raise CommerceFailure('REVIEW_STALE') from None
