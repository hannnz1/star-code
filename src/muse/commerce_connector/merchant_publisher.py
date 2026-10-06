"""Default-disabled v4 broker; no public write or model-facing approval route."""
from muse.commerce_connector.site_publisher import SiteReleasePublisher


class MerchantReleasePublisher(SiteReleasePublisher):
    required_operations = SiteReleasePublisher.required_operations | {'create_owned_media'}
    # Explicitly bounded at 100 images + 20 products + six pages. The remaining
    # approval lifetime still fences sending after this read-only preflight.
    maximum_read_seconds = 600
