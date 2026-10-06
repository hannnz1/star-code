"""Separate merchant audiences; a constructed grant is never approval."""
from dataclasses import dataclass

from muse.commerce.merchant_steps import project_merchant_step
from muse.commerce_connector.site_authorization import (
    SiteReleaseAuthority,
    SiteReleaseGrant,
)


@dataclass(frozen=True)
class MerchantReleaseGrant(SiteReleaseGrant):
    pass


class MerchantReleaseAuthority(SiteReleaseAuthority):
    grant_type = MerchantReleaseGrant
    version = 4
    audience = 'muse-wp-merchant-step-v4'
    maximum_token = 65536
    project_step = staticmethod(project_merchant_step)

    def _extra_claims(self, intent):
        from muse.commerce.merchant_release import preview_category_products
        return {'workflow': intent.workflow, 'image_count': len(intent.images),
            'product_count': len(intent.products)+len(preview_category_products(intent.workflow,intent.blueprint,intent.products))}

    def _claims(self, grant, intent, connection, code, index, history, snapshot, proofs):
        claims, step = super()._claims(grant, intent, connection, code, index, history, snapshot, proofs)
        from muse.commerce.merchant_release import store_configuration_enabled
        if intent.workflow == 'build_site' and store_configuration_enabled(intent.blueprint):
            from muse.commerce.store_configuration import category_targets
            claims.update(v=8 if self.version == 5 else 7,
                audience='muse-wp-store-preview-v8' if self.version == 5 else 'muse-wp-store-step-v7',
                shipping_enabled='shipping_rules' in intent.blueprint.required_settings,
                category_count=len(category_targets(intent.blueprint,intent.products)))
        # The independently reconstructed preview still installs a theme and
        # retains v5 semantics. Only a frozen merchant launch may omit it.
        elif (self.version == 4 and intent.workflow == 'launch_products'
                and intent.blueprint.required_settings.get('retain_existing_theme') is True):
            claims.update(v=6, audience='muse-wp-retained-merchant-step-v6')
        return claims, step
