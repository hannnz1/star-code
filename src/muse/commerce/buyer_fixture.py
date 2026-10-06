"""Read-only contract for the host's owned hidden disposable purchase product.

This is not a merchant product proposal, a passed report or write authority.
Creation/readback in the fixed reference producer and stage binding are required
before the runtime can use it; this parser alone grants no ability to buy.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import Field, ValidationError

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Contract, ProductDraft


class DisposableProductProof(Contract):
    job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    project_id: str
    connection_id: str
    product_id: int = Field(gt=0, strict=True)
    sku: str
    title: Literal['MUSE disposable purchase probe']
    price: Literal['12.50']
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    stock_quantity: int = Field(ge=3, le=3, strict=True)
    status: Literal['publish']
    catalog_visibility: Literal['hidden']
    fixture_only: Literal[True]


@dataclass(frozen=True)
class DisposableBuyerProduct:
    project_id: str
    job_id: str
    connection_id: str
    product_id: int
    draft: ProductDraft
    fixture_only: Literal[True] = True


def read_disposable_product(raw, *, project_id, job_id, currency):
    try:
        proof = DisposableProductProof.model_validate(raw)
        if (proof.job_id != job_id or proof.project_id != project_id or proof.currency != currency
                or proof.connection_id != 'ref-' + job_id or proof.sku != 'MUSE-PROBE-' + job_id
                or raw.get('fixture_only') is not True):
            raise ValueError()
        draft = ProductDraft(sku=proof.sku, title=proof.title, price=Decimal(proof.price),
            currency=proof.currency, stock=proof.stock_quantity)
        return DisposableBuyerProduct(project_id, job_id, proof.connection_id, proof.product_id, draft)
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise CommerceFailure('VERIFICATION_FAILED', 422) from None



class BuyerFixtureRepository:
    @staticmethod
    def key(project_id, plan_id, reference_id):
        from muse.commerce.repository import digest
        return digest([project_id, plan_id, reference_id, 'buyer_fixture_binding'])

    @staticmethod
    def read(conn, jobs, project_id, plan_id, reference_id, intent):
        from muse.commerce.release_approval import (
            ProductReleaseApprovalRepository as Records,
        )
        row, value = Records._read(conn, BuyerFixtureRepository.key(project_id, plan_id, reference_id), 'buyer_fixture_binding')
        if (row['project_id'] != project_id or row['plan_id'] != plan_id
                or set(value) != {'verification_job_id', 'source_binding', 'staging_intent', 'proof'}
                or value['staging_intent'] != intent.digest or intent.project_id != project_id or intent.plan_id != plan_id
                or intent.target.connector_ref != 'ref-' + reference_id or any(p.stock >= 1 for p in intent.products)):
            raise CommerceFailure('REVIEW_STALE')
        job = jobs._read(conn, project_id, value['verification_job_id'])
        if (job.plan_id != plan_id or job.cancel_requested or job.state not in {'RUNNING', 'NEEDS_RECONCILIATION', 'COLLECTED'}
                or job.source_binding != value['source_binding']
                or jobs._source(conn, project_id, plan_id, job.plan_revision) != job.source_binding):
            raise CommerceFailure('REVIEW_STALE')
        return read_disposable_product(value['proof'], project_id=project_id, job_id=reference_id,
            currency=intent.blueprint.required_settings['currency'])
