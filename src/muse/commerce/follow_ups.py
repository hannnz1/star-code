"""Evidence-bound deterministic suggestions. Reading never schedules model work."""
import json
from contextlib import nullcontext
from typing import Literal

from pydantic import Field
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan, Contract
from muse.commerce.repository import digest
from muse.commerce.task_drafts import CommerceDraftService


class FollowUpSuggestion(Contract):
    id: str
    source_plan_id: str
    source_plan_revision: int
    project_revision: int
    code_base_revision: int
    title: str
    kind: Literal['build_site', 'launch_products']
    prompt: str
    evidence: list[str]
    review_digest: str


class FollowUpAccept(Contract):
    suggestion_id: str = Field(min_length=1, max_length=200)
    review_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    client_request_id: str = Field(min_length=1, max_length=200)


class FollowUpSelection(Contract):
    suggestion_id: str = Field(min_length=1, max_length=200)
    review_digest: str = Field(pattern=r'^[a-f0-9]{64}$')


class FollowUpBatch(Contract):
    items: list[FollowUpSelection] = Field(min_length=1, max_length=20)
    client_request_id: str = Field(min_length=1, max_length=200)


class FollowUpService:
    def __init__(self, repo, workflows):
        self.repo, self.workflows = repo, workflows

    def _suggestions(self, conn, project_id, plan_id):
        project = self.repo._project(conn, project_id)
        row = conn.execute(text('SELECT data,root_task_id FROM commerce_plans WHERE id=:id AND project_id=:project'),
                           {'id': plan_id, 'project': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
        plan = CommercePlan.model_validate_json(row['data'])
        root = conn.execute(text('SELECT checkpoint,cancel_requested FROM tasks WHERE id=:id'),
                            {'id': row['root_task_id']}).mappings().first()
        if not root or root['cancel_requested'] or plan.state in {'CANCELLED', 'STALE', 'PUBLISHING', 'PARTIAL', 'NEEDS_RECONCILIATION'}:
            return []
        binding = json.loads(root['checkpoint']).get('commerce', {})
        if (binding.get('project_revision') != project.revision or binding.get('project_id') != project_id
                or binding.get('plan_id') != plan_id):
            return []
        options = []
        if plan.state == 'SUCCEEDED':
            if plan.kind == 'build_site':
                options.append(('products', '准备新品上线', 'launch_products',
                    '根据已完成建站成果准备新品。先选择当前商品批次，核对事实、图片与页面，重新验证并提交商家审查。',
                    ['建站计划状态：SUCCEEDED']))
            options.append(('improve', '检查网站体验并提出改进', 'build_site',
                '检查当前主题的导航、移动端和商品页面，保留商品事实及购买流程，封存改进并提交独立验证与审查。',
                ['来源计划状态：SUCCEEDED']))
        elif plan.state in {'FAILED', 'BLOCKED', 'NEEDS_INPUT'} and plan.error_code:
            options.append(('repair', '修复阻塞后重新准备', plan.kind,
                f'先诊断来源计划的阻塞 {plan.error_code}，确认资料和环境是否齐备；保留原成果与商品事实，再准备新的可审查成果。',
                [f'来源状态：{plan.state}', f'错误码：{plan.error_code}']))
        if plan.code_revision and plan.state not in {'FAILED', 'NEEDS_INPUT'}:
            from muse.commerce.code_integration import CommerceCodeIntegration
            review, _, _ = CommerceCodeIntegration(self.repo, None)._review(conn, project_id, plan_id, plan.revision)
            if review.reason == 'conflicts':
                options.append(('conflict', '准备代码冲突修复', 'build_site',
                    f'来源计划 {plan.id} 的封存成果与当前代码基线在以下文件冲突：'
                    + '、'.join(review.conflict_files)
                    + '。先审查来源计划差异，再基于当前代码起点协调修复。不要静默选择任一方；重新封存、验证并审查。',
                    ['当前代码整合审查：conflicts', '冲突文件：' + '、'.join(review.conflict_files)]))
        revision = CommerceDraftService._code_revision(conn, project_id)
        suggestions = [FollowUpSuggestion(id=digest([plan.id, key]), source_plan_id=plan.id,
            source_plan_revision=plan.revision, project_revision=project.revision, code_base_revision=revision,
            title=title, kind=kind, prompt=prompt, evidence=evidence,
            review_digest=digest([plan.model_dump(mode='json'), project.revision, revision, key, title, prompt, evidence]))
            for key, title, kind, prompt, evidence in options]
        from muse.commerce.follow_up_models import ModelSuggestionJob, suggestion_context
        from muse.commerce.planning import provider_identity
        try:
            context_hash = digest(suggestion_context(self.repo, conn, project_id, plan_id))
        except CommerceFailure:
            return suggestions
        for row in conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='follow_up_model_job' AND json_extract(data,'$.status')='SUCCEEDED' ORDER BY rowid DESC LIMIT 1"),
                                {'project': project_id, 'plan': plan_id}).mappings():
            job = ModelSuggestionJob.model_validate_json(row['data'])
            if digest(job.model_dump(mode='json')) != row['digest']:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            if job.context_digest != context_hash or job.provider_hash != provider_identity(self.workflows.settings):
                continue
            for index, item in enumerate(job.suggestions):
                suggestions.append(FollowUpSuggestion(id=digest([job.id, index]), source_plan_id=plan.id,
                    source_plan_revision=plan.revision, project_revision=project.revision, code_base_revision=revision,
                    title=item.title, kind=item.kind, prompt=item.prompt,
                    evidence=['模型建议：待审查，不代表验证结果', '来源任务：' + job.id[:8]],
                    review_digest=digest([job.model_dump(mode='json'), context_hash, index])))
        return suggestions

    def list(self, project_id, plan_id):
        with self.repo.db.transaction() as conn:
            return self._suggestions(conn, project_id, plan_id)

    def accept(self, project_id, plan_id, body, *, _connection=None):
        from muse.commerce.api import TaskDraftInput
        provenance = {'source_plan_id': plan_id, 'suggestion_id': body.suggestion_id}
        identity = digest([project_id, 'follow-up-accept', body.client_request_id])
        request_hash = digest([plan_id, body.model_dump(mode='json')])
        with (nullcontext(_connection) if _connection is not None else self.repo.db.transaction()) as conn:
            old = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='follow_up_receipt'"),
                               {'id': identity, 'project': project_id}).mappings().first()
            if old:
                receipt = json.loads(old['data'])
                if digest(receipt) != old['digest'] or receipt['request_hash'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return CommerceDraftService._read(conn, project_id, receipt['draft_id'])
            suggestion = next((item for item in self._suggestions(conn, project_id, plan_id)
                               if item.id == body.suggestion_id and item.review_digest == body.review_digest), None)
            if suggestion is None:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            provenance['source_plan_revision'] = suggestion.source_plan_revision
            draft = CommerceDraftService(self.repo, self.workflows).create(project_id,
                TaskDraftInput(kind=suggestion.kind, title=suggestion.title, prompt=suggestion.prompt,
                    expected_project_revision=suggestion.project_revision,
                    client_request_id='follow-up:' + digest([project_id, plan_id, suggestion.id, suggestion.review_digest])),
                _connection=conn, provenance=provenance)
            from muse.commerce.code_integration import CommerceCodeIntegration
            CommerceCodeIntegration._save(conn, identity, project_id, plan_id, 'follow_up_receipt',
                                           {'request_hash': request_hash, 'draft_id': draft.id})
            return draft

    def accept_batch(self, project_id, plan_id, body):
        from muse.commerce.code_integration import CommerceCodeIntegration
        identity = digest([project_id, plan_id, 'follow-up-batch', body.client_request_id])
        request_hash = digest(body.model_dump(mode='json'))
        with self.repo.db.transaction() as conn:
            old = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='follow_up_batch_receipt'"), {'id': identity}).mappings().first()
            if old:
                saved = json.loads(old['data'])
                if digest(saved) != old['digest'] or saved['request_hash'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return [CommerceDraftService._read(conn, project_id, draft_id) for draft_id in saved['ids']]
            if len({item.suggestion_id for item in body.items}) != len(body.items):
                raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
            drafts = [self.accept(project_id, plan_id, FollowUpAccept(suggestion_id=item.suggestion_id,
                review_digest=item.review_digest, client_request_id=digest([identity, index])), _connection=conn)
                for index, item in enumerate(body.items)]
            CommerceCodeIntegration._save(conn, identity, project_id, plan_id, 'follow_up_batch_receipt',
                                          {'request_hash': request_hash, 'ids': [draft.id for draft in drafts]})
            return drafts
