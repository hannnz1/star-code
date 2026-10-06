"""One-shot local code application. Never grants remote publication permission."""
import json
import time
from contextlib import nullcontext
from typing import Literal

from pydantic import Field
from sqlalchemy import text

from muse.commerce.code_integration import CommerceCodeIntegration
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan, Contract
from muse.commerce.repository import digest


class LocalApplyAutomation(Contract):
    id: str
    project_id: str
    plan_id: str
    revision: int
    project_revision: int
    head_revision: int
    status: Literal['ARMED', 'APPLYING', 'APPLIED', 'BLOCKED', 'CANCELLED'] = 'ARMED'
    reason: str | None = None
    expires_at: float
    apply_body: dict | None = None


class ArmLocalApply(Contract):
    expected_plan_revision: int = Field(ge=1, strict=True)
    expected_project_revision: int = Field(ge=1, strict=True)
    expected_head_revision: int = Field(ge=0, strict=True)
    client_request_id: str = Field(min_length=1, max_length=200)


class AutomationControl(Contract):
    expected_revision: int = Field(ge=1, strict=True)


class LocalApplyService:
    def __init__(self, repo, source_root):
        self.repo, self.integration = repo, CommerceCodeIntegration(repo, source_root)

    def _read(self, conn, project_id, plan_id):
        identity = digest([project_id, plan_id, 'local-apply-automation'])
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='local_apply_automation'"),
                           {'id': identity, 'project': project_id}).mappings().first()
        if not row:
            return None
        value = LocalApplyAutomation.model_validate_json(row['data'])
        if digest(value.model_dump(mode='json')) != row['digest']:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return value

    def get(self, project_id, plan_id):
        self.repo.get_plan(plan_id, project_id=project_id)
        with self.repo.db.transaction() as conn:
            return self._read(conn, project_id, plan_id)

    def _save(self, conn, value):
        self.integration._save(conn, value.id, value.project_id, value.plan_id, 'local_apply_automation', value.model_dump(mode='json'))
        self.repo.event(conn, value.project_id, 'local_apply_automation',
                        {'plan_id': value.plan_id, 'status': value.status, 'published': False})
        return value

    def arm(self, project_id, plan_id, body, *, _connection=None):
        receipt_id = digest([project_id, plan_id, 'arm-local-apply', body.client_request_id])
        request_hash = digest(body.model_dump(mode='json'))
        with (nullcontext(_connection) if _connection is not None else self.repo.db.transaction()) as conn:
            receipt = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='local_apply_arm_receipt'"),
                                   {'id': receipt_id}).mappings().first()
            if receipt:
                saved = json.loads(receipt['data'])
                if digest(saved) != receipt['digest'] or saved['request_hash'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return self._read(conn, project_id, plan_id)
            self.repo._project(conn, project_id, body.expected_project_revision)
            raw = conn.execute(text('SELECT data,root_task_id FROM commerce_plans WHERE id=:id AND project_id=:project'),
                               {'id': plan_id, 'project': project_id}).mappings().first()
            if not raw:
                raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
            plan = CommercePlan.model_validate_json(raw['data'])
            root = conn.execute(text('SELECT checkpoint,cancel_requested FROM tasks WHERE id=:id'),
                                {'id': raw['root_task_id']}).mappings().first()
            binding = json.loads(root['checkpoint']).get('commerce', {}) if root else {}
            head = self.integration.head(conn, project_id)
            previous = self._read(conn, project_id, plan_id)
            if (plan.revision != body.expected_plan_revision or not root or root['cancel_requested']
                    or binding.get('project_revision') != body.expected_project_revision
                    or (head.revision if head else 0) != body.expected_head_revision
                    or plan.state in {'FAILED', 'CANCELLED', 'STALE', 'NEEDS_INPUT', 'PUBLISHING', 'PARTIAL', 'NEEDS_RECONCILIATION'}
                    or previous and previous.status in {'ARMED', 'APPLYING'}):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            value = LocalApplyAutomation(id=digest([project_id, plan_id, 'local-apply-automation']), project_id=project_id,
                plan_id=plan_id, revision=previous.revision + 1 if previous else 1,
                project_revision=body.expected_project_revision, head_revision=body.expected_head_revision,
                expires_at=time.time() + 86400)
            self._save(conn, value)
            self.integration._save(conn, receipt_id, project_id, plan_id, 'local_apply_arm_receipt', {'request_hash': request_hash})
            return value

    def cancel(self, project_id, plan_id, expected_revision):
        with self.repo.db.transaction() as conn:
            value = self._read(conn, project_id, plan_id)
            if not value or value.revision != expected_revision or value.status != 'ARMED':
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            return self._save(conn, value.model_copy(update={'status': 'CANCELLED', 'revision': value.revision + 1}))

    def process(self):
        from muse.commerce.api import CodeIntegrationInput
        rows = self.repo.db.rows("SELECT data FROM commerce_artifacts WHERE kind='local_apply_automation' AND json_extract(data,'$.status') IN ('ARMED','APPLYING')")
        for row in rows:
            snapshot = LocalApplyAutomation.model_validate_json(row['data'])
            with self.repo.db.transaction() as conn:
                value = self._read(conn, snapshot.project_id, snapshot.plan_id)
                if not value or value.status not in {'ARMED', 'APPLYING'}:
                    continue
                if value.status == 'ARMED':
                    reason = None
                    project = self.repo._project(conn, value.project_id)
                    plan_data = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
                                             {'id': value.plan_id, 'project': value.project_id}).scalar()
                    plan = CommercePlan.model_validate_json(plan_data)
                    head = self.integration.head(conn, value.project_id)
                    if time.time() >= value.expires_at:
                        reason = 'expired'
                    elif project.revision != value.project_revision or (head.revision if head else 0) != value.head_revision:
                        reason = 'baseline_changed'
                    elif plan.state in {'FAILED', 'CANCELLED', 'STALE', 'NEEDS_INPUT'}:
                        reason = 'plan_ineligible'
                    elif not plan.code_revision:
                        continue
                    else:
                        try:
                            review, _, _ = self.integration._review(conn, value.project_id, value.plan_id, plan.revision)
                            if review.applicable:
                                value = value.model_copy(update={'status': 'APPLYING', 'revision': value.revision + 1,
                                    'apply_body': {'expected_plan_revision': review.plan_revision,
                                    'expected_head_revision': review.head_revision, 'review_digest': review.review_digest,
                                    'client_request_id': 'auto:' + value.id + ':' + str(value.revision)}})
                                self._save(conn, value)
                            else:
                                reason = review.reason
                        except CommerceFailure as error:
                            reason = error.public.code
                    if reason:
                        self._save(conn, value.model_copy(update={'status': 'BLOCKED', 'reason': reason, 'revision': value.revision + 1}))
                        continue
            try:
                self.integration.apply(value.project_id, value.plan_id, CodeIntegrationInput.model_validate(value.apply_body),
                                       authorized_until=value.expires_at)
                status, reason = 'APPLIED', None
            except CommerceFailure as error:
                status, reason = 'BLOCKED', error.public.code
            with self.repo.db.transaction() as conn:
                latest = self._read(conn, value.project_id, value.plan_id)
                if latest.status == 'APPLYING' and latest.revision == value.revision:
                    self._save(conn, latest.model_copy(update={'status': status, 'reason': reason, 'revision': latest.revision + 1}))
