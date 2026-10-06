"""Durable merchant task drafts, separate from running workflow plans."""
import time
from contextlib import nullcontext

from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlanLabel, CommerceTaskDraft
from muse.commerce.repository import digest, encode


def proposed_steps(kind):
    if kind == 'build_site':
        return ['店长核对品牌目标与已有资料', '商品内容整理商品事实与文案',
                '网站开发封存主题代码', '隔离环境验证页面和购买流程', '商家审查结果后明确发布']
    return ['店长确认新品范围与店铺上下文', '商品内容整理事实、文案和图片',
            '网站开发核对商品页面与代码', '隔离环境验证新品与购买流程', '商家审查结果后明确发布']


class CommerceDraftService:
    def __init__(self, repo, workflows):
        self.repo, self.workflows = repo, workflows

    @staticmethod
    def _code_revision(conn, project_id):
        from muse.commerce.code_integration import CommerceCodeIntegration
        head = CommerceCodeIntegration.head(conn, project_id)
        return head.revision if head else 0

    @staticmethod
    def _read(conn, project_id, draft_id):
        row = conn.execute(text('SELECT data,revision FROM commerce_task_drafts WHERE id=:id AND project_id=:project'),
                           {'id': draft_id, 'project': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
        draft = CommerceTaskDraft.model_validate_json(row['data'])
        if row['revision'] != draft.revision:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return draft

    @staticmethod
    def _dependencies(conn, project_id, ids):
        if len(ids) != len(set(ids)) or any(not isinstance(value, str) or not 1 <= len(value) <= 200 for value in ids):
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
        for identity in ids:
            if not conn.execute(text('SELECT 1 FROM commerce_plans WHERE id=:id AND project_id=:project'),
                                {'id': identity, 'project': project_id}).first():
                raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)

    def list(self, project_id):
        self.repo.get_project(project_id)
        return [CommerceTaskDraft.model_validate_json(row['data']) for row in self.repo.db.rows(
            'SELECT data FROM commerce_task_drafts WHERE project_id=:project ORDER BY created_at,id',
            {'project': project_id})]

    def list_labels(self, project_id):
        self.repo.get_project(project_id)
        return [CommercePlanLabel.model_validate(row) for row in self.repo.db.rows(
            'SELECT plan_id,project_id,title,revision,updated_at FROM commerce_plan_labels WHERE project_id=:project',
            {'project': project_id})]

    def rename_plan(self, project_id, plan_id, title, expected_revision):
        with self.repo.db.transaction() as conn:
            if not conn.execute(text('SELECT 1 FROM commerce_plans WHERE id=:id AND project_id=:project'),
                                {'id': plan_id, 'project': project_id}).first():
                raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
            row = conn.execute(text('SELECT revision FROM commerce_plan_labels WHERE plan_id=:id AND project_id=:project'),
                               {'id': plan_id, 'project': project_id}).mappings().first()
            current = row['revision'] if row else 0
            if current != expected_revision:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            label = CommercePlanLabel(plan_id=plan_id, project_id=project_id, title=title,
                                      revision=current + 1, updated_at=time.time())
            if row:
                conn.execute(text('UPDATE commerce_plan_labels SET revision=:revision,title=:title,updated_at=:now WHERE plan_id=:id'),
                             {'id': plan_id, 'revision': label.revision, 'title': title, 'now': label.updated_at})
            else:
                conn.execute(text('INSERT INTO commerce_plan_labels VALUES(:id,:project,1,:title,:now)'),
                             {'id': plan_id, 'project': project_id, 'title': title, 'now': label.updated_at})
            self.repo.event(conn, project_id, 'plan_renamed', {'plan_id': plan_id, 'revision': label.revision})
            return label

    def create(self, project_id, data, *, _connection=None, provenance=None):
        identity = digest([project_id, 'commerce_task_draft', data.client_request_id])
        request_hash = digest([project_id, data.model_dump(mode='json'), provenance] if provenance else [project_id, data.model_dump(mode='json')])
        with (nullcontext(_connection) if _connection is not None else self.repo.db.transaction()) as conn:
            old = conn.execute(text('SELECT data,request_digest FROM commerce_task_drafts WHERE id=:id'),
                               {'id': identity}).mappings().first()
            if old:
                if old['request_digest'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return CommerceTaskDraft.model_validate_json(old['data'])
            self.repo._project(conn, project_id, data.expected_project_revision)
            self._dependencies(conn, project_id, data.dependency_plan_ids)
            now = time.time()
            draft = CommerceTaskDraft(id=identity, project_id=project_id, kind=data.kind, title=data.title,
                prompt=data.prompt, max_requests=data.max_requests, import_id=data.import_id,
                theme_source_id=data.theme_source_id, proposed_steps=proposed_steps(data.kind),
                project_revision=data.expected_project_revision, code_base_revision=self._code_revision(conn, project_id),
                created_at=now, updated_at=now)
            draft = draft.model_copy(update={'dependency_plan_ids': data.dependency_plan_ids})
            if provenance:
                draft = CommerceTaskDraft.model_validate({**draft.model_dump(), **provenance})
            conn.execute(text('INSERT INTO commerce_task_drafts VALUES(:id,:project,:request,:digest,1,:data,:now,:now)'),
                         {'id': identity, 'project': project_id,
                          'request': f'{project_id}:{data.client_request_id}', 'digest': request_hash,
                          'data': encode(draft), 'now': now})
            self.repo.event(conn, project_id, 'task_draft_created', {'draft_id': identity})
            return draft

    def _save(self, conn, draft, event):
        changed = draft.model_copy(update={'revision': draft.revision + 1, 'updated_at': time.time()})
        conn.execute(text('UPDATE commerce_task_drafts SET revision=:revision,data=:data,updated_at=:now WHERE id=:id'),
                     {'id': changed.id, 'revision': changed.revision, 'data': encode(changed), 'now': changed.updated_at})
        self.repo.event(conn, changed.project_id, event, {'draft_id': changed.id, 'revision': changed.revision})
        return changed

    def edit(self, project_id, draft_id, data):
        with self.repo.db.transaction() as conn:
            draft = self._read(conn, project_id, draft_id)
            if draft.revision != data.expected_revision or draft.status != 'DRAFT':
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            self.repo._project(conn, project_id, data.expected_project_revision)
            self._dependencies(conn, project_id, data.dependency_plan_ids)
            draft = draft.model_copy(update={'kind': data.kind, 'title': data.title, 'prompt': data.prompt,
                'max_requests': data.max_requests, 'import_id': data.import_id,
                'theme_source_id': data.theme_source_id, 'proposed_steps': proposed_steps(data.kind),
                'project_revision': data.expected_project_revision, 'code_base_revision': self._code_revision(conn, project_id),
                'dependency_plan_ids': data.dependency_plan_ids, 'queue_reason': None, 'auto_apply_local': False})
            return self._save(conn, draft, 'task_draft_updated')

    def rename(self, project_id, draft_id, title, expected_revision):
        with self.repo.db.transaction() as conn:
            draft = self._read(conn, project_id, draft_id)
            if draft.revision != expected_revision:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            return self._save(conn, draft.model_copy(update={'title': title}), 'task_draft_renamed')

    def archive(self, project_id, draft_id, expected_revision):
        with self.repo.db.transaction() as conn:
            draft = self._read(conn, project_id, draft_id)
            if draft.revision != expected_revision or draft.status != 'DRAFT':
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            return self._save(conn, draft.model_copy(update={'status': 'ARCHIVED', 'auto_apply_local': False}), 'task_draft_archived')

    def restore(self, project_id, draft_id, expected_revision):
        with self.repo.db.transaction() as conn:
            draft = self._read(conn, project_id, draft_id)
            if draft.revision != expected_revision or draft.status != 'ARCHIVED':
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            return self._save(conn, draft.model_copy(update={'status': 'DRAFT', 'auto_apply_local': False}), 'task_draft_restored')

    def start(self, project_id, draft_id, expected_revision, expected_project_revision, *, _connection=None):
        with (nullcontext(_connection) if _connection is not None else self.repo.db.transaction()) as conn:
            draft = self._read(conn, project_id, draft_id)
            if draft.status == 'STARTED' and draft.revision == expected_revision and draft.plan_id:
                return draft
            if (draft.revision != expected_revision or draft.status != 'DRAFT'
                    or draft.project_revision != expected_project_revision):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            self.repo._project(conn, project_id, expected_project_revision)
            from muse.commerce.task_queue import CommerceTaskQueue
            if CommerceTaskQueue(self.repo, self.workflows)._reason(conn, draft):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            if draft.theme_source_id is None and draft.code_base_revision != self._code_revision(conn, project_id):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            from muse.commerce.conflict_context import capture_repair_context
            repair_context = capture_repair_context(self.repo, conn, draft)
            plan = self.workflows.create_workflow(project_id, draft.kind, draft.prompt, f'draft:{draft.id}',
                expected_project_revision, max_requests=draft.max_requests, import_id=draft.import_id,
                theme_source_id=draft.theme_source_id, _connection=conn, repair_context=repair_context)
            if draft.auto_apply_local:
                from muse.commerce.task_automation import ArmLocalApply, LocalApplyService
                LocalApplyService(self.repo, self.workflows.settings.data_dir / 'commerce-source.git').arm(project_id, plan.id,
                    ArmLocalApply(expected_plan_revision=plan.revision, expected_project_revision=expected_project_revision,
                        expected_head_revision=self._code_revision(conn, project_id), client_request_id='draft:' + draft.id), _connection=conn)
            started = self._save(conn, draft.model_copy(update={'status': 'STARTED', 'plan_id': plan.id}),
                                 'task_draft_started')
            return started
