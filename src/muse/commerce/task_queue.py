"""Explicitly authorized draft admission, dependency waits, and atomic batch actions."""
import json

from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan, CommerceTaskDraft
from muse.commerce.repository import digest
from muse.commerce.task_drafts import CommerceDraftService


class CommerceTaskQueue:
    def __init__(self, repo, workflows):
        self.repo, self.workflows = repo, workflows
        self.drafts = CommerceDraftService(repo, workflows)

    def _active(self, conn, project_id):
        return conn.execute(text("SELECT COUNT(DISTINCT p.id) FROM commerce_plans p JOIN commerce_steps s ON s.plan_id=p.id "
            "JOIN tasks t ON t.id=s.task_id WHERE p.project_id=:project AND t.status NOT IN ('SUCCEEDED','FAILED','CANCELLED')"),
            {'project': project_id}).scalar()

    def _reason(self, conn, draft):
        project = self.repo._project(conn, draft.project_id)
        if project.revision != draft.project_revision:
            return 'project_changed'
        if draft.theme_source_id is None and draft.code_base_revision != self.drafts._code_revision(conn, draft.project_id):
            return 'code_base_changed'
        waiting = False
        for identity in draft.dependency_plan_ids:
            raw = conn.execute(text('SELECT data,root_task_id FROM commerce_plans WHERE id=:id AND project_id=:project'),
                               {'id': identity, 'project': draft.project_id}).mappings().first()
            if raw is None:
                return 'dependency_missing'
            plan = CommercePlan.model_validate_json(raw['data'])
            cancelled = conn.execute(text('SELECT cancel_requested FROM tasks WHERE id=:id'),
                                     {'id': raw['root_task_id']}).scalar()
            if cancelled or plan.state in {'FAILED', 'CANCELLED', 'STALE', 'PARTIAL', 'NEEDS_RECONCILIATION'}:
                return 'dependency_failed'
            waiting |= plan.state != 'SUCCEEDED'
        if waiting:
            return 'dependencies'
        if self._active(conn, draft.project_id) >= self.workflows.settings.commerce_max_active_plans:
            return 'capacity'
        return None

    def capacity(self, project_id):
        with self.repo.db.transaction() as conn:
            self.repo._project(conn, project_id)
            active = self._active(conn, project_id)
            queued = conn.execute(text("SELECT COUNT(*) FROM commerce_task_drafts WHERE project_id=:project AND json_extract(data,'$.status')='QUEUED'"),
                                  {'project': project_id}).scalar()
            return {'project_id': project_id, 'active': active, 'limit': self.workflows.settings.commerce_max_active_plans,
                    'queued': queued, 'available': max(0, self.workflows.settings.commerce_max_active_plans - active),
                    'code_base_revision': self.drafts._code_revision(conn, project_id), 'project_revision': self.repo._project(conn, project_id).revision}

    def batch(self, project_id, body):
        from muse.commerce.code_integration import CommerceCodeIntegration
        identity = digest([project_id, 'draft-batch', body.client_request_id])
        request_hash = digest(body.model_dump(mode='json'))
        with self.repo.db.transaction() as conn:
            old = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='draft_batch_receipt'"),
                               {'id': identity}).mappings().first()
            if old:
                saved = json.loads(old['data'])
                if digest(saved) != old['digest'] or saved['request_hash'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return [self.drafts._read(conn, project_id, draft_id) for draft_id in saved['ids']]
            self.repo._project(conn, project_id, body.expected_project_revision)
            ids = [item.draft_id for item in body.items]
            if len(set(ids)) != len(ids):
                raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
            drafts = [self.drafts._read(conn, project_id, identity) for identity in ids]
            for draft, item in zip(drafts, body.items):
                allowed = {'DRAFT', 'QUEUED'} if body.action == 'cancel' else {'DRAFT'}
                if draft.revision != item.expected_revision or draft.status not in allowed:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                if body.action == 'start' and self._reason(conn, draft) in {'project_changed', 'code_base_changed', 'dependency_failed', 'dependency_missing'}:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            result = []
            for draft in drafts:
                if body.action != 'start':
                    result.append(self.drafts._save(conn, draft.model_copy(update={'status': 'ARCHIVED', 'queue_reason': None, 'auto_apply_local': False}), 'task_draft_archived'))
                elif (reason := self._reason(conn, draft)):
                    result.append(self.drafts._save(conn, draft.model_copy(update={'status': 'QUEUED', 'queue_reason': reason,
                        'auto_apply_local': body.auto_apply_local}), 'task_draft_queued'))
                else:
                    if body.auto_apply_local:
                        draft = self.drafts._save(conn, draft.model_copy(update={'auto_apply_local': True}), 'task_auto_apply_requested')
                    result.append(self.drafts.start(project_id, draft.id, draft.revision, draft.project_revision, _connection=conn))
            CommerceCodeIntegration._save(conn, identity, project_id, None, 'draft_batch_receipt',
                                           {'request_hash': request_hash, 'ids': ids})
            return result

    def promote(self):
        """Worker-only mutations; never called by a read/refresh endpoint."""
        with self.repo.db.transaction() as conn:
            rows = conn.execute(text("SELECT data FROM commerce_task_drafts WHERE json_extract(data,'$.status')='QUEUED' ORDER BY created_at,id")).all()
            for row in rows:
                draft = CommerceTaskDraft.model_validate_json(row[0])
                reason = self._reason(conn, draft)
                if reason:
                    if draft.queue_reason != reason:
                        self.drafts._save(conn, draft.model_copy(update={'queue_reason': reason}), 'task_queue_waiting')
                    continue
                # A savepoint leaves this authorization queued if admission fails.
                try:
                    with conn.begin_nested():
                        ready = self.drafts._save(conn, draft.model_copy(update={'status': 'DRAFT', 'queue_reason': None}), 'task_queue_released')
                        self.drafts.start(draft.project_id, ready.id, ready.revision, ready.project_revision, _connection=conn)
                except CommerceFailure as error:
                    self.drafts._save(conn, draft.model_copy(update={'queue_reason': error.public.code}), 'task_queue_blocked')
