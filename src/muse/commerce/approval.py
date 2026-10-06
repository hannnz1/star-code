"""Internal review/approval persistence. No public approve or write endpoint.

stage_review is reserved for the trusted verifier integration. Shape/hash checks
are not proof a browser/OS/purchase check actually ran. P6 integration is required.
"""
import asyncio
import math
import re
import uuid

from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    ApprovalGrant,
    ChangeSet,
    CommercePlan,
    StoreProject,
    VerificationReport,
)
from muse.commerce.repository import digest, encode
from muse.commerce_connector.operations import validate_operation
from muse.commerce_connector.publisher import ApprovedExecution


class ApprovalRepository:
    def __init__(self, commerce, *, clock):
        self.commerce, self.db, self.clock = commerce, commerce.db, clock

    @staticmethod
    def _row(conn, changeset_id):
        row = conn.execute(text('SELECT * FROM commerce_changesets WHERE id=:id'), {'id': changeset_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404)
        return row

    @staticmethod
    def _source(conn, project_id, plan_id):
        project = conn.execute(text('SELECT data FROM commerce_projects WHERE id=:id'), {'id': project_id}).scalar()
        plan = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
                            {'id': plan_id, 'project': project_id}).scalar()
        if not project or not plan:
            raise CommerceFailure('NOT_FOUND', 404)
        return StoreProject.model_validate_json(project), CommercePlan.model_validate_json(plan)

    @staticmethod
    def _binding(project, plan, target):
        return {'project_revision': project.revision, 'plan_revision': plan.revision,
                'plan_hash': digest(plan), 'target': target.model_dump(mode='json')}

    @staticmethod
    def _check_binding(binding, project, plan):
        if (binding['project_revision'] != project.revision or binding['plan_revision'] != plan.revision
                or binding['plan_hash'] != digest(plan)
                or not any(item.model_dump(mode='json') == binding['target'] for item in project.environment_refs)):
            raise CommerceFailure('REVIEW_STALE')

    @staticmethod
    def _validate_source(changeset, report, plan):
        for value in (changeset.content_hash, report.snapshot_hash):
            if not re.fullmatch(r'[a-f0-9]{64}', value):
                raise CommerceFailure('VERIFICATION_FAILED', 422)
        if report.code_revision is not None and not re.fullmatch(r'[a-f0-9]{40}', report.code_revision):
            raise CommerceFailure('VERIFICATION_FAILED', 422)
        if (plan.content_hash != changeset.content_hash or plan.snapshot_hash != report.snapshot_hash
                or plan.code_revision != report.code_revision or not report.passed or not report.checks
                or not report.evidence_refs or any(item.get('passed') is not True for item in report.checks)):
            raise CommerceFailure('VERIFICATION_FAILED', 422)
        for op in changeset.operations:
            validate_operation(op)
            if changeset.resource_preconditions.get(op.resource_key) != op.expected_fingerprint:
                raise CommerceFailure('REVIEW_STALE')
            if op.kind == 'install_theme_package':
                package = op.payload['package']
                if (package['code_revision'] != report.code_revision
                        or package['content_sha256'] != changeset.content_hash
                        or package['package_sha256'] != changeset.package_hash):
                    raise CommerceFailure('VERIFICATION_FAILED', 422)

    def _validate_stored(self, row, changeset, review, report, plan):
        actual = digest(changeset.model_dump(mode='json', exclude={'digest'}))
        if (row['digest'] != actual or changeset.digest != actual or report.changeset_digest != actual
                or review.get('report_hash') != digest(report)
                or row['plan_id'] != changeset.plan_id or row['project_id'] != changeset.project_id):
            raise CommerceFailure('REVIEW_STALE')
        self._validate_source(changeset, report, plan)

    def stage_review(self, changeset, report, *, connection_id, expected_project_revision, expected_plan_revision):
        # Freeze caller-owned candidate before crossing the transaction boundary.
        changeset = ChangeSet.model_validate_json(encode(changeset))
        report = VerificationReport.model_validate_json(encode(report))
        actual = digest(changeset.model_dump(mode='json', exclude={'digest'}))
        if (not 1 <= len(changeset.operations) <= 100 or changeset.digest != actual
                or len({op.operation_id for op in changeset.operations}) != len(changeset.operations)
                or not report.passed or report.changeset_digest != actual or not report.checks
                or not report.evidence_refs or any(check.get('passed') is not True for check in report.checks)):
            raise CommerceFailure('VERIFICATION_FAILED', 422)
        for op in changeset.operations:
            validate_operation(op)
            if changeset.resource_preconditions.get(op.resource_key) != op.expected_fingerprint:
                raise CommerceFailure('REVIEW_STALE')
        with self.db.transaction() as conn:
            project, plan = self._source(conn, changeset.project_id, changeset.plan_id)
            if (project.revision != expected_project_revision or plan.revision != expected_plan_revision
                    or plan.state != 'REVIEW_REQUIRED' or plan.content_hash != changeset.content_hash
                    or plan.code_revision != report.code_revision or plan.snapshot_hash != report.snapshot_hash):
                raise CommerceFailure('REVIEW_STALE')
            self._validate_source(changeset, report, plan)
            targets = [ref for ref in project.environment_refs if ref.connector_ref == connection_id and ref.environment == changeset.environment]
            if len(targets) != 1:
                raise CommerceFailure('PERMISSION_DENIED', 403)
            envelope = {'report_hash': digest(report), 'report': report.model_dump(mode='json'), 'binding': self._binding(project, plan, targets[0])}
            existing = conn.execute(text('SELECT data,verification FROM commerce_changesets WHERE id=:id'), {'id': changeset.id}).mappings().first()
            if existing:
                if existing['data'] != encode(changeset) or existing['verification'] != encode(envelope):
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return changeset
            conn.execute(text('INSERT INTO commerce_changesets VALUES(:id,:plan,:project,:digest,:data,:verification)'),
                         {'id':changeset.id, 'plan':plan.id, 'project':project.id, 'digest':actual,
                          'data':encode(changeset), 'verification':encode(envelope)})
            self.commerce.event(conn, project.id, 'changeset_reviewed', {'changeset_id':changeset.id, 'digest':actual})
            return changeset

    def _load(self, conn, approval_row):
        import json
        payload = json.loads(approval_row['data'])
        original = ApprovalGrant.model_validate(payload['grant'])
        if original.expires_at != approval_row['expires_at']:
            raise CommerceFailure('REVIEW_STALE')
        grant = original.model_copy(update={'status': approval_row['status']})
        row = self._row(conn, approval_row['changeset_id'])
        changeset = ChangeSet.model_validate_json(row['data'])
        review = json.loads(row['verification'])
        report = VerificationReport.model_validate(review['report'])
        project, plan = self._source(conn, changeset.project_id, changeset.plan_id)
        if grant.status != 'approved':
            raise CommerceFailure('APPROVAL_REQUIRED', 403)
        if not math.isfinite(self.clock()) or not math.isfinite(grant.expires_at) or self.clock() >= grant.expires_at:
            raise CommerceFailure('APPROVAL_EXPIRED', 403)
        self._check_binding(payload['binding'], project, plan)
        self._validate_stored(row, changeset, review, report, plan)
        actual = digest(changeset.model_dump(mode='json', exclude={'digest'}))
        if (plan.state != 'APPROVED' or row['digest'] != actual or changeset.digest != actual
                or grant.changeset_digest != actual or approval_row['digest'] != actual
                or not report.passed or grant.verification_hash != digest(report)
                or report.changeset_digest != actual or grant.resource_preconditions != changeset.resource_preconditions
                or grant.project_id != project.id or grant.environment != changeset.environment):
            raise CommerceFailure('REVIEW_STALE')
        return ApprovedExecution(grant, changeset, report), payload['binding']

    def approve(self, changeset_id, reviewed_digest, *, expected_revision):
        import json
        self.expire_due()
        with self.db.transaction() as conn:
            row = self._row(conn, changeset_id)
            if row['digest'] != reviewed_digest:
                raise CommerceFailure('REVIEW_STALE')
            previous = conn.execute(text('SELECT * FROM commerce_approvals WHERE changeset_id=:id ORDER BY rowid DESC LIMIT 1'),
                                    {'id':changeset_id}).mappings().first()
            if previous:
                context, _binding = self._load(conn, previous)
                if json.loads(previous['data'])['review_revision'] != expected_revision:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return context.approval
            changeset = ChangeSet.model_validate_json(row['data'])
            review = json.loads(row['verification'])
            report = VerificationReport.model_validate(review['report'])
            project, plan = self._source(conn, changeset.project_id, changeset.plan_id)
            self._check_binding(review['binding'], project, plan)
            self._validate_stored(row, changeset, review, report, plan)
            if plan.revision != expected_revision or plan.state != 'REVIEW_REQUIRED':
                raise CommerceFailure('REVIEW_STALE')
            now = self.clock()
            if not math.isfinite(now):
                raise CommerceFailure('INPUT_INVALID', 422)
            approved = plan.model_copy(update={'state':'APPROVED','revision':plan.revision+1})
            grant = ApprovalGrant(id=uuid.uuid4().hex, project_id=project.id, environment=changeset.environment,
                                  changeset_digest=changeset.digest, resource_preconditions=changeset.resource_preconditions,
                                  verification_hash=digest(report), expires_at=now+1800)
            payload = {'grant':grant.model_dump(mode='json'), 'binding':self._binding(project, approved,
                       next(ref for ref in project.environment_refs if ref.model_dump(mode='json')==review['binding']['target'])),
                       'review_revision':expected_revision}
            conn.execute(text('UPDATE commerce_plans SET data=:data,revision=:revision WHERE id=:id'),
                         {'data':encode(approved),'revision':approved.revision,'id':plan.id})
            conn.execute(text('INSERT INTO commerce_approvals VALUES(:id,:changeset,:digest,:status,:expires,:data)'),
                         {'id':grant.id,'changeset':changeset.id,'digest':changeset.digest,'status':'approved',
                          'expires':grant.expires_at,'data':encode(payload)})
            self.commerce.event(conn, project.id, 'approval_granted', {'approval_id':grant.id,'changeset_id':changeset.id,'expires_at':grant.expires_at})
            return grant

    def _revoke_row(self, conn, row, kind):
        import json
        if row['status'] != 'approved':
            return
        payload = json.loads(row['data'])
        changeset = ChangeSet.model_validate_json(self._row(conn, row['changeset_id'])['data'])
        project, plan = self._source(conn, changeset.project_id, changeset.plan_id)
        conn.execute(text("UPDATE commerce_approvals SET status='revoked' WHERE id=:id"), {'id':row['id']})
        try:
            self._check_binding(payload['binding'], project, plan)
        except CommerceFailure:
            # A newer revision must not be restored to this old review.
            pass
        else:
            if plan.state == 'APPROVED':
                updated = plan.model_copy(update={'state':'REVIEW_REQUIRED', 'revision':plan.revision+1})
                conn.execute(text('UPDATE commerce_plans SET data=:data,revision=:revision WHERE id=:id'),
                             {'data':encode(updated),'revision':updated.revision,'id':plan.id})
        self.commerce.event(conn, project.id, kind, {'approval_id':row['id']})

    def expire_due(self):
        now = self.clock()
        if not math.isfinite(now):
            raise CommerceFailure('INPUT_INVALID', 422)
        with self.db.transaction() as conn:
            rows = conn.execute(text("SELECT * FROM commerce_approvals WHERE status='approved' AND expires_at<=:now"), {'now':now}).mappings().all()
            for row in rows:
                self._revoke_row(conn, row, 'approval_expired')

    def revoke(self, approval_id, *, project_id):
        with self.db.transaction() as conn:
            row = conn.execute(text('SELECT a.* FROM commerce_approvals a JOIN commerce_changesets c ON a.changeset_id=c.id WHERE a.id=:id AND c.project_id=:project'),
                               {'id':approval_id,'project':project_id}).mappings().first()
            if not row:
                raise CommerceFailure('NOT_FOUND', 404)
            self._revoke_row(conn, row, 'approval_revoked')

    def provider(self, connection):
        async def lookup(approval_id):
            def read():
                self.expire_due()
                with self.db.transaction() as conn:
                    row = conn.execute(text('SELECT * FROM commerce_approvals WHERE id=:id'), {'id':approval_id}).mappings().first()
                    if not row:
                        raise CommerceFailure('NOT_FOUND', 404)
                    context, binding = self._load(conn, row)
                    target = binding['target']
                    if (target['project_id'] != connection.project_id or target['connector_ref'] != connection.connection_id
                            or target['environment'] != connection.environment or target['public_url'].rstrip('/') != connection.base_url.rstrip('/')):
                        raise CommerceFailure('PERMISSION_DENIED', 403)
                    return context
            return await asyncio.to_thread(read)
        return lookup
