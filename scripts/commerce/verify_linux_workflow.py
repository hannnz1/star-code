"""Real six-stage merchant workflow against disposable Linux stores only.

Role preparation uses deterministic synthetic inputs, not an LLM. Verification,
browser, purchase, approvals and publication use production implementations.
The test approval is never evidence of a human merchant's acceptance.
"""
import argparse
import asyncio
import io
import json
import platform
import time
from pathlib import Path

from PIL import Image

from muse.commerce.code_bridge import ThemeCodeBridge
from muse.commerce.context import normalize_snapshot
from muse.commerce.media import MediaRepository
from muse.commerce.models import EnvironmentRef, PlatformCapabilities, SiteBrief
from muse.commerce.orchestration import CommerceWorkflowService
from muse.commerce.reference_environment import load_reference_assets
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.reference_runner import DockerReferenceRunner
from muse.commerce.repository import CommerceRepository
from muse.commerce_connector.reference_service import ReferenceEnvironmentService
from muse.commerce_connector.runtime import (
    create_publication_service,
    create_verification_service,
)
from muse.commerce_connector.wordpress import WordPressReader
from muse.config import ProviderSettings, load_settings
from muse.tasks.repository import TaskRepository
from muse.tools.context import ExecutionContext


class DiagnosticHandler:
    """Observe failures without removing the producer's readback interface."""
    def __init__(self, handler, phase, record):
        self.handler, self.phase, self.record = handler, phase, record

    def __getattr__(self, name):
        return getattr(self.handler, name)

    async def __call__(self, *args, **kwargs):
        try:
            return await self.handler(*args, **kwargs)
        except (Exception, asyncio.CancelledError) as error:
            import traceback
            self.record({'phase': self.phase, 'type': type(error).__name__,
                'code': getattr(getattr(error, 'public', None), 'code', None),
                'frames': [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                    for f in traceback.extract_tb(error.__traceback__)]})
            raise


def prepare_roles(service, tasks, settings, plan, *, theme_edits=None):
    manager = tasks.claim_next('acceptance-manager', ttl=1800)
    ctx = ExecutionContext(settings, tasks, manager, 'acceptance-manager', enforce_budgets=True)
    service.submit(ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'manager-output')
    for role in ('product_content', 'site_developer'):
        current = service.repo.get_plan(plan.id, project_id=plan.project_id)
        step = next(item for item in current.steps if item.role == role)
        service.dispatch_step(ctx, step.id)
        child = tasks.claim_next('acceptance-' + role, ttl=1800)
        child_ctx = ExecutionContext(settings, tasks, child, 'acceptance-' + role, enforce_budgets=True)
        if role == 'product_content':
            service.submit(child_ctx, 'products', {'candidate': [p.model_dump(mode='json') for p in plan.products]}, 'products-output')
        else:
            bridge = ThemeCodeBridge(child_ctx)
            draft = bridge.read('style.css')
            if theme_edits:
                for name, extra in theme_edits.items():
                    draft = bridge.read(name)
                    draft = bridge.write(name, draft['content'] + extra, draft['draft_hash'])
            bridge.seal(draft['draft_hash'])
            service.submit(child_ctx, 'blueprint', {'candidate': plan.blueprint.model_dump(mode='json')}, 'developer-output')
        tasks.finish(child.id, child_ctx.owner, child_ctx.epoch, 'SUCCEEDED', result='Deterministic acceptance preparation')
    service.request_review(ctx)
    tasks.finish(manager.id, ctx.owner, ctx.epoch, 'SUCCEEDED', result='Preparation only; independent verification required')
    return service.repo.get_plan(plan.id, project_id=plan.project_id)


def record_flow_progress(evidence, value):
    # Overall success is written only after every requested flow completes.
    if value.get('kind') != evidence.get('kind'):
        for key in ('kind', 'plan_id', 'verification_id', 'phases', 'state', 'error_code', 'active_phase',
                    'phase_timings', 'review_digest', 'review_checks', 'approval_source', 'publication_phase',
                    'completed_steps', 'total_steps', 'final_facts_pass'):
            evidence.pop(key, None)
    evidence.update({key: item for key, item in value.items() if key != 'passed'})


async def complete_flow(verifier, publication, repo, reader, plan, progress, *, sku, price, stock):
    result = {'kind': plan.kind, 'plan_id': plan.id}
    job = verifier.reserve(plan.project_id, plan.id, plan.revision, 'full-verification-' + plan.id)
    result['verification_id'] = job.id
    for _ in range(7):
        started = time.monotonic()
        await verifier.run_once(plan.project_id)
        status = verifier.read(plan.project_id, job.id)
        result.setdefault('phase_timings', []).append({'phase': status.phase or status.completed_phases[-1],
            'completed': list(status.completed_phases), 'seconds': round(time.monotonic() - started, 3)})
        result.update(phases=status.completed_phases, state=status.state, error_code=status.error_code,
                      active_phase=status.phase)
        progress(result)
        if status.state == 'REVIEW_REQUIRED':
            break
        if status.state == 'NEEDS_RECONCILIATION':
            raise ValueError('Verification needs read-only reconciliation')
    if verifier.read(plan.project_id, job.id).state != 'REVIEW_REQUIRED':
        raise ValueError('Independent verification did not produce a review')
    plan = repo.get_plan(plan.id, project_id=plan.project_id)
    review = publication.reviews.latest(plan.project_id, plan.id, plan.revision)
    result.update(review_digest=review.intent_digest, review_checks=review.checks,
                  approval_source='explicit synthetic test authorizer, not human merchant')
    progress(result)
    review = publication.reviews.approve(plan.project_id, plan.id, review.intent_digest, review.plan_revision)
    for _ in range(review.total_steps):
        review = await publication.execute(plan.project_id, plan.id, review.intent_digest,
                                          review.plan_revision, reconcile_only=False)
        result.update(publication_phase=review.phase, completed_steps=review.completed_steps, total_steps=review.total_steps)
        progress(result)
    final = normalize_snapshot(await reader.read('snapshot', remaining_seconds=30), plan.project_id, 'staging')
    products = [item for item in final.products if item['sku'] == sku]
    result['final_facts_pass'] = (len(products) == 1 and products[0]['price'] == price
        and products[0]['stock_quantity'] == stock and products[0]['status'] == 'publish')
    if plan.blueprint.required_settings.get('store_design'):
        from muse.commerce.code_bridge import load_captured_code
        # Publication changes the persisted plan. Keep the strict source reader's
        # equality check and read its current revision before verifying files.
        code = load_captured_code(repo, repo.get_plan(plan.id, project_id=plan.project_id))
        expected = {item['path']:item['sha256'] for item in code.package.files_manifest}
        result['design_source_readback'] = final.theme_identity.get('files_sha256') == expected
        result['final_facts_pass'] &= result['design_source_readback']
    result['passed'] = review.phase == 'SUCCEEDED' and result['final_facts_pass']
    progress(result)
    if not result['passed']:
        raise ValueError('Publication/readback acceptance failed')
    return result


async def verify(args):
    if platform.system() != 'Linux' or args.root.exists():
        raise ValueError('A new private Linux acceptance directory is required')
    args.root.mkdir(mode=0o700, parents=True)
    settings = load_settings(data_dir=args.root / 'state', require_provider=False).model_copy(update={
        'provider': ProviderSettings(base_url='https://example.invalid/v1', model='synthetic-preparation',
                                     api_key='not-a-provider-credential'),
        'memory_auto_extract': False, 'memory_auto_consolidate': False})
    tasks = TaskRepository(settings.data_dir / 'state.sqlite3')
    repo = CommerceRepository(tasks)
    jobs = ReferenceJobRepository(repo)
    lock = json.loads(args.lock.read_text())
    bundle = load_reference_assets(lock, args.woocommerce)
    private = args.root / 'private'
    private.mkdir(mode=0o700)
    runner = DockerReferenceRunner(jobs, private, lock)
    reference = ReferenceEnvironmentService(jobs, runner, bundle, ports=(args.port, args.port + 1, args.port + 2))
    evidence = {'scope': 'disposable Linux merchant workflow', 'paid_api_calls': 0, 'passed': False,
                'human_acceptance': False, 'production_verified': False, 'phases': [], 'resources': []}
    def save():
        (args.root / 'evidence.json').write_text(json.dumps(evidence, indent=2))
    verifier = None
    try:
        space = args.root / 'workspace'
        space.mkdir()
        project = repo.create_project(tasks.register_workspace(str(space))['id'], SiteBrief(
            brand_name='Linux Acceptance Shop', language='en-US', currency='USD',
            merchant_supplied_policies={'shipping': 'Ship in 3 days', 'returns': 'Return in 14 days',
                                        'privacy': 'Synthetic test privacy policy'}), 'acceptance-project')
        target = reference.reserve(project.id, project.revision, 'disposable-target')
        evidence['resources'].append({'job_id': target.id, 'project_id': project.id})
        save()
        await reference.execute(project.id, target.id, target.revision, 'provision')
        connection = reference.resolve_connection('ref-' + target.id, project.id)
        project = repo.attach_connection(project.id, EnvironmentRef(id='target', project_id=project.id,
            environment='staging', connector_ref=connection.connection_id, public_url=connection.base_url), 'target-bind', project.revision)
        reader = WordPressReader(connection)
        snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=30), project.id, 'staging')
        capabilities = PlatformCapabilities.model_validate(await reader.read('capabilities', remaining_seconds=30))
        repo.save_context(project.id, connection.connection_id, snapshot, capabilities, project.revision)
        project = repo.get_project(project.id)
        pixels = io.BytesIO()
        Image.new('RGB', (40, 40), '#5b4b91').save(pixels, format='PNG')
        media = MediaRepository(repo).upload(project.id, 'cup.png', 'image/png', pixels.getvalue(), 'cup-image', project.revision)
        batch = repo.import_products(project.id,
            'sku,name,price,currency,stock,category,description,image_names\nLINUX-CUP,Cup,12.30,USD,4,' + ('Cups' if args.store_configuration else '') + ',Ceramic cup,cup.png\n',
            'product-batch', project.revision, media_ids=[media.id])
        if args.design_editor:
            from muse.commerce.design_repository import DesignRepository
            designs = DesignRepository(repo)
            document = designs.get_or_create(project.id, project.revision)
            document.home_sections[0].props.title = 'Crew edited storefront'
            document.home_sections[0].props.text = 'Versioned merchant content'
            document.home_sections[0].props.media_id = media.id
            document.home_sections[0].props.alt = 'Synthetic cup image'
            document.theme_tokens.font = 'serif'
            document = designs.save(project.id, project.revision, document.revision, 'design-test-save', document)
            evidence['design_revision'] = document.revision
        if args.store_configuration:
            from muse.commerce.shipping_drafts import ShippingDraftRepository
            from muse.commerce.shipping_rules import ShippingRules
            from muse.commerce.category_navigation import CategoryNavigation
            drafts = ShippingDraftRepository(repo)
            source = drafts.get(project.id) or repo.create_site_blueprint(project.id, 'configuration-source', project.revision)
            source = drafts.save_source(project.id, project.revision, source.id, source.revision, 'category-source',
                'category_navigation', CategoryNavigation(import_id=batch.id, items=[{'category':'Cups','label':'Shop cups'}]))
            source = drafts.save(project.id, project.revision, source.id, source.revision, 'shipping-source',
                ShippingRules(currency='USD', zones=[{'key':'us','name':'United States','countries':['US'],
                    'rate':'6.00','free_from':'24.60'}]))
            evidence['configuration_source_revision'] = source.revision
        service = CommerceWorkflowService(repo, settings)
        plan = service.create_workflow(project.id, 'build_site', 'Build the synthetic shop', 'build-workflow',
                                       project.revision, import_id=batch.id, max_requests=8)
        plan = prepare_roles(service, tasks, settings, plan)
        verifier = create_verification_service({connection.connection_id: connection}, reference)
        if args.design_editor:
            import muse.commerce.readback_verification_stage as readback_stage
            original_capture = readback_stage.capture_staging_preview
            async def diagnosed_capture(plan, *capture_args, **capture_kwargs):
                capture = await original_capture(plan, *capture_args, **capture_kwargs)
                evidence.setdefault('browser_captures', []).append({
                    'plan_id':plan.id, 'checks':capture.checks,
                    'diagnostics':list(capture.diagnostics), 'frame_count':len(capture.frames),
                    'passed':capture.passed})
                save()
                return capture
            readback_stage.capture_staging_preview = diagnosed_capture
            # Keep public, bounded diagnostics for all late verification stages;
            # frames only, never exception messages or connection credentials.
            def record_failure(value):
                evidence['stage_failure'] = value
                save()
            for phase in ('staging','source_capture','browser','facts'):
                verifier.runtime.worker.handlers[phase] = DiagnosticHandler(
                    verifier.runtime.worker.handlers[phase], phase, record_failure)
            verifier.verifier.request_review = DiagnosticHandler(
                verifier.verifier.request_review, 'report', record_failure)
        publication_private = args.root / 'publication-private'
        publication_private.mkdir(mode=0o700)
        secret = runner._read_private(jobs.read(project.id, target.id), 'connection.json')['execution_secret'].encode()
        publication = create_publication_service({connection.connection_id: connection},
            {connection.connection_id: secret}, runtime_database=settings.data_dir / 'state.sqlite3',
            private_directory=publication_private, versions_lock=lock)
        def progress(value):
            record_flow_progress(evidence, value)
            save()
        evidence['project_id'] = project.id
        evidence['flows'] = [await complete_flow(verifier, publication, repo, reader, plan, progress,
            sku='LINUX-CUP', price='12.30', stock=4)]
        if args.store_configuration:
            import httpx
            final = normalize_snapshot(await reader.read('snapshot', remaining_seconds=30), project.id, 'staging')
            product = next(item for item in final.products if item['sku'] == 'LINUX-CUP')
            category = next(item for item in product['categories'] if item['name'] == 'Cups')
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(category['url'])
                response.raise_for_status()
                evidence['category_destination_pass'] = response.status_code == 200 and 'Cup' in response.text
                quotes = []
                for quantity, expected in [(1,'600'),(2,'0'),(3,'0')]:
                    async with httpx.AsyncClient(timeout=30) as buyer:
                        base = connection.base_url + '/wp-json/wc/store/v1'
                        cart = await buyer.get(base+'/cart')
                        cart.raise_for_status()
                        headers = {'Cart-Token': cart.headers['Cart-Token']}
                        add = await buyer.post(base+'/cart/add-item', headers=headers,
                            json={'id':product['id'],'quantity':quantity})
                        add.raise_for_status()
                        addressed = await buyer.post(base+'/cart/update-customer', headers=headers,
                            json={'shipping_address':{'country':'US','state':'CA','postcode':'90210','city':'Beverly Hills'}})
                        addressed.raise_for_status()
                        rates = addressed.json()['shipping_rates'][0]['shipping_rates']
                        expected_kind = 'flat_rate' if quantity == 1 else 'free_shipping'
                        passed = len(rates)==1 and rates[0]['method_id']==expected_kind and rates[0]['price']==expected
                        quotes.append({'quantity':quantity,'expected_minor_units':expected,'passed':passed})
                evidence['shipping_cart_boundaries'] = quotes
                save()
                if not evidence['category_destination_pass'] or not all(item['passed'] for item in quotes):
                    raise ValueError('Category destination or actual cart shipping differs')
        if args.launch_after_build:
            project = repo.get_project(project.id)
            current = normalize_snapshot(await reader.read('snapshot', remaining_seconds=30), project.id, 'staging')
            previous_theme = current.theme_identity['files_sha256']
            repo.save_context(project.id, connection.connection_id, current, capabilities, project.revision)
            project = repo.get_project(project.id)
            new_pixels = io.BytesIO()
            Image.new('RGB', (40, 40), '#345f91').save(new_pixels, format='PNG')
            new_media = MediaRepository(repo).upload(project.id, 'new-cup.png', 'image/png', new_pixels.getvalue(),
                                                   'new-cup-image', project.revision)
            batch = repo.import_products(project.id,
                'sku,name,price,currency,stock,category,description,image_names\nLINUX-NEW-CUP,New Cup,14.50,USD,5,,New ceramic cup,new-cup.png\n',
                'launch-batch', project.revision, media_ids=[new_media.id])
            launch = service.create_workflow(project.id, 'launch_products', 'Launch the confirmed new cup',
                'launch-workflow', project.revision, import_id=batch.id, max_requests=8)
            launch = prepare_roles(service, tasks, settings, launch)
            evidence['flows'].append(await complete_flow(verifier, publication, repo, reader, launch, progress,
                sku='LINUX-NEW-CUP', price='14.50', stock=5))
            if args.design_editor:
                after_launch = normalize_snapshot(await reader.read('snapshot', remaining_seconds=30), project.id, 'staging')
                evidence['launch_retains_design'] = after_launch.theme_identity['files_sha256'] == previous_theme
                if not evidence['launch_retains_design']:
                    raise ValueError('Product launch replaced the edited storefront')
            if args.store_configuration:
                previous_configuration=final.settings['shipping_configuration']
                actual=normalize_snapshot(await reader.read('snapshot',remaining_seconds=30),project.id,'staging')
                evidence['launch_retains_shipping']=actual.settings['shipping_configuration']==previous_configuration
                evidence['launch_retains_category_navigation']=actual.theme_identity['owned_navigation']==final.theme_identity['owned_navigation']
                evidence['merchant_has_no_preview_fixture']=not any(item['sku'].startswith('CREW-PREVIEW-CAT-') for item in actual.products)
                if not all(evidence[key] for key in ['launch_retains_shipping','launch_retains_category_navigation','merchant_has_no_preview_fixture']):
                    raise ValueError('New product launch changed existing configuration or leaked private fixtures')
        evidence['passed'] = all(item['passed'] for item in evidence['flows'])
        save()
    except Exception as error:
        evidence['passed'] = False
        evidence['failure_type'] = type(error).__name__
        evidence['failure_code'] = getattr(getattr(error, 'public', None), 'code', None)
        save()
        raise
    finally:
        if verifier is not None:
            verifier.host_lease.close()
        rows = jobs.db.rows("SELECT id,project_id FROM commerce_artifacts WHERE kind='reference_job'")
        for row in rows:
            current = jobs.read(row['project_id'], row['id'])
            cleaned = await runner.cleanup(current)
            evidence['resources'].append({'job_id': current.id, 'cleanup_state': cleaned.state})
            save()
    print(json.dumps({key: evidence.get(key) for key in ('passed', 'phases', 'completed_steps', 'final_facts_pass')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--woocommerce', type=Path, required=True)
    parser.add_argument('--launch-after-build', action='store_true')
    parser.add_argument('--design-editor', action='store_true')
    parser.add_argument('--store-configuration', action='store_true')
    parser.add_argument('--port', type=int, default=19681)
    asyncio.run(verify(parser.parse_args()))

