"""Merchant checklist separates stored configuration from independent verification."""
from decimal import Decimal
from pydantic import Field
from muse.commerce.models import Contract
from muse.commerce.design_repository import DesignRepository


class ReadinessItem(Contract):
    key:str
    configuration_status:str
    verification_status:str
    evidence_ref:str | None = None
    action:str
    configuration_url:str | None = None
    confirmation_url:str | None = None


class StoreReadinessReport(Contract):
    project_id:str
    project_revision:int
    items:list[ReadinessItem]
    can_publish:bool=False


class ShippingQuote(Contract):
    country:str=Field(pattern=r'^[A-Z]{2}$')
    rate:Decimal=Field(ge=0,allow_inf_nan=False)
    free_from:Decimal | None=Field(default=None,ge=0,allow_inf_nan=False)
    subtotal:Decimal=Field(ge=0,allow_inf_nan=False)


def quote_shipping(value:ShippingQuote)->Decimal:
    return Decimal('0.00') if value.free_from is not None and value.subtotal>=value.free_from else value.rate.quantize(Decimal('0.01'))


class StoreReadinessService:
    def __init__(self,repo):self.repo=repo

    def evaluate(self,project_id):
        project=self.repo.get_project(project_id)
        with self.repo.db.transaction() as conn:
            context=self.repo._context(conn,project,'staging')
            design=DesignRepository.read(conn,project_id)
        settings=context.snapshot.settings if context else {}
        items=[]
        def add(key,configured,action,evidence=None):
            items.append(ReadinessItem(key=key,configuration_status='CONFIGURED' if configured else 'MISSING',
                verification_status='NOT_VERIFIED',evidence_ref=evidence,action=action))
        add('policy',all(project.brief.merchant_supplied_policies.get(k,'').strip() for k in ('shipping','returns','privacy')),'settings')
        add('shipping',settings.get('shipping_confirmed') is True,'connection',context.snapshot_id if context else None)
        add('payment',settings.get('payment_confirmed') is True,'connection',context.snapshot_id if context else None)
        add('domain',any(r.environment=='live' for r in project.environment_refs),'connection')
        add('design',design is not None and design.project_revision==project.revision,'website')
        add('products',any(batch.project_revision==project.revision and batch.result.drafts for batch in self.repo.list_product_imports(project_id)),'products')
        add('verification',False,'team')
        add('tax',bool(settings.get('tax_settings')),'connection')
        # Reuse actual platform configuration screens rather than inventing a local confirmation.
        reference=next((r for r in project.environment_refs if r.environment=='staging'),None)
        if reference:
            from urllib.parse import urlsplit
            parsed=urlsplit(reference.public_url)
            if parsed.scheme in {'http','https'} and parsed.hostname and not parsed.username and not parsed.password:
                base=reference.public_url.rstrip('/')
                paths={'shipping':'/wp-admin/admin.php?page=wc-settings&tab=shipping','payment':'/wp-admin/admin.php?page=wc-settings&tab=checkout','tax':'/wp-admin/admin.php?page=wc-settings&tab=tax','domain':'/wp-admin/options-general.php'}
                for item in items:
                    if item.key in paths: item.configuration_url=base+paths[item.key]
                    if item.key in {'shipping', 'payment'}:
                        item.confirmation_url=base+'/wp-admin/options-general.php?page=muse-connector'
        # Only a still-current private release review can identify verified source.
        from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
        from muse.commerce.merchant_review import MerchantReviewRepository
        from muse.commerce.errors import CommerceFailure
        reviews=MerchantReviewRepository(MerchantReleaseApprovalRepository(self.repo))
        for plan in reversed(self.repo.list_plans(project_id)):
            if plan.state!='REVIEW_REQUIRED': continue
            try: review=reviews.latest(project_id,plan.id,plan.revision)
            except CommerceFailure: continue
            if not review.approvable or 'buyer_flow' not in review.checks: continue
            for item in items:
                if item.key in {'shipping','payment','verification','design','products'}:
                    item.verification_status='VERIFIED_STAGING'
                    item.evidence_ref=review.intent_digest
                    if item.key=='verification':item.configuration_status='CONFIGURED'
            break
        # Approval/verification permission comes exclusively from the release review API.
        return StoreReadinessReport(project_id=project_id,project_revision=project.revision,items=items)
