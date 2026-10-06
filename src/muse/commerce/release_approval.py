"""Private v2 review/approval journal in the existing transactional runtime DB.

Only a trusted verifier may write trusted_product_verification artifacts.
No public endpoint, Agent tool or model output can stage such evidence here.
"""
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import VerificationReport
from muse.commerce.release import (
    ProductReleaseIntent,
    release_source_hash,
    validate_product_release,
)
from muse.commerce.repository import digest, encode
from muse.commerce_connector.release_authorization import ProductReleaseGrant
from muse.commerce_connector.wordpress import WordPressConnection

CHECKS = frozenset({'os_boundary', 'pages', 'layout_desktop', 'layout_mobile', 'links', 'product_facts', 'buyer_flow', 'media'})


@dataclass(frozen=True)
class ApprovedProductRelease:
    intent: ProductReleaseIntent
    grant: ProductReleaseGrant
    verification: VerificationReport


class ProductReleaseApprovalRepository:
    intent_type = ProductReleaseIntent
    grant_type = ProductReleaseGrant
    approved_type = ApprovedProductRelease
    validate_intent = staticmethod(validate_product_release)
    review_kind = 'product_release_review'
    grant_kind = 'product_release_grant'
    verification_kind = 'trusted_product_verification'
    event_prefix = 'product_release'
    check_names = CHECKS

    def _check_source_code(self, intent, code):
        """Specialized releases may require additional exact package binding."""

    def _review_extra(self, conn, intent, plan):
        return {}

    def __init__(self, commerce, *, clock=time.time):
        self.commerce, self.db, self.clock = commerce, commerce.db, clock

    @staticmethod
    def _id(kind, identity):
        return digest([kind, identity])

    @staticmethod
    def _read(conn, identity, kind):
        row = conn.execute(text('SELECT * FROM commerce_artifacts WHERE id=:id AND kind=:kind'),
                           {'id': identity, 'kind': kind}).mappings().first()
        if row is None:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            value = json.loads(row['data'])
            if not isinstance(value, dict) or digest(value) != row['digest']:
                raise ValueError()
            return row, value
        except (ValueError, TypeError):
            raise CommerceFailure('REVIEW_STALE') from None

    @staticmethod
    def _write(conn, row, value):
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                     {'id': row['id'], 'data': encode(value), 'digest': digest(value)})

    @staticmethod
    def _insert(conn, identity, project, plan, kind, value):
        conn.execute(text('INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,:kind,:digest,:data)'),
            {'id': identity, 'project': project, 'plan': plan, 'kind': kind, 'digest': digest(value), 'data': encode(value)})

    def _verify(self, conn, intent, proof_id, project, plan, connection):
        intent = self.validate_intent(intent, connection=connection)
        if (project.revision != intent.project_revision or project.id != intent.project_id
                or plan.id != intent.plan_id or plan.project_id != project.id or release_source_hash(plan) != intent.plan_source_hash
                or intent.target not in project.environment_refs or plan.snapshot_hash != intent.snapshot_hash
                or plan.content_hash != intent.content_hash or plan.code_revision != intent.code_revision
                or not plan.steps or any(step.status != 'SUCCEEDED' or not step.output_hash for step in plan.steps)):
            raise CommerceFailure('REVIEW_STALE')
        code = load_captured_code(self.commerce, plan, connection=conn)
        self._check_source_code(intent, code)
        row, proof = self._read(conn, proof_id, self.verification_kind)
        try:
            report = VerificationReport.model_validate(proof['report'])
            names = [check['name'] for check in report.checks]
            if (row['project_id'] != project.id or row['plan_id'] != plan.id or row['id'] != report.id
                    or set(proof) != {'report', 'target', 'source_digest', 'package_sha256'}
                    or proof['target'] != intent.target.model_dump(mode='json')
                    or proof['source_digest'] != code.source_digest or proof['package_sha256'] != code.package.package_sha256
                    or report.changeset_digest != intent.digest or report.snapshot_hash != intent.snapshot_hash
                    or report.code_revision != intent.code_revision or report.passed is not True
                    or set(names) != self.check_names or len(names) != len(self.check_names) or not report.evidence_refs
                    or any(check.get('passed') is not True for check in report.checks)):
                raise ValueError()
            return report
        except (ValueError, TypeError, KeyError):
            raise CommerceFailure('VERIFICATION_FAILED', 422) from None

    @staticmethod
    def _not_cancelled(conn, plan):
        row = conn.execute(text('SELECT t.cancel_requested,t.status FROM commerce_plans p JOIN tasks t ON p.root_task_id=t.id WHERE p.id=:id'),
                           {'id': plan.id}).mappings().first()
        if row is None or row['cancel_requested'] or row['status'] in {'CANCELLED', 'FAILED'}:
            raise CommerceFailure('APPROVAL_REQUIRED', 403)

    def _current(self, conn, row, value, connection):
        try:
            intent = self.intent_type.model_validate(value['intent'])
            project, plan = ApprovalRepository._source(conn, intent.project_id, intent.plan_id)
            if (row['project_id'] != project.id or row['plan_id'] != plan.id
                    or row['id'] != self._id(self.review_kind, intent.digest)
                    or value['project_hash'] != digest(project) or value['phase'] != plan.state
                    or type(value['plan_revision']) is not int or value['plan_revision'] != plan.revision):
                raise CommerceFailure('REVIEW_STALE')
            self._not_cancelled(conn, plan)
            report = self._verify(conn, intent, value['verification_id'], project, plan, connection)
            if value['verification_hash'] != digest(report):
                raise CommerceFailure('REVIEW_STALE')
            return intent, project, plan, report
        except (ValueError, TypeError, KeyError):
            raise CommerceFailure('REVIEW_STALE') from None

    def stage_review(self, intent, verification_id, *, connection, expected_plan_revision):
        intent = self.validate_intent(intent, connection=connection)
        with self.db.transaction() as conn:
            return self._stage_review(conn, intent, verification_id, connection, expected_plan_revision)

    def _stage_review(self, conn, intent, verification_id, connection, expected_plan_revision):
        """Trusted producer can share its report/plan transaction; no new API."""
        intent = self.validate_intent(intent, connection=connection)
        project, plan = ApprovalRepository._source(conn, intent.project_id, intent.plan_id)
        if type(expected_plan_revision) is not int or plan.revision != expected_plan_revision or plan.state != 'REVIEW_REQUIRED':
            raise CommerceFailure('REVIEW_STALE')
        self._not_cancelled(conn, plan)
        report = self._verify(conn, intent, verification_id, project, plan, connection)
        value = {'intent': intent.model_dump(mode='json'), 'verification_id': verification_id,
            'verification_hash': digest(report), 'project_hash': digest(project), 'plan_revision': plan.revision,
            'phase': plan.state, 'review_revision': plan.revision, 'grant': None, 'status': 'review'}
        value.update(self._review_extra(conn, intent, plan))
        identity = self._id(self.review_kind, intent.digest)
        existing = conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': identity}).first()
        if existing:
            _, previous = self._read(conn, identity, self.review_kind)
            if previous != value:
                raise CommerceFailure('RESOURCE_CONFLICT')
            return intent
        self._insert(conn, identity, project.id, plan.id, self.review_kind, value)
        self.commerce.event(conn, project.id, self.event_prefix + '_reviewed', {'intent_digest': intent.digest})
        return intent

    def _load(self, conn, grant_id, connection):
        alias, frozen = self._read(conn, self._id(self.grant_kind, grant_id), self.grant_kind)
        try:
            row, value = self._read(conn, self._id(self.review_kind, frozen['intent_digest']), self.review_kind)
            grant = self.grant_type(**value['grant'])
            if (grant.id != grant_id or frozen != asdict(grant) or alias['project_id'] != grant.project_id
                    or value['status'] != 'approved' or value['phase'] not in {'APPROVED', 'PUBLISHING'}):
                raise CommerceFailure('APPROVAL_REQUIRED', 403)
            now = self.clock()
            if (any(type(n) not in (int, float) or not math.isfinite(n) for n in (now, grant.approved_at, grant.expires_at))
                    or grant.approved_at > now or not 0 < grant.expires_at - grant.approved_at <= 1800 or now >= grant.expires_at):
                raise CommerceFailure('APPROVAL_EXPIRED', 403)
            intent, project, plan, report = self._current(conn, row, value, connection)
            if (grant.intent_digest != intent.digest or grant.project_id != project.id or grant.status != 'approved'
                    or grant.connection_id != connection.connection_id or grant.environment != connection.environment
                    or grant.target_url != connection.base_url or grant.verification_hash != digest(report)):
                raise CommerceFailure('REVIEW_STALE')
            return self.approved_type(intent, grant, report), row, value, plan
        except (ValueError, TypeError, KeyError):
            raise CommerceFailure('REVIEW_STALE') from None

    def approve(self, intent_digest, *, expected_plan_revision):
        self.expire_due()
        with self.db.transaction() as conn:
            row, value = self._read(conn, self._id(self.review_kind, intent_digest), self.review_kind)
            try:
                target = value['intent']['target']
                connection = WordPressConnection(target['connector_ref'], target['project_id'], target['environment'],
                    target['public_url'], 'scope-only', 'not-a-credential', approved_development_http=True)
                if type(expected_plan_revision) is not int or value['review_revision'] != expected_plan_revision:
                    raise CommerceFailure('REVIEW_STALE')
                if value['grant'] is not None:
                    return self._load(conn, value['grant']['id'], connection)[0].grant
                intent, project, plan, report = self._current(conn, row, value, connection)
                if plan.state != 'REVIEW_REQUIRED' or value['status'] != 'review':
                    raise CommerceFailure('REVIEW_STALE')
                now = self.clock()
                if type(now) not in (int, float) or not math.isfinite(now):
                    raise CommerceFailure('INPUT_INVALID', 422)
                grant = self.grant_type(uuid.uuid4().hex, intent.digest, project.id, connection.connection_id,
                    connection.environment, connection.base_url, digest(report), now, now + 1800, 'approved')
                approved = plan.model_copy(update={'state': 'APPROVED', 'revision': plan.revision + 1})
                self._plan(conn, approved)
                value.update({'grant': asdict(grant), 'status': 'approved', 'phase': approved.state, 'plan_revision': approved.revision})
                self._write(conn, row, value)
                self._insert(conn, self._id(self.grant_kind, grant.id), project.id, plan.id, self.grant_kind, asdict(grant))
                self.commerce.event(conn, project.id, self.event_prefix + '_approved', {'grant_id': grant.id, 'intent_digest': intent.digest})
                return grant
            except (ValueError, TypeError, KeyError):
                raise CommerceFailure('REVIEW_STALE') from None

    @staticmethod
    def _plan(conn, plan):
        conn.execute(text('UPDATE commerce_plans SET data=:data,revision=:revision WHERE id=:id'),
                     {'id': plan.id, 'data': encode(plan), 'revision': plan.revision})

    def load(self, grant_id, connection):
        self.expire_due()
        with self.db.transaction() as conn:
            return self._load(conn, grant_id, connection)[0]

    def start(self, grant_id, connection):
        self.expire_due()
        with self.db.transaction() as conn:
            execution, row, value, plan = self._load(conn, grant_id, connection)
            if plan.state == 'APPROVED':
                plan = plan.model_copy(update={'state': 'PUBLISHING', 'revision': plan.revision + 1})
                self._plan(conn, plan)
                value.update({'phase': plan.state, 'plan_revision': plan.revision})
                self._write(conn, row, value)
            return execution

    def revoke(self, grant_id, *, project_id):
        with self.db.transaction() as conn:
            _, frozen = self._read(conn, self._id(self.grant_kind, grant_id), self.grant_kind)
            if frozen['project_id'] != project_id:
                raise CommerceFailure('NOT_FOUND', 404)
            row, value = self._read(conn, self._id(self.review_kind, frozen['intent_digest']), self.review_kind)
            if value['grant'] != frozen:
                raise CommerceFailure('REVIEW_STALE')
            if value['status'] == 'revoked':
                return
            self._revoke(conn, row, value, self.event_prefix + '_revoked')

    def _revoke(self, conn, row, value, event):
        if value['status'] != 'approved':
            return
        intent = self.intent_type.model_validate(value['intent'])
        project, plan = ApprovalRepository._source(conn, intent.project_id, intent.plan_id)
        # Never roll an externally changed/newer plan back to an old review.
        if (plan.revision == value['plan_revision'] and plan.state == value['phase']
                and release_source_hash(plan) == intent.plan_source_hash and digest(project) == value['project_hash']):
            state = 'NEEDS_RECONCILIATION' if plan.state == 'PUBLISHING' else 'REVIEW_REQUIRED'
            plan = plan.model_copy(update={'state': state, 'revision': plan.revision + 1,
                                           'error_code': 'WRITE_OUTCOME_UNKNOWN' if state == 'NEEDS_RECONCILIATION' else None})
            self._plan(conn, plan)
            value.update({'phase': state, 'plan_revision': plan.revision})
        value['status'] = 'revoked'
        self._write(conn, row, value)
        self.commerce.event(conn, project.id, event, {'grant_id': value['grant']['id']})

    def expire_due(self):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise CommerceFailure('INPUT_INVALID', 422)
        with self.db.transaction() as conn:
            ids = conn.execute(text("SELECT id FROM commerce_artifacts WHERE kind=:kind"),
                               {"kind": self.review_kind}).scalars().all()
            for identity in ids:
                row, value = self._read(conn, identity, self.review_kind)
                if value.get('status') != 'approved':
                    continue
                try:
                    expiry = value['grant']['expires_at']
                    if type(expiry) not in (int, float) or not math.isfinite(expiry):
                        raise ValueError()
                    if expiry <= now:
                        self._revoke(conn, row, value, self.event_prefix + '_expired')
                except (ValueError, TypeError, KeyError):
                    raise CommerceFailure('REVIEW_STALE') from None
