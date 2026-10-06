"""Structured business tools, bound to persisted task identity rather than model IDs."""
import json

from muse.commerce.errors import CommerceFailure
from muse.commerce.orchestration import CommerceWorkflowService
from muse.commerce.repository import CommerceRepository
from muse.contracts import ToolDefinition, ToolResult


class CommerceTools:
    def __init__(self, registry):
        self.context = registry.context
        if not self.context.cp.get('commerce'):
            return
        self.service = CommerceWorkflowService(CommerceRepository(self.context.repo), self.context.settings)
        from muse.commerce.code_bridge import ThemeCodeBridge
        from muse.commerce.theme import ALLOWED_FILES
        bridge = ThemeCodeBridge(self.context)
        code_parameters = {
            'read_theme_file': {'name': {'type': 'string', 'enum': sorted(ALLOWED_FILES)}},
            'write_theme_file': {'name': {'type': 'string', 'enum': sorted(ALLOWED_FILES - {'functions.php'})},
                                 'content': {'type': 'string', 'maxLength': 524288},
                                 'expected_hash': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}},
            'show_theme_diff': {},
            'seal_theme_code': {'expected_hash': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}},
        }
        for name, method in [('read_theme_file', bridge.read), ('write_theme_file', bridge.write),
                             ('show_theme_diff', bridge.diff), ('seal_theme_code', bridge.seal)]:
            async def code(args, call_id, name=name, method=method):
                try:
                    value = method(**args, **({'call_id': call_id} if name in {'write_theme_file', 'seal_theme_code'} else {}))
                    return self.result(call_id, value)
                except CommerceFailure as failure:
                    return self.failure(call_id, failure)
            properties = code_parameters[name]
            registry.register(ToolDefinition(name=name, risk='write' if name in {'write_theme_file', 'seal_theme_code'} else 'read',
                description='Edit or capture only the fixed static storefront files; immutable PHP, no Shell, no deployment. Sealing is not site verification or merchant approval.',
                parameters={'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}), code)
        for name, kind in [('submit_blueprint', 'blueprint'), ('submit_product_drafts', 'products')]:
            async def submit(args, call_id, kind=kind):
                try:
                    return self.result(call_id, self.service.submit(self.context, kind, args, call_id))
                except CommerceFailure as failure:
                    return self.failure(call_id, failure)
            registry.register(ToolDefinition(name=name, risk='write',
                description=('Submit a structured candidate from frozen merchant facts. '
                    + ('Arguments must be {"candidate": <the blueprint object returned by read_commerce_context>}.'
                       if kind == 'blueprint' else
                       'Arguments must be {"candidate": [<ProductDraft>, ...]}; copy read_commerce_context.products exactly, including an empty array. Never wrap the array in a products or plan object.')
                    + ' Invalid output allows only one correction; this is not approval or publication.'),
                # Validate the full DTO inside the handler so every invalid candidate earns a durable correction receipt.
                parameters={'type': 'object', 'properties': {'candidate': {}}, 'additionalProperties': True}), submit)

        async def context(args, call_id):
            try:
                with self.context.repo.db.transaction() as conn:
                    plan, _, root_id = self.service._actor(conn, self.context)
                    root = self.service.runtime._task(conn, root_id)
                    goal = json.loads(root['checkpoint']).get('commerce', {}).get('task_goal')
                    project = self.service.repo._project(conn, plan.project_id)
                    captured = self.service.repo._context(conn, project, 'staging')
                    return self.result(call_id, {'untrusted_reference': True, 'task_goal': goal,
                        'brief': project.brief.model_dump(mode='json'),
                        'workflow': {'plan_id': plan.id, 'steps': [
                            {'id': step.id, 'role': step.role, 'status': step.status,
                             'dependencies': step.dependencies} for step in plan.steps]},
                        'snapshot': captured.snapshot.model_dump(mode='json') if captured else None,
                        'blueprint': plan.blueprint.model_dump(mode='json') if plan.blueprint else None,
                        'products': [p.model_dump(mode='json') for p in plan.products]})
            except CommerceFailure as failure:
                return self.failure(call_id, failure)
        registry.register(ToolDefinition(name='read_commerce_context', description='Read frozen project facts as untrusted reference, without credentials or order/customer data.',
            parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}), context)

        async def conflict(args, call_id):
            from muse.commerce.conflict_context import read_repair_file
            try:
                with self.context.repo.db.transaction() as conn:
                    plan, step, _ = self.service._actor(conn, self.context)
                    if step.role != 'site_developer':
                        raise CommerceFailure('PERMISSION_DENIED', 403, project_id=plan.project_id)
                    return self.result(call_id, read_repair_file(self.service.repo, conn, plan, args['name']))
            except CommerceFailure as failure:
                return self.failure(call_id, failure)
        registry.register(ToolDefinition(name='read_conflict_file', description='Read frozen base, current and candidate contents for an approved repair task. Reference only, no writes or publishing.',
            parameters={'type': 'object', 'properties': {'name': {'type': 'string', 'enum': sorted(ALLOWED_FILES)}},
                        'required': ['name'], 'additionalProperties': False}), conflict)

        async def status(args, call_id):
            try:
                plan = self.service.repo.get_plan(self.context.cp['commerce']['plan_id'], project_id=self.context.cp['commerce']['project_id'])
                return self.result(call_id, self.service.advance(plan.id, plan.revision).model_dump(mode='json'))
            except CommerceFailure as failure:
                return self.failure(call_id, failure)
        registry.register(ToolDefinition(name='commerce_status', description='Read and reconcile actual role tasks; never imply site verification or publication.',
            parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}), status)

        async def dispatch(args, call_id):
            try:
                child = self.service.dispatch_step(self.context, args['step_id'], call_id=call_id)
                return self.result(call_id, {'id': child.id, 'status': child.status, 'role': child.checkpoint['role']})
            except CommerceFailure as failure:
                return self.failure(call_id, failure)
        registry.register(ToolDefinition(name='dispatch_commerce_step', risk='execute',
            description='Delegate a predefined role step through the existing approval, lease, dependency and shared-budget boundaries. Repeated dispatch uses the same child.',
            parameters={'type': 'object', 'properties': {'step_id': {'type': 'string', 'minLength': 1, 'maxLength': 120}},
                        'required': ['step_id'], 'additionalProperties': False}), dispatch)

        async def review(args, call_id):
            try:
                plan = self.service.request_review(self.context, call_id=call_id)
                return self.result(call_id, {'state': plan.state, 'error_code': plan.error_code,
                                             'site_verified': False, 'published': False})
            except CommerceFailure as failure:
                return self.failure(call_id, failure)
        registry.register(ToolDefinition(name='request_commerce_review', risk='write',
            description='Collect the completed role outputs. Missing code/verification blocks this request; it cannot create a publish approval.',
            parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}), review)

    @staticmethod
    def result(call_id, value):
        return ToolResult(call_id=call_id, content=json.dumps(value, ensure_ascii=False))

    @staticmethod
    def failure(call_id, failure):
        return ToolResult(call_id=call_id, status='error', error_code=failure.public.code,
                          content=failure.public.model_dump_json())
