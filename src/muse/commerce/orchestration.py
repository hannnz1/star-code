"""Durable preparation team, using the existing task/delegation transactions.

No WordPress writes or paid requests happen in this service itself. The current
developer step submits a structured proposal; P6 must supply real isolated code.
"""
import json
import time
from contextlib import nullcontext

from pydantic import ValidationError
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    CommercePlan,
    CommerceStep,
    Contract,
    ProductDraft,
    SiteBlueprint,
)
from muse.commerce.planning import provider_identity
from muse.commerce.repository import digest, encode
from muse.commerce.roles import (
    DELEGATION_CEILING,
    ROLE_TOOLS,
    prompt_from_snapshot,
    role_snapshot,
)
from muse.commerce.site import build_site_blueprint
from muse.contracts import TERMINAL, TaskRequest


class Submission(Contract):
    candidate: object


class CommerceWorkflowService:
    def __init__(self, repository, settings):
        self.repo, self.runtime, self.settings = repository, repository.runtime, settings

    @staticmethod
    def _persist(conn, plan):
        plan = plan.model_copy(update={'revision': plan.revision + 1})
        conn.execute(text('UPDATE commerce_plans SET revision=:revision,data=:data WHERE id=:id'),
                     {'id': plan.id, 'revision': plan.revision, 'data': encode(plan)})
        for step in plan.steps:
            conn.execute(text('UPDATE commerce_steps SET task_id=:task,revision=:revision,data=:data WHERE id=:id'),
                         {'id': step.id, 'task': step.task_id, 'revision': plan.revision, 'data': encode(step)})
        return plan

    def create_workflow(self, project_id, kind, prompt, request_id, expected_revision, *, max_requests=20, import_id=None, theme_source_id=None, _connection=None, repair_context=None):
        if (kind not in {'build_site', 'launch_products'} or not isinstance(prompt, str) or not 1 <= len(prompt) <= 10000
                or (theme_source_id is not None and (not isinstance(theme_source_id, str) or not 1 <= len(theme_source_id) <= 200))
                or isinstance(max_requests, bool) or not isinstance(max_requests, int) or not 1 <= max_requests <= 100):
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
        if self.settings.provider is None:
            raise CommerceFailure('MODEL_UNAVAILABLE', 503, project_id=project_id)
        identity = digest([project_id, 'workflow', request_id])
        request_parts = [project_id, kind, prompt, expected_revision, max_requests, import_id]
        if theme_source_id is not None:
            request_parts.append(theme_source_id)
        if repair_context is not None:
            request_parts.append(digest(repair_context))
        request_hash = digest(request_parts)
        with self.repo.db.transaction() if _connection is None else nullcontext(_connection) as conn:
            old = conn.execute(text('SELECT data,request_digest FROM commerce_plans WHERE id=:id'), {'id': identity}).mappings().first()
            if old:
                if old['request_digest'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return CommercePlan.model_validate_json(old['data'])
            project = self.repo._project(conn, project_id, expected_revision)
            context = self.repo._context(conn, project, 'staging')
            if context is None:
                raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503, project_id=project_id)
            products = []
            if kind == 'launch_products' or import_id is not None:
                from muse.commerce.models import ImportedProducts
                record = conn.execute(text("SELECT data FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='product_import'"),
                                      {'id': import_id, 'project': project_id}).scalar()
                if not record:
                    raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
                source = ImportedProducts.model_validate_json(record)
                if source.project_revision != expected_revision:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                products = source.result.drafts
            blueprint = build_site_blueprint(project.brief, context.snapshot)
            if kind == 'launch_products' and theme_source_id is None:
                from muse.commerce.retained_storefront import retain_published_storefront
                retained = retain_published_storefront(conn, self.repo, project, context.snapshot)
                if retained is not None:
                    blueprint, theme_source_id = retained
            if kind == 'build_site':
                draft = self.repo.current_site_draft(conn, project_id)
                if draft is not None:
                    blueprint.pages = [page.model_copy(deep=True) for page in draft.blueprint.pages]
                    blueprint.navigation = [item.model_copy(deep=True) for item in draft.blueprint.navigation]
                    if 'shipping_rules' in draft.blueprint.required_settings:
                        from muse.commerce.shipping_rules import ShippingRules
                        shipping = ShippingRules.model_validate(draft.blueprint.required_settings['shipping_rules'])
                        if shipping.currency != project.brief.currency:
                            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                        blueprint.required_settings['shipping_rules'] = shipping.model_dump(mode='json')
                        blueprint.required_settings['missing_fields'] = [field for field in blueprint.required_settings['missing_fields'] if field != 'shipping_confirmed']
                    if 'category_navigation' in draft.blueprint.required_settings:
                        from muse.commerce.category_navigation import CategoryNavigation, validate_category_source
                        navigation = CategoryNavigation.model_validate(draft.blueprint.required_settings['category_navigation'])
                        validate_category_source(conn, project, navigation)
                        if navigation.items and (navigation.import_id != import_id or
                            any(item.category not in {product.category for product in products} for item in navigation.items)):
                            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
                        blueprint.required_settings['category_navigation'] = navigation.model_dump(mode='json')

            if kind == 'build_site':
                from muse.commerce.design_repository import DesignRepository
                design = DesignRepository.read(conn, project_id)
                if design is not None:
                    draft = self.repo.current_site_draft(conn, project_id)
                    if (design.project_revision != expected_revision or draft is None
                        or design.blueprint_plan_id != draft.id or design.blueprint_revision != draft.revision):
                        raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                    blueprint.required_settings['store_design'] = design.model_dump(mode='json')
                    blueprint.design_tokens.update(design.theme_tokens.model_dump(mode='json'))
                    from muse.commerce.design_resources import design_media_refs,owned_image_path
                    from muse.commerce.media import MediaRepository
                    paths={}
                    for ref in design_media_refs(blueprint):
                        record,_=MediaRepository._read(conn,project_id,ref)
                        paths[ref]=owned_image_path(project_id,record.image.sha256,record.image.mime_type)
                    blueprint.required_settings['design_media_urls']=paths
                    from muse.commerce.code_integration import CommerceCodeIntegration
                    head=CommerceCodeIntegration.head(conn,project_id)
                    if theme_source_id is not None and (head is None or theme_source_id!=head.source_id):
                        raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                    if head is not None:
                        from muse.commerce.design_code_merge import merge_design_source
                        theme_source_id=merge_design_source(conn,self.repo,blueprint,products,head)
                        blueprint.required_settings['local_code_base_revision']=head.revision
            if theme_source_id is None:
                from muse.commerce.code_integration import CommerceCodeIntegration
                head = CommerceCodeIntegration.head(conn, project_id)
                if head is not None:
                    theme_source_id = head.source_id
                    blueprint.required_settings['local_code_base_revision'] = head.revision
            if theme_source_id is not None:
                from muse.commerce.restore import ProjectRestorer
                _, source_digest = ProjectRestorer._theme_source(conn, project_id, theme_source_id)
                blueprint.required_settings['restored_theme_source'] = {'id': theme_source_id, 'digest': source_digest}
            if repair_context is not None:
                from muse.commerce.code_integration import CommerceCodeIntegration
                repair_id = digest([identity, 'conflict-repair-context'])
                blueprint.required_settings['repair_context'] = {'id': repair_id, 'digest': digest(repair_context),
                    'files': sorted(repair_context['conflicts']), 'source_plan_id': repair_context['source_plan_id']}
            roles = role_snapshot()
            manager = CommerceStep(id=identity + ':manager', role='store_manager')
            steps = [manager, CommerceStep(id=identity + ':content', role='product_content', dependencies=[manager.id]),
                     CommerceStep(id=identity + ':website', role='site_developer', dependencies=[manager.id])]
            plan = CommercePlan(id=identity, project_id=project_id, kind=kind, blueprint=blueprint,
                                products=products, snapshot_hash=context.snapshot_hash, steps=steps,
                                content_hash=digest({'blueprint': blueprint.model_dump(mode='json'), 'products': [p.model_dump(mode='json') for p in products]}))
            root = None
            binding = {'plan_id': plan.id, 'project_id': project_id, 'step_id': manager.id,
                       'project_revision': expected_revision, 'provider_hash': provider_identity(self.settings),
                       'task_goal': prompt}
            if blueprint.required_settings.get('missing_fields'):
                plan.state, plan.error_code = 'NEEDS_INPUT', 'FACTS_INCOMPLETE'
            else:
                root = self.runtime.create(TaskRequest(prompt=prompt_from_snapshot({'commerce': roles}, 'store_manager', prompt),
                    workspace_id=project.workspace_id, scenario='coding', client_request_id='commerce:' + identity),
                    initial_checkpoint={'commerce': binding, 'role': 'store_manager', 'allowed_tools': DELEGATION_CEILING,
                                        'max_local_turns': max_requests, 'commerce_role_snapshot': roles}, _connection=conn)
                manager.task_id = root.id
            conn.execute(text('INSERT INTO commerce_plans VALUES(:id,:project,:request,:digest,1,:data,:root)'),
                         {'id': plan.id, 'project': project_id, 'request': 'commerce:' + identity, 'digest': request_hash,
                          'data': encode(plan), 'root': root.id if root else None})
            if repair_context is not None:
                CommerceCodeIntegration._save(conn, repair_id, project_id, identity, 'conflict_repair_context', repair_context)
            for step in steps:
                conn.execute(text('INSERT INTO commerce_steps VALUES(:id,:plan,:task,1,:data)'),
                             {'id': step.id, 'plan': plan.id, 'task': step.task_id, 'data': encode(step)})
            if root:
                conn.execute(text('INSERT INTO execution_budgets(root_id,max_turns,max_tool_calls,max_active_seconds,model_requests) VALUES(:root,:turns,:tools,:seconds,0)'),
                             {'root': root.id, 'turns': min(max_requests, self.settings.max_turns),
                              'tools': self.settings.max_tool_calls, 'seconds': self.settings.max_active_seconds})
            self.repo.event(conn, project_id, 'workflow_created', {'plan_id': plan.id, 'root_task_id': root.id if root else None,
                           'snapshot_hash': plan.snapshot_hash, 'max_requests': min(max_requests, self.settings.max_turns)})
            return plan

    def _actor(self, conn, ctx):
        row = self.runtime._lease(conn, ctx.task_id, ctx.owner, ctx.epoch, time.time())
        binding = json.loads(row['checkpoint']).get('commerce', {})
        data = conn.execute(text('SELECT * FROM commerce_plans WHERE id=:id'), {'id': binding.get('plan_id')}).mappings().first()
        if not data:
            raise CommerceFailure('PERMISSION_DENIED', 403)
        plan = CommercePlan.model_validate_json(data['data'])
        step = next((s for s in plan.steps if s.id == binding.get('step_id') and s.task_id == ctx.task_id), None)
        project = self.repo._project(conn, plan.project_id)
        root = self.runtime._task(conn, data['root_task_id'])
        if (step is None or binding.get('project_id') != project.id or project.revision != binding.get('project_revision')
                or plan.state in {'STALE', 'FAILED', 'CANCELLED', 'SUCCEEDED'} or root['cancel_requested'] or row['cancel_requested']):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
        return plan, step, data['root_task_id']

    def _receipt(self, conn, ctx, call_id, *, error_code=None):
        if call_id is None:
            return
        from muse.commerce.recovery import save_managed_receipt
        save_managed_receipt(conn, ctx, call_id, error_code=error_code)

    def dispatch_step(self, ctx, step_id, *, call_id=None):
        with self.repo.db.transaction() as conn:
            plan, manager, root_id = self._actor(conn, ctx)
            step = next((s for s in plan.steps if s.id == step_id and s.role != 'store_manager'), None)
            if manager.role != 'store_manager' or step is None:
                raise CommerceFailure('PERMISSION_DENIED', 403, project_id=plan.project_id)
            if any(next(s for s in plan.steps if s.id == dependency).status != 'SUCCEEDED' for dependency in step.dependencies):
                raise CommerceFailure('FACTS_INCOMPLETE', project_id=plan.project_id)
            binding = {**ctx.cp['commerce'], 'step_id': step.id}
            prompt = 'Plan: ' + plan.id + '. Prepare the ' + step.role + ' proposal; read_commerce_context supplies frozen data.'
            role_prompt = prompt_from_snapshot(ctx.cp['role_snapshot'], step.role, prompt)
            child = self.runtime.spawn_child(root_id, ctx.owner, ctx.epoch, 'commerce-step:' + step.id, role_prompt,
                capabilities={'role': step.role, 'allowed_tools': sorted(ROLE_TOOLS[step.role]),
                              'max_local_turns': 12, 'commerce': binding}, _connection=conn)
            if step.task_id != child.id:
                step.task_id, step.status = child.id, 'RUNNING'
                self._persist(conn, plan)
                self.repo.event(conn, plan.project_id, 'commerce_step_dispatched', {'plan_id': plan.id, 'step_id': step.id, 'task_id': child.id})
            self._receipt(conn, ctx, call_id)
            return child

    def _invalid(self, conn, plan, step, root_id, ctx, args, call_id):
        identity = digest([plan.id, step.id, 'invalid', call_id])
        old = conn.execute(text('SELECT digest FROM commerce_artifacts WHERE id=:id'), {'id': identity}).scalar()
        args_hash = digest(args)
        if old is None:
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'invalid_submission',:digest,'{}')"),
                         {'id': identity, 'project': plan.project_id, 'plan': plan.id, 'digest': args_hash})
            if step.correction_attempts == 0:
                step.correction_attempts = 1
            else:
                step.status, plan.state, plan.error_code = 'FAILED', 'FAILED', 'MODEL_OUTPUT_INVALID'
                root = self.runtime._task(conn, root_id)
                self.runtime._cancel_descendants(conn, root_id, time.time())
                self.runtime._state(conn, root_id, 'RUNNING' if root['status'] == 'RUNNING' else 'CANCELLED', time.time(), cancel_requested=1)
            self._persist(conn, plan)
            self.repo.event(conn, plan.project_id, 'structured_output_invalid', {'plan_id': plan.id, 'step_id': step.id,
                                                                            'correction_attempts': step.correction_attempts})
        elif old != args_hash:
            return CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
        self._receipt(conn, ctx, call_id, error_code='MODEL_OUTPUT_INVALID')
        return CommerceFailure('MODEL_OUTPUT_INVALID', 422, project_id=plan.project_id)

    def submit(self, ctx, kind, args, call_id):
        failure = None
        proposal_replayed = False
        with self.repo.db.transaction() as conn:
            plan, step, root_id = self._actor(conn, ctx)
            if ((kind == 'blueprint' and step.role not in {'store_manager', 'site_developer'})
                    or (kind == 'products' and step.role != 'product_content') or kind not in {'blueprint', 'products'}):
                raise CommerceFailure('PERMISSION_DENIED', 403, project_id=plan.project_id)
            try:
                value = Submission.model_validate(args).candidate
                if kind == 'blueprint':
                    candidate = SiteBlueprint.model_validate(value)
                    if candidate != plan.blueprint:
                        raise CommerceFailure('FACTS_INCOMPLETE', project_id=plan.project_id)
                    payload = candidate.model_dump(mode='json')
                else:
                    from muse.commerce.products import review_product_content
                    if not isinstance(value, list):
                        raise TypeError('Product list required')
                    if len(value) != len(plan.products):
                        raise CommerceFailure('FACTS_INCOMPLETE', project_id=plan.project_id)
                    candidates = [ProductDraft.model_validate(item) for item in value]
                    if any(review_product_content(source, candidate) for source, candidate in zip(plan.products, candidates, strict=True)):
                        from muse.commerce.content_proposals import (
                            ContentProposalRepository,
                        )
                        proposal_replayed = not ContentProposalRepository(self.repo).offer(conn, plan, candidates)
                        raise CommerceFailure('FACTS_INCOMPLETE', project_id=plan.project_id)
                    payload = [p.model_dump(mode='json') for p in candidates]
            except CommerceFailure as error:
                if error.public.code == 'RESOURCE_CONFLICT':
                    raise
                plan.state, plan.error_code = 'NEEDS_INPUT', error.public.code
                if not proposal_replayed:
                    self._persist(conn, plan)
                    self.repo.event(conn, plan.project_id, 'merchant_facts_required', {'plan_id': plan.id, 'step_id': step.id})
                failure = error
                self._receipt(conn, ctx, call_id, error_code=error.public.code)
            except (ValidationError, ValueError, TypeError):
                failure = self._invalid(conn, plan, step, root_id, ctx, args, call_id)
            else:
                output_hash = digest(payload)
                if step.output_hash and step.output_hash != output_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
                identity = digest([plan.id, step.id, 'output'])
                receipt = {'plan_id': plan.id, 'step_id': step.id, 'task_id': ctx.task_id, 'role': step.role,
                           'kind': kind, 'content_hash': output_hash, 'payload': payload}
                old = conn.execute(text('SELECT digest FROM commerce_artifacts WHERE id=:id'), {'id': identity}).scalar()
                if old and old != output_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
                if not old:
                    conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'commerce_output',:digest,:data)"),
                        {'id': identity, 'project': plan.project_id, 'plan': plan.id, 'digest': output_hash, 'data': encode(receipt)})
                    step.status, step.output_hash = 'SUCCEEDED', output_hash
                    self._persist(conn, plan)
                    self.repo.event(conn, plan.project_id, 'commerce_output_submitted', {key: receipt[key] for key in ('plan_id', 'step_id', 'task_id', 'role', 'content_hash')})
                self._receipt(conn, ctx, call_id)
                return receipt
        # Raise after commit so an invalid output cannot roll back its correction receipt.
        raise failure

    def request_review(self, ctx, *, call_id=None):
        with self.repo.db.transaction() as conn:
            plan, step, _ = self._actor(conn, ctx)
            if step.role != 'store_manager':
                raise CommerceFailure('PERMISSION_DENIED', 403, project_id=plan.project_id)
            if not all(s.status == 'SUCCEEDED' and s.output_hash for s in plan.steps):
                raise CommerceFailure('FACTS_INCOMPLETE', project_id=plan.project_id)
            for member in plan.steps:
                if member.role != 'store_manager' and self.runtime._task(conn, member.task_id)['status'] != 'SUCCEEDED':
                    raise CommerceFailure('FACTS_INCOMPLETE', project_id=plan.project_id)
                record = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='commerce_output'"),
                    {'id': digest([plan.id, member.id, 'output']), 'project': plan.project_id, 'plan': plan.id}).mappings().first()
                receipt = json.loads(record['data']) if record else {}
                if (not record or record['digest'] != member.output_hash or digest(receipt.get('payload')) != member.output_hash
                        or receipt.get('task_id') != member.task_id or receipt.get('step_id') != member.id):
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
            # P6 has not provided a real code package or verification. Never fake readiness.
            plan.state, plan.error_code = 'BLOCKED', 'VERIFICATION_UNAVAILABLE'
            saved = self._persist(conn, plan)
            self.repo.event(conn, plan.project_id, 'workflow_blocked', {'plan_id': plan.id, 'code': plan.error_code})
            self._receipt(conn, ctx, call_id)
            return saved

    def advance(self, plan_id, expected_revision):
        with self.repo.db.transaction() as conn:
            row = conn.execute(text('SELECT * FROM commerce_plans WHERE id=:id'), {'id': plan_id}).mappings().first()
            if not row:
                raise CommerceFailure('NOT_FOUND', 404)
            plan = CommercePlan.model_validate_json(row['data'])
            if plan.revision != expected_revision:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
            if not row['root_task_id']:
                return plan  # Missing facts/structure-only plans intentionally queue no model task.
            if plan.state in {'FAILED', 'CANCELLED', 'STALE', 'SUCCEEDED'}:
                return plan
            root = self.runtime._task(conn, row['root_task_id'])
            before = encode(plan)
            changed = False
            for step in plan.steps:
                if not step.task_id:
                    continue
                task = self.runtime._task(conn, step.task_id)
                if task['cancel_requested'] or task['status'] == 'CANCELLED':
                    step.status, plan.state, changed = 'CANCELLED', 'CANCELLED', True
                elif task['status'] == 'FAILED':
                    step.status, plan.state, changed = 'FAILED', 'FAILED', True
                    plan.error_code = 'BUDGET_EXHAUSTED' if 'budget' in task['error'].lower() else 'MODEL_OUTPUT_INVALID'
                elif task['status'] == 'INTERRUPTED':
                    plan.state, plan.error_code, changed = 'BLOCKED', 'MODEL_UNAVAILABLE', True
                elif task['status'] == 'RUNNING' and step.status == 'PENDING':
                    step.status, changed = 'RUNNING', True
                elif task['status'] == 'SUCCEEDED' and not step.output_hash:
                    step.status, plan.state, plan.error_code, changed = 'FAILED', 'FAILED', 'MODEL_OUTPUT_INVALID', True
            if root['status'] == 'SUCCEEDED' and any(s.status != 'SUCCEEDED' or not s.output_hash for s in plan.steps):
                plan.state, plan.error_code, changed = 'FAILED', 'MODEL_OUTPUT_INVALID', True
            if root['cancel_requested']:
                plan.state, changed = 'CANCELLED', True
            if plan.state == 'FAILED':
                self.runtime._cancel_descendants(conn, root['id'], time.time())
                if root['status'] not in TERMINAL:
                    self.runtime._state(conn, root['id'], 'RUNNING' if root['status'] == 'RUNNING' else 'CANCELLED',
                                        time.time(), cancel_requested=1)
                for member in plan.steps:
                    if member.status not in {'FAILED', 'SUCCEEDED'}:
                        member.status = 'CANCELLED'
            if changed and encode(plan) != before:
                return self._persist(conn, plan)
            return plan

    def resume(self, plan_id, expected_revision):
        with self.repo.db.transaction() as conn:
            row = conn.execute(text('SELECT * FROM commerce_plans WHERE id=:id'), {'id': plan_id}).mappings().first()
            if not row:
                raise CommerceFailure('NOT_FOUND', 404)
            plan = CommercePlan.model_validate_json(row['data'])
            if plan.revision != expected_revision or plan.state != 'BLOCKED' or plan.error_code != 'MODEL_UNAVAILABLE':
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
            project = self.repo._project(conn, plan.project_id)
            for step in plan.steps:
                if not step.task_id:
                    continue
                task = self.runtime._task(conn, step.task_id)
                cp = json.loads(task['checkpoint'])
                binding = cp['commerce']
                if project.revision != binding['project_revision'] or binding['provider_hash'] != provider_identity(self.settings):
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
                if task['status'] == 'INTERRUPTED':
                    if conn.execute(text("SELECT id FROM tool_calls WHERE task_id=:id AND status='UNKNOWN'"), {'id': task['id']}).first():
                        raise CommerceFailure('WRITE_OUTCOME_UNKNOWN', project_id=plan.project_id)
                    cp.pop('pending_failure', None)
                    conn.execute(text('UPDATE tasks SET checkpoint=:cp WHERE id=:id'), {'id': task['id'], 'cp': encode(cp)})
                    self.runtime._state(conn, task['id'], 'QUEUED', time.time(), pause_requested=0, lease_owner=None, lease_until=None)
            plan.state, plan.error_code = 'PLANNING', None
            return self._persist(conn, plan)
