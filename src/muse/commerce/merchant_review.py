"""Merchant-safe views and explicit one-step commands over private v4 reviews.

No client can submit evidence, intent bytes, resource IDs, or a signing token.
The publication adapter is injected by trusted deployment code; the main app
does not instantiate a WordPress credential holder or enable writes by default.
"""
from typing import Literal

from pydantic import Field
from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Contract, EnvironmentRef, ProductDraft
from muse.commerce_connector.media import ImageDescriptor
from muse.commerce_connector.wordpress import WordPressConnection


class MerchantReviewImage(ImageDescriptor):
    media_ref: str


class MerchantReviewStep(Contract):
    index: int = Field(ge=0, le=154)
    key: str
    kind: str
    resource_ref: str
    depends_on: list[str]


class MerchantAttemptView(Contract):
    index: int
    operation_id: str
    state: str
    effect_verified: bool


class MerchantReleaseReview(Contract):
    project_id: str
    plan_id: str
    plan_revision: int
    intent_digest: str
    workflow: Literal['build_site', 'launch_products']
    target: EnvironmentRef
    source_digest: str
    code_revision: str
    package_sha256: str
    source_snapshot_hash: str
    target_snapshot_hash: str
    products: list[ProductDraft]
    images: list[MerchantReviewImage]
    steps: list[MerchantReviewStep]
    checks: list[str]
    status: str
    phase: str
    approvable: bool
    approved_at: float | None = None
    expires_at: float | None = None
    completed_steps: int = Field(ge=0, le=155)
    total_steps: int = Field(ge=1, le=155)
    last_attempt: MerchantAttemptView | None = None


class MerchantReviewRepository:
    def __init__(self, approvals):
        self.approvals = approvals
        self.commerce = approvals.commerce

    @staticmethod
    def _scope(intent):
        target = intent.target
        return WordPressConnection(target.connector_ref, target.project_id, target.environment,
            target.public_url, 'scope-only', 'not-a-credential', approved_development_http=True)

    def _frozen(self, conn, project_id, plan_id, intent_digest):
        _, plan = ApprovalRepository._source(conn, project_id, plan_id)
        row, value = self.approvals._read(conn, self.approvals._id(self.approvals.review_kind, intent_digest),
            self.approvals.review_kind)
        if row['project_id'] != project_id or row['plan_id'] != plan_id:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            intent = self.approvals.intent_type.model_validate(value['intent'])
            connection = self._scope(intent)
            self.approvals.validate_intent(intent, connection=connection)
            if intent.digest != intent_digest or intent.project_id != project_id or intent.plan_id != plan_id:
                raise ValueError()
            self.approvals.frozen_code(intent, connection=conn)
            return plan, value, intent, connection, row
        except (ValueError, KeyError, TypeError):
            raise CommerceFailure('REVIEW_STALE') from None

    def read(self, project_id, plan_id, intent_digest, expected_revision, *, journal=None):
        self.approvals.expire_due()
        with self.approvals.db.transaction() as conn:
            plan, value, intent, connection, row = self._frozen(conn, project_id, plan_id, intent_digest)
            if type(expected_revision) is not int or expected_revision != plan.revision:
                raise CommerceFailure('REVIEW_STALE')
            if value['status'] in {'review', 'approved'}:
                self.approvals._current(conn, row, value, connection)
            count = value.get('history_count', 0)
            if type(count) is not int or not 0 <= count <= len(intent.steps):
                raise CommerceFailure('REVIEW_STALE')
            grant = value.get('grant')
            view = MerchantReleaseReview(project_id=project_id, plan_id=plan_id, plan_revision=plan.revision,
                intent_digest=intent.digest, workflow=intent.workflow, target=intent.target,
                source_digest=intent.source_digest, code_revision=intent.code_revision,
                package_sha256=intent.package.package_sha256, source_snapshot_hash=intent.snapshot_hash,
                target_snapshot_hash=intent.target_snapshot_hash, products=intent.products,
                images=[MerchantReviewImage(media_ref=image.media_ref, **image.image.model_dump()) for image in intent.images],
                steps=[MerchantReviewStep(index=index, **step.model_dump(exclude={'payload'}))
                    for index, step in enumerate(intent.steps)], checks=sorted(self.approvals.check_names),
                status=value['status'], phase=plan.state, approvable=value['status'] == 'review' and plan.state == 'REVIEW_REQUIRED',
                approved_at=grant['approved_at'] if grant else None, expires_at=grant['expires_at'] if grant else None,
                completed_steps=count, total_steps=len(intent.steps))
        if journal is not None and grant:
            progress = journal.progress(grant['id'], connection)
            attempt = progress['last_attempt']
            if attempt:
                view.last_attempt = MerchantAttemptView(index=attempt.index, operation_id=attempt.operation.operation_id,
                    state=attempt.state, effect_verified=attempt.effect_verified)
        return view

    def latest(self, project_id, plan_id, expected_revision):
        self.commerce.get_plan(plan_id, project_id=project_id)
        with self.approvals.db.transaction() as conn:
            row = conn.execute(text('SELECT id FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan '
                'AND kind=:kind ORDER BY rowid DESC LIMIT 1'),
                {'project': project_id, 'plan': plan_id, 'kind': self.approvals.review_kind}).first()
            if row is None:
                raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
            _, value = self.approvals._read(conn, row[0], self.approvals.review_kind)
            identity = value['intent']['digest']
        return self.read(project_id, plan_id, identity, expected_revision)

    def approve(self, project_id, plan_id, intent_digest, expected_revision):
        # Scope is checked before the approval method's idempotent old-revision
        # path. The caller cannot approve another project's known digest.
        with self.approvals.db.transaction() as conn:
            self._frozen(conn, project_id, plan_id, intent_digest)
        self.approvals.approve(intent_digest, expected_plan_revision=expected_revision)
        plan = self.commerce.get_plan(plan_id, project_id=project_id)
        return self.read(project_id, plan_id, intent_digest, plan.revision)


class MerchantPublicationService:
    """Trusted connector-side adapter; no public arbitrary-operation dispatch."""
    def __init__(self, approvals, publisher_for_connection):
        self.reviews = MerchantReviewRepository(approvals)
        self.approvals = approvals
        self.publisher_for_connection = publisher_for_connection

    def _publisher(self, scope):
        publisher = self.publisher_for_connection(scope.connection_id)
        if (publisher.approvals is not self.approvals or publisher.connection.connection_id != scope.connection_id
                or publisher.connection.project_id != scope.project_id or publisher.connection.environment != scope.environment
                or publisher.connection.base_url != scope.base_url):
            raise CommerceFailure('PERMISSION_DENIED', 403)
        return publisher

    def review(self, project_id, plan_id, intent_digest, expected_revision):
        view = self.reviews.read(project_id, plan_id, intent_digest, expected_revision)
        if view.approved_at is None:
            return view
        with self.approvals.db.transaction() as conn:
            _, _, _, scope, _ = self.reviews._frozen(conn, project_id, plan_id, intent_digest)
        publisher = self._publisher(scope)
        return self.reviews.read(project_id, plan_id, intent_digest, expected_revision, journal=publisher.journal)

    async def execute(self, project_id, plan_id, intent_digest, expected_revision, *, reconcile_only):
        self.reviews.read(project_id, plan_id, intent_digest, expected_revision)
        with self.approvals.db.transaction() as conn:
            _, value, intent, scope, _ = self.reviews._frozen(conn, project_id, plan_id, intent_digest)
            if not value.get('grant'):
                raise CommerceFailure('APPROVAL_REQUIRED', 403)
            grant_id = value['grant']['id']
        publisher = self._publisher(scope)
        if reconcile_only:
            # Explicit recovery cannot fall through to publish_next(), which
            # would prepare a new write when there is no pending attempt.
            pending = publisher.journal.pending(grant_id, publisher.connection)
            if pending is not None:
                await publisher.reconcile_attempt(pending.id)
        else:
            await publisher.publish_next(grant_id)
        plan = self.approvals.commerce.get_plan(plan_id, project_id=project_id)
        return self.reviews.read(project_id, plan_id, intent.digest, plan.revision, journal=publisher.journal)
