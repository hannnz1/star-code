"""Private synthetic buyer send fence. No public report or checkout tool.

A successful response alone is not a verified buyer flow. Actual independent
order readback and source/safety probes remain the trusted verifier's job.
"""
from decimal import Decimal
from typing import Literal

from pydantic import Field, ValidationError
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Contract, ProductDraft
from muse.commerce.repository import digest, encode


class BuyerSource(Contract):
    job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    staging_intent_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    product_id: int = Field(gt=0, strict=True)
    sku: str = Field(min_length=1, max_length=100)
    connection_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')


class BuyerReceipt(Contract):
    order_id: int = Field(gt=0, strict=True)
    status: Literal['on-hold']


class BuyerProbe(Contract):
    id: str
    project_id: str
    plan_id: str
    source: BuyerSource
    state: Literal['UNKNOWN', 'SUCCEEDED']
    receipt: BuyerReceipt | None = None
    buyer_flow_verified: Literal[False] = False


class BuyerOrderProof(Contract):
    state: Literal['found']
    probe_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    staging_intent_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    product_id: int = Field(gt=0, strict=True)
    sku: str = Field(min_length=1, max_length=100)
    order_id: int = Field(gt=0, strict=True)
    status: Literal['on-hold']
    payment_method: Literal['cod']
    quantity: int = Field(ge=1, le=1, strict=True)
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    item_subtotal: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    shipping_total: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    tax_total: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    order_total: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


class BuyerPriceFact(Contract):
    probe_id: str
    source: BuyerSource
    price: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str = Field(pattern=r'^[A-Z]{3}$')


class BuyerDeliveryFact(Contract):
    probe_id: str
    source: BuyerSource
    amount: Decimal = Field(ge=0, allow_inf_nan=False)


class BuyerReadback(Contract):
    probe_id: str
    project_id: str
    plan_id: str
    source: BuyerSource
    receipt: BuyerReceipt
    proof_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    order_facts: BuyerOrderProof


class BuyerProbeRepository:
    def __init__(self, repo):
        self.repo, self.db = repo, repo.db

    @staticmethod
    def _read(conn, project_id, plan_id, identity):
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='buyer_probe'"),
            {'id': identity, 'project': project_id, 'plan': plan_id}).mappings().first()
        if row is None:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            probe = BuyerProbe.model_validate_json(row['data'])
            if (digest(probe) != row['digest'] or probe.id != identity or probe.project_id != project_id
                    or probe.plan_id != plan_id or identity != digest([project_id, plan_id, 'buyer_probe', probe.source.job_id])):
                raise ValueError()
            return probe
        except (ValueError, TypeError):
            raise CommerceFailure('RESOURCE_CONFLICT') from None

    def read(self, project_id, plan_id, identity):
        with self.db.engine.connect() as conn:
            return self._read(conn, project_id, plan_id, identity)

    def begin(self, project_id, plan_id, source, *, authorize=None, expected_product=None, expected_shipping=None):
        try:
            source = BuyerSource.model_validate(source)
            if expected_product is not None:
                expected_product = ProductDraft.model_validate(expected_product)
                if expected_product.sku != source.sku:
                    raise CommerceFailure('REVIEW_STALE')
            if expected_shipping is not None:
                expected_shipping = BuyerDeliveryFact(probe_id='pending', source=source, amount=expected_shipping).amount
                if expected_product is None:
                    raise CommerceFailure('INPUT_INVALID', 422)
        except ValidationError:
            raise CommerceFailure('INPUT_INVALID', 422) from None
        identity = digest([project_id, plan_id, 'buyer_probe', source.job_id])
        with self.db.transaction() as conn:
            self.repo._project(conn, project_id)
            if not conn.execute(text('SELECT id FROM commerce_plans WHERE id=:id AND project_id=:project'),
                {'id': plan_id, 'project': project_id}).first():
                raise CommerceFailure('NOT_FOUND', 404)
            if conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': identity}).first():
                # Even a known failed checkout can have side effects. This is
                # deliberately not idempotent permission for another send.
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            if authorize is not None and BuyerSource.model_validate(authorize(conn)) != source:
                raise CommerceFailure('REVIEW_STALE')
            probe = BuyerProbe(id=identity, project_id=project_id, plan_id=plan_id, source=source, state='UNKNOWN')
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'buyer_probe',:digest,:data)"),
                {'id': identity, 'project': project_id, 'plan': plan_id, 'digest': digest(probe), 'data': encode(probe)})
            if expected_product is not None:
                facts = BuyerPriceFact(probe_id=identity, source=source, price=expected_product.price, currency=expected_product.currency)
                conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'buyer_price_fact',:digest,:data)"),
                    {'id': digest([identity, 'buyer_price_fact']), 'project': project_id, 'plan': plan_id,
                     'digest': digest(facts), 'data': encode(facts)})
            if expected_shipping is not None:
                delivery = BuyerDeliveryFact(probe_id=identity,source=source,amount=expected_shipping)
                conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'buyer_delivery_fact',:digest,:data)"),
                    {'id':digest([identity,'buyer_delivery_fact']),'project':project_id,'plan':plan_id,
                     'digest':digest(delivery),'data':encode(delivery)})
            return probe

    @staticmethod
    def _save_receipt(conn, probe, receipt):
        if probe.state == 'SUCCEEDED':
            if probe.receipt != receipt:
                raise CommerceFailure('RESOURCE_CONFLICT')
            return probe
        saved = probe.model_copy(update={'state': 'SUCCEEDED', 'receipt': receipt})
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
            {'id': probe.id, 'digest': digest(saved), 'data': encode(saved)})
        return saved

    def confirm_readback(self, identity, response, *, require_amounts=False):
        """Private trusted reader only; accounts late results without resend."""
        try:
            proof = BuyerOrderProof.model_validate(response)
        except ValidationError:
            raise CommerceFailure('VERIFICATION_FAILED', 422) from None
        with self.db.transaction() as conn:
            row = conn.execute(text("SELECT project_id,plan_id FROM commerce_artifacts WHERE id=:id AND kind='buyer_probe'"),
                {'id': identity}).mappings().first()
            if not row:
                raise CommerceFailure('NOT_FOUND', 404)
            probe = self._read(conn, row['project_id'], row['plan_id'], identity)
            if (proof.probe_id != identity or any(getattr(proof, key) != getattr(probe.source, key)
                    for key in ('job_id', 'source_digest', 'staging_intent_digest', 'product_id', 'sku'))):
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            receipt = BuyerReceipt(order_id=proof.order_id, status=proof.status)
            price_row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='buyer_price_fact'"),
                {'id': digest([identity, 'buyer_price_fact']), 'project': probe.project_id, 'plan': probe.plan_id}).mappings().first()
            if require_amounts and price_row is None:
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            if price_row:
                try:
                    facts = BuyerPriceFact.model_validate_json(price_row['data'])
                    shipping = Decimal(5)
                    delivery_row=conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='buyer_delivery_fact'"),
                        {'id':digest([identity,'buyer_delivery_fact']),'project':probe.project_id,'plan':probe.plan_id}).mappings().first()
                    if delivery_row:
                        delivery=BuyerDeliveryFact.model_validate_json(delivery_row['data'])
                        if digest(delivery)!=delivery_row['digest'] or delivery.probe_id!=identity or delivery.source!=probe.source:
                            raise ValueError()
                        shipping=delivery.amount
                    if (digest(facts) != price_row['digest'] or facts.probe_id != identity or facts.source != probe.source
                            or proof.currency != facts.currency or proof.item_subtotal != facts.price
                            or proof.shipping_total != shipping or proof.tax_total != Decimal(0)
                            or proof.order_total != facts.price + shipping):
                        raise ValueError()
                except (ValueError, TypeError):
                    raise CommerceFailure('VERIFICATION_FAILED', 422) from None
            saved = BuyerReadback(probe_id=identity, project_id=probe.project_id, plan_id=probe.plan_id,
                source=probe.source, receipt=receipt, proof_sha256=digest(proof), order_facts=proof)
            readback_id = digest([identity, 'buyer_order_readback'])
            prior = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='buyer_order_readback'"),
                {'id': readback_id}).mappings().first()
            if prior:
                if prior['digest'] != digest(saved) or prior['data'] != encode(saved):
                    raise CommerceFailure('RESOURCE_CONFLICT')
            else:
                conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'buyer_order_readback',:digest,:data)"),
                    {'id': readback_id, 'project': probe.project_id, 'plan': probe.plan_id, 'digest': digest(saved), 'data': encode(saved)})
            self._save_receipt(conn, probe, receipt)
            return saved

    def complete(self, identity, response):
        try:
            receipt = BuyerReceipt.model_validate(response)
        except ValidationError:
            raise CommerceFailure('VERIFICATION_FAILED', 422) from None
        with self.db.transaction() as conn:
            row = conn.execute(text("SELECT project_id,plan_id FROM commerce_artifacts WHERE id=:id AND kind='buyer_probe'"),
                {'id': identity}).mappings().first()
            if not row:
                raise CommerceFailure('NOT_FOUND', 404)
            probe = self._read(conn, row['project_id'], row['plan_id'], identity)
            return self._save_receipt(conn, probe, receipt)
