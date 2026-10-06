import inspect
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field, model_validator

from muse.commerce.content_proposals import (
    ContentConfirmation,
    ContentProposal,
    ContentProposalRepository,
)
from muse.commerce.errors import CommerceErrorEnvelope
from muse.commerce.merchant_review import (
    MerchantReleaseReview,
    MerchantReviewRepository,
)
from muse.commerce.models import (
    BlueprintPage,
    NavigationItem,
    SiteBlueprint,
    CommercePlan,
    CommercePlanArchive,
    CommerceCodeHead,
    CodeIntegrationReview,
    CodeDisposition,
    CommercePlanLabel,
    CommerceTaskDraft,
    Contract,
    Environment,
    ImportedProducts,
    ProjectExport,
    ProjectMedia,
    RestoredProject,
    RestoredThemeSource,
    RestoredThemeSummary,
    SiteBrief,
    StoreContext,
    StorePreview,
    StorePreviewImage,
    StoreProject,
    ThemeCodeReview,
)
from muse.commerce.reference_jobs import ReferenceJob, ReferenceJobRepository
from muse.commerce.repository import CommerceRepository
from muse.commerce.task_drafts import CommerceDraftService
from muse.commerce.task_automation import ArmLocalApply, AutomationControl, LocalApplyAutomation, LocalApplyService
from muse.commerce.follow_up_models import ModelSuggestionInput, ModelSuggestionJob, ModelSuggestionService
from muse.commerce.follow_ups import FollowUpAccept, FollowUpBatch, FollowUpService, FollowUpSuggestion
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce.shipping_rules import ShippingRules
from muse.commerce.category_navigation import CategoryNavigation
from muse.commerce.verification_service import (
    VerificationStatus,
    VerificationStatusRepository,
)


class ProjectInput(Contract):
    workspace_id: str = Field(min_length=1, max_length=200)
    client_request_id: str = Field(min_length=1, max_length=200)
    brief: SiteBrief


class BriefUpdate(Contract):
    expected_revision: int = Field(ge=1)
    brief: SiteBrief


class ProjectLifecycleInput(Contract):
    expected_revision: int = Field(ge=1, strict=True)


class ProjectDeleteInput(ProjectLifecycleInput):
    confirmation_name: str = Field(min_length=1, max_length=200)


class ProductImportInput(Contract):
    expected_revision: int = Field(ge=1)
    client_request_id: str = Field(min_length=1, max_length=200)
    csv_text: str = Field(min_length=1, max_length=1024 * 1024)
    media_ids: list[str] = Field(default_factory=list, max_length=100)


class BlueprintInput(Contract):
    expected_revision: int = Field(ge=1)
    client_request_id: str = Field(min_length=1, max_length=200)


class ShippingDraftInput(Contract):
    expected_revision: int = Field(ge=1, strict=True)
    expected_plan_revision: int = Field(ge=1, strict=True)
    plan_id: str = Field(min_length=1, max_length=200)
    client_request_id: str = Field(min_length=1, max_length=200)
    rules: ShippingRules


class ShippingDraftQuoteInput(Contract):
    plan_id: str = Field(min_length=1, max_length=200)
    expected_plan_revision: int = Field(ge=1, strict=True)
    country: str = Field(pattern=r'^[A-Z]{2}$')
    subtotal: str = Field(pattern=r'^[0-9]{1,8}(?:\.[0-9]{1,2})?$')


class CategoryNavigationDraftInput(Contract):
    expected_revision: int = Field(ge=1, strict=True)
    expected_plan_revision: int = Field(ge=1, strict=True)
    plan_id: str = Field(min_length=1, max_length=200)
    client_request_id: str = Field(min_length=1, max_length=200)
    navigation: CategoryNavigation


class ShippingDraftQuote(Contract):
    served: bool
    amount: str | None
    currency: str


class BlueprintEditInput(Contract):
    expected_revision: int = Field(ge=1, strict=True)
    expected_plan_revision: int = Field(ge=1, strict=True)
    pages: list[BlueprintPage] = Field(min_length=7, max_length=7)
    navigation: list[NavigationItem] = Field(min_length=1, max_length=6)

    @model_validator(mode='after')
    def valid_structure(self):
        SiteBlueprint(pages=self.pages, navigation=self.navigation)
        slugs = {page.slug for page in self.pages if page.kind != 'product'}
        if any(item.slug not in slugs for item in self.navigation) or len({item.slug for item in self.navigation}) != len(self.navigation):
            raise ValueError('Navigation must reference distinct existing pages')
        if any(not page.title.strip() for page in self.pages) or any(not item.label.strip() for item in self.navigation):
            raise ValueError('Page titles and navigation labels cannot be blank')
        return self


class ConnectionInput(Contract):
    connection_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    expected_revision: int = Field(ge=1)
    client_request_id: str = Field(min_length=1, max_length=200)


class RefreshInput(Contract):
    environment: Environment
    expected_revision: int = Field(ge=1)


class WorkflowInput(Contract):
    kind: Literal['build_site', 'launch_products']
    prompt: str = Field(min_length=1, max_length=10000)
    expected_revision: int = Field(ge=1)
    client_request_id: str = Field(min_length=1, max_length=200)
    max_requests: int = Field(default=20, ge=1, le=100, strict=True)
    import_id: str | None = Field(default=None, min_length=1, max_length=200)
    theme_source_id: str | None = Field(default=None, min_length=1, max_length=200)


class TaskDraftInput(Contract):
    dependency_plan_ids: list[str] = Field(default_factory=list, max_length=20)
    kind: Literal['build_site', 'launch_products']
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=10000)
    expected_project_revision: int = Field(ge=1, strict=True)
    client_request_id: str = Field(min_length=1, max_length=200)
    max_requests: int = Field(default=20, ge=1, le=100, strict=True)
    import_id: str | None = Field(default=None, min_length=1, max_length=200)
    theme_source_id: str | None = Field(default=None, min_length=1, max_length=200)


class PlanArchiveItem(Contract):
    plan_id: str = Field(min_length=1, max_length=200)
    expected_plan_revision: int = Field(ge=1, strict=True)
    expected_revision: int = Field(ge=0, strict=True)


class PlanArchiveInput(Contract):
    items: list[PlanArchiveItem] = Field(min_length=1, max_length=50)
    archived: bool = Field(strict=True)


class CodeIntegrationInput(Contract):
    expected_plan_revision: int = Field(ge=1, strict=True)
    expected_head_revision: int = Field(ge=0, strict=True)
    review_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    client_request_id: str = Field(min_length=1, max_length=200)


class CodeDecisionInput(CodeIntegrationInput):
    dismissed: bool = Field(strict=True)


class TaskDraftEdit(Contract):
    dependency_plan_ids: list[str] = Field(default_factory=list, max_length=20)
    kind: Literal['build_site', 'launch_products']
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=10000)
    expected_revision: int = Field(ge=1, strict=True)
    expected_project_revision: int = Field(ge=1, strict=True)
    max_requests: int = Field(ge=1, le=100, strict=True)
    import_id: str | None = Field(default=None, min_length=1, max_length=200)
    theme_source_id: str | None = Field(default=None, min_length=1, max_length=200)


class TaskDraftControl(Contract):
    expected_revision: int = Field(ge=1, strict=True)


class DraftBatchItem(TaskDraftControl):
    draft_id: str = Field(min_length=1, max_length=200)


class DraftBatchInput(Contract):
    auto_apply_local: bool = Field(default=False, strict=True)
    items: list[DraftBatchItem] = Field(min_length=1, max_length=50)
    action: Literal['start', 'archive', 'cancel']
    expected_project_revision: int = Field(ge=1, strict=True)
    client_request_id: str = Field(min_length=1, max_length=200)


class TaskDraftStart(TaskDraftControl):
    expected_project_revision: int = Field(ge=1, strict=True)


class TaskDraftRename(TaskDraftControl):
    title: str = Field(min_length=1, max_length=160)


class PlanRename(Contract):
    expected_revision: int = Field(ge=0, strict=True)
    title: str = Field(min_length=1, max_length=160)


class PlanControl(Contract):
    expected_revision: int = Field(ge=1)


class ReleaseControl(Contract):
    expected_revision: int = Field(ge=1, strict=True)


class ContentConfirmationInput(Contract):
    expected_project_revision: int = Field(ge=1, strict=True)
    expected_plan_revision: int = Field(ge=1, strict=True)
    content_digest: str = Field(pattern=r'^[a-f0-9]{64}$')


class ReferenceControl(Contract):
    expected_revision: int = Field(ge=1, strict=True)
    action: Literal['provision', 'verify', 'recover', 'cleanup']


class VerificationStart(Contract):
    expected_revision: int = Field(ge=1, strict=True)
    client_request_id: str = Field(min_length=1, max_length=200)


def create_router(repo: CommerceRepository) -> APIRouter:
    def require_active_project(request: Request):
        identity = request.path_params.get('project_id')
        lifecycle = request.scope['route'].path in {'/api/commerce/projects/{project_id}/archive', '/api/commerce/projects/{project_id}/restore', '/api/commerce/projects/{project_id}'} and (request.method == 'DELETE' or request.url.path.endswith(('/archive','/restore')))
        if identity and not lifecycle:
            repo.get_project(identity)

    router = APIRouter(prefix='/api/commerce', tags=['commerce'], dependencies=[Depends(require_active_project)], responses={
        code: {'model': CommerceErrorEnvelope} for code in (404, 409, 422, 502, 503)})

    def reference_service(request):
        from muse.commerce.errors import CommerceFailure
        service = getattr(request.app.state, 'commerce_reference', None)
        if service is None:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        return service

    @router.get('/projects/{project_id}/reference-jobs', response_model=list[ReferenceJob])
    def reference_jobs(project_id: str):
        return ReferenceJobRepository(repo).list(project_id)

    @router.post('/projects/{project_id}/reference-jobs', response_model=ReferenceJob)
    async def reserve_reference(project_id: str, body: BlueprintInput, request: Request):
        return await reference_service(request).reserve(project_id, body.expected_revision, body.client_request_id)

    @router.post('/projects/{project_id}/reference-jobs/{job_id}')
    async def control_reference(project_id: str, job_id: str, body: ReferenceControl, request: Request):
        return await reference_service(request).execute(project_id, job_id, body.expected_revision, body.action)

    def verification_service(request):
        from muse.commerce.errors import CommerceFailure
        service = getattr(request.app.state, 'commerce_verification', None)
        if service is None:
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        return service

    @router.get('/projects/{project_id}/plans/{plan_id}/verification-jobs', response_model=list[VerificationStatus])
    def verification_jobs(project_id: str, plan_id: str):
        return VerificationStatusRepository(VerificationJobRepository(repo)).list(project_id, plan_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/verification-jobs', response_model=VerificationStatus)
    async def start_verification(project_id: str, plan_id: str, body: VerificationStart, request: Request):
        return await verification_service(request).reserve(project_id, plan_id, body.expected_revision, body.client_request_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/verification-jobs/{job_id}/cancel', response_model=VerificationStatus)
    async def cancel_verification(project_id: str, plan_id: str, job_id: str, body: ReleaseControl, request: Request):
        from muse.commerce.errors import CommerceFailure
        job = VerificationJobRepository(repo).read(project_id, job_id)
        if job.plan_id != plan_id:
            raise CommerceFailure('NOT_FOUND', 404)
        return await verification_service(request).cancel(project_id, job_id, body.expected_revision)

    @router.post('/projects/{project_id}/plans/{plan_id}/verification-jobs/{job_id}/reconcile', response_model=VerificationStatus)
    async def reconcile_verification(project_id: str, plan_id: str, job_id: str, body: ReleaseControl, request: Request):
        from muse.commerce.errors import CommerceFailure
        job = VerificationJobRepository(repo).read(project_id, job_id)
        if job.plan_id != plan_id:
            raise CommerceFailure('NOT_FOUND', 404)
        return await verification_service(request).reconcile(project_id, job_id, body.expected_revision)

    @router.post('/projects/{project_id}/plans/{plan_id}/verification-jobs/{job_id}/resume_staging', response_model=VerificationStatus)
    async def resume_staging_verification(project_id: str, plan_id: str, job_id: str, body: ReleaseControl, request: Request):
        from muse.commerce.errors import CommerceFailure
        job = VerificationJobRepository(repo).read(project_id, job_id)
        if job.plan_id != plan_id:
            raise CommerceFailure('NOT_FOUND', 404)
        return await verification_service(request).resume_staging(project_id, job_id, body.expected_revision)

    @router.get('/projects/{project_id}/plans/{plan_id}/content-proposal', response_model=ContentProposal)
    def content_proposal(project_id: str, plan_id: str):
        return ContentProposalRepository(repo).latest(project_id, plan_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/content-proposal/{proposal_id}/confirm', response_model=ContentConfirmation)
    def confirm_content(project_id: str, plan_id: str, proposal_id: str, body: ContentConfirmationInput):
        return ContentProposalRepository(repo).confirm(project_id, plan_id, proposal_id,
            body.expected_project_revision, body.expected_plan_revision, body.content_digest)

    def merchant_reviews(request):
        from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
        approvals = getattr(request.app.state, 'commerce_merchant_approvals', None)
        return MerchantReviewRepository(approvals if approvals is not None else MerchantReleaseApprovalRepository(repo))

    @router.get('/projects/{project_id}/plans/{plan_id}/release-review', response_model=MerchantReleaseReview)
    async def latest_release_review(project_id: str, plan_id: str, request: Request, revision: int = Query(ge=1)):
        view = merchant_reviews(request).latest(project_id, plan_id, revision)
        service = getattr(request.app.state, 'commerce_publication', None)
        result = service.review(project_id, plan_id, view.intent_digest, revision) if service else view
        return await result if inspect.isawaitable(result) else result

    @router.get('/projects/{project_id}/plans/{plan_id}/releases/{intent_digest}', response_model=MerchantReleaseReview)
    async def release_review(project_id: str, plan_id: str, intent_digest: str, request: Request, revision: int = Query(ge=1)):
        service = getattr(request.app.state, 'commerce_publication', None)
        result = (service.review(project_id, plan_id, intent_digest, revision) if service else
            merchant_reviews(request).read(project_id, plan_id, intent_digest, revision))
        return await result if inspect.isawaitable(result) else result

    @router.post('/projects/{project_id}/plans/{plan_id}/releases/{intent_digest}/approve', response_model=MerchantReleaseReview)
    def approve_release(project_id: str, plan_id: str, intent_digest: str, body: ReleaseControl, request: Request):
        return merchant_reviews(request).approve(project_id, plan_id, intent_digest, body.expected_revision)

    async def publication(project_id, plan_id, intent_digest, body, request, *, reconcile_only):
        from muse.commerce.errors import CommerceFailure
        repo.get_plan(plan_id, project_id=project_id)
        service = getattr(request.app.state, 'commerce_publication', None)
        if service is None:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        return await service.execute(project_id, plan_id, intent_digest, body.expected_revision, reconcile_only=reconcile_only)

    @router.post('/projects/{project_id}/plans/{plan_id}/releases/{intent_digest}/publish', response_model=MerchantReleaseReview)
    async def publish_release(project_id: str, plan_id: str, intent_digest: str, body: ReleaseControl, request: Request):
        return await publication(project_id, plan_id, intent_digest, body, request, reconcile_only=False)

    @router.post('/projects/{project_id}/plans/{plan_id}/releases/{intent_digest}/reconcile', response_model=MerchantReleaseReview)
    async def reconcile_release(project_id: str, plan_id: str, intent_digest: str, body: ReleaseControl, request: Request):
        return await publication(project_id, plan_id, intent_digest, body, request, reconcile_only=True)

    @router.post('/projects', response_model=StoreProject, status_code=201)
    def create_project(body: ProjectInput):
        return repo.create_project(body.workspace_id, body.brief, body.client_request_id)

    @router.post('/projects/restore', response_model=RestoredProject, status_code=201)
    async def restore_project(request: Request, workspace_id: str = Query(min_length=1, max_length=200),
                              client_request_id: str = Query(min_length=1, max_length=200)):
        import asyncio

        from muse.commerce.errors import CommerceFailure
        from muse.commerce.export import MAX_EXPORT
        from muse.commerce.restore import ProjectRestorer
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/zip':
            raise CommerceFailure('INPUT_INVALID', 422)
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_EXPORT:
                raise CommerceFailure('INPUT_INVALID', 422)
            content.extend(chunk)
        return await asyncio.to_thread(ProjectRestorer(repo).restore, workspace_id, bytes(content), client_request_id)

    @router.get('/projects/{project_id}/restored-themes', response_model=list[RestoredThemeSummary])
    def restored_theme_sources(project_id: str):
        from muse.commerce.restore import ProjectRestorer
        return ProjectRestorer(repo).list_theme_sources(project_id)

    @router.get('/projects/{project_id}/restored-themes/{source_id}', response_model=RestoredThemeSource)
    def restored_theme_source(project_id: str, source_id: str):
        from muse.commerce.restore import ProjectRestorer
        return ProjectRestorer(repo).theme_source(project_id, source_id)

    @router.get('/projects', response_model=list[StoreProject])
    def projects():
        return repo.list_projects()

    @router.get('/archived-projects', response_model=list[StoreProject])
    def archived_projects():
        return repo.list_archived_projects()

    @router.post('/projects/{project_id}/archive', response_model=StoreProject)
    def archive_project(project_id: str, body: ProjectLifecycleInput):
        return repo.archive_project(project_id, body.expected_revision)

    @router.post('/projects/{project_id}/restore', response_model=StoreProject)
    def restore_archived_project(project_id: str, body: ProjectLifecycleInput):
        return repo.restore_project(project_id, body.expected_revision)

    @router.delete('/projects/{project_id}', status_code=204)
    def delete_project(project_id: str, body: ProjectDeleteInput):
        repo.delete_project(project_id, body.expected_revision, body.confirmation_name)
        return Response(status_code=204)

    @router.get('/projects/{project_id}', response_model=StoreProject)
    def project(project_id: str):
        return repo.get_project(project_id)

    @router.get('/projects/{project_id}/export', response_model=ProjectExport)
    def export_project(project_id: str, revision: int = Query(ge=1)):
        from muse.commerce.export import ProjectExporter
        return ProjectExporter(repo).download_project(project_id, revision)

    @router.post('/projects/{project_id}/connections', response_model=StoreProject, status_code=201)
    async def bind_connection(project_id: str, body: ConnectionInput, request: Request):
        from muse.commerce.repository import digest
        previous = repo.binding_receipt(project_id, body.client_request_id, digest([body.connection_id, body.expected_revision]))
        if previous:
            return previous
        current = repo.get_project(project_id)
        if current.revision != body.expected_revision:
            from muse.commerce.errors import CommerceFailure
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        platform = request.app.state.commerce_platform
        reference = await platform.describe(project_id, body.connection_id)
        await platform.capabilities(project_id, body.connection_id)
        return repo.attach_connection(project_id, reference, body.client_request_id, body.expected_revision)

    @router.post('/projects/{project_id}/refresh-context', response_model=StoreContext)
    async def refresh_context(project_id: str, body: RefreshInput, request: Request):
        from muse.commerce.errors import CommerceFailure
        current = repo.get_project(project_id)
        if current.revision != body.expected_revision:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        ref = next((ref for ref in current.environment_refs if ref.environment == body.environment), None)
        if ref is None:
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503, project_id=project_id)
        platform = request.app.state.commerce_platform
        reference = await platform.describe(project_id, ref.connector_ref)
        if reference != ref:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        capabilities = await platform.capabilities(project_id, ref.connector_ref)
        snapshot = await platform.snapshot(project_id, ref.connector_ref, body.environment)
        return repo.save_context(project_id, ref.connector_ref, snapshot, capabilities, body.expected_revision)

    @router.get('/projects/{project_id}/context', response_model=StoreContext)
    def context(project_id: str, environment: Environment = 'staging'):
        return repo.get_context(project_id, environment)

    @router.patch('/projects/{project_id}', response_model=StoreProject)
    def update_brief(project_id: str, body: BriefUpdate):
        return repo.update_brief(project_id, body.brief, body.expected_revision)

    @router.get('/projects/{project_id}/events')
    def events(project_id: str, after: int = Query(default=0, ge=0)):
        return repo.events(project_id, after)

    @router.post('/projects/{project_id}/product-imports', response_model=ImportedProducts, status_code=201)
    def import_products(project_id: str, body: ProductImportInput):
        return repo.import_products(project_id, body.csv_text, body.client_request_id, body.expected_revision, media_ids=body.media_ids)

    @router.post('/projects/{project_id}/media', response_model=ProjectMedia, status_code=201)
    async def upload_media(project_id: str, request: Request, name: str = Query(min_length=1, max_length=200),
                           client_request_id: str = Query(min_length=1, max_length=200), expected_revision: int = Query(ge=1)):
        from muse.commerce.errors import CommerceFailure
        from muse.commerce.media import MediaRepository
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > 10 * 1024 * 1024:
                raise CommerceFailure('INPUT_INVALID', 422)
            content.extend(chunk)
        import asyncio
        return await asyncio.to_thread(MediaRepository(repo).upload, project_id, name,
            request.headers.get('content-type', ''), bytes(content), client_request_id, expected_revision)

    @router.get('/projects/{project_id}/media', response_model=list[ProjectMedia])
    def media(project_id: str):
        from muse.commerce.media import MediaRepository
        return MediaRepository(repo).list(project_id)

    @router.get('/projects/{project_id}/media/{media_id}/content')
    def media_content(project_id: str, media_id: str):
        from muse.commerce.media import MediaRepository
        record, content = MediaRepository(repo).content(project_id, media_id)
        suffix = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[record.image.mime_type]
        return Response(content, media_type=record.image.mime_type, headers={'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'none'; sandbox",
            'Content-Disposition': f'attachment; filename="image-{record.id}.{suffix}"'})

    @router.get('/projects/{project_id}/product-imports', response_model=list[ImportedProducts])
    def product_imports(project_id: str):
        return repo.list_product_imports(project_id)

    @router.post('/projects/{project_id}/site-blueprint', response_model=CommercePlan, status_code=201)
    def site_blueprint(project_id: str, body: BlueprintInput):
        return repo.create_site_blueprint(project_id, body.client_request_id, body.expected_revision)

    @router.patch('/projects/{project_id}/site-blueprint/{plan_id}', response_model=CommercePlan)
    def edit_site_blueprint(project_id: str, plan_id: str, body: BlueprintEditInput):
        return repo.edit_site_blueprint(project_id, plan_id, body.expected_revision,
                                       body.expected_plan_revision, body.pages, body.navigation)

    @router.get('/projects/{project_id}/plans', response_model=list[CommercePlan])
    def plans(project_id: str):
        return repo.list_plans(project_id)

    @router.get('/projects/{project_id}/shipping-rules', response_model=CommercePlan | None)
    def shipping_rules(project_id: str):
        from muse.commerce.shipping_drafts import ShippingDraftRepository
        return ShippingDraftRepository(repo).get(project_id)

    @router.patch('/projects/{project_id}/category-navigation', response_model=CommercePlan)
    def save_category_navigation(project_id: str, body: CategoryNavigationDraftInput):
        from muse.commerce.shipping_drafts import ShippingDraftRepository
        return ShippingDraftRepository(repo).save_source(project_id, body.expected_revision, body.plan_id,
            body.expected_plan_revision, body.client_request_id, 'category_navigation', body.navigation)

    @router.patch('/projects/{project_id}/shipping-rules', response_model=CommercePlan)
    def save_shipping_rules(project_id: str, body: ShippingDraftInput):
        from muse.commerce.shipping_drafts import ShippingDraftRepository
        return ShippingDraftRepository(repo).save(project_id, body.expected_revision, body.plan_id,
            body.expected_plan_revision, body.client_request_id, body.rules)

    @router.post('/projects/{project_id}/shipping-rules/quote', response_model=ShippingDraftQuote)
    def shipping_draft_quote(project_id: str, body: ShippingDraftQuoteInput):
        from decimal import Decimal
        from muse.commerce.errors import CommerceFailure
        from muse.commerce.shipping_drafts import ShippingDraftRepository
        current = ShippingDraftRepository(repo).get(project_id)
        if current is None or current.id != body.plan_id or current.revision != body.expected_plan_revision:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        raw = current.blueprint.required_settings.get('shipping_rules')
        if raw is None:
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
        try:
            rules = ShippingRules.model_validate(raw)
            amount = rules.quote(body.country, Decimal(body.subtotal))
        except ValueError:
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id) from None
        return ShippingDraftQuote(served=amount is not None, amount=None if amount is None else format(amount, '.2f'), currency=rules.currency)

    @router.get('/projects/{project_id}/plan-archives', response_model=list[CommercePlanArchive])
    def plan_archives(project_id: str):
        from muse.commerce.board import CommerceBoardRepository
        return CommerceBoardRepository(repo).list_archives(project_id)

    @router.post('/projects/{project_id}/plan-archives', response_model=list[CommercePlanArchive])
    def archive_plans(project_id: str, body: PlanArchiveInput):
        from muse.commerce.board import CommerceBoardRepository
        return CommerceBoardRepository(repo).archive(project_id, body.items, body.archived)

    @router.get('/projects/{project_id}/plans/{plan_id}', response_model=CommercePlan)
    def plan(project_id: str, plan_id: str):
        return repo.get_plan(plan_id, project_id=project_id)

    @router.get('/projects/{project_id}/plans/{plan_id}/code', response_model=ThemeCodeReview)
    def code_review(project_id: str, plan_id: str, revision: int = Query(ge=1)):
        from muse.commerce.code_bridge import review_captured_code
        from muse.commerce.errors import CommerceFailure
        current = repo.get_plan(plan_id, project_id=project_id)
        if current.revision != revision:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return review_captured_code(repo, current)

    @router.get('/projects/{project_id}/plans/{plan_id}/code-integration', response_model=CodeIntegrationReview)
    def code_integration_review(project_id: str, plan_id: str, request: Request, revision: int = Query(ge=1)):
        from muse.commerce.code_integration import CommerceCodeIntegration
        return CommerceCodeIntegration(repo, request.app.state.settings.data_dir / 'commerce-source.git').review(project_id, plan_id, revision)

    @router.post('/projects/{project_id}/plans/{plan_id}/code-integration', response_model=CommerceCodeHead)
    def apply_code_integration(project_id: str, plan_id: str, body: CodeIntegrationInput, request: Request):
        from muse.commerce.code_integration import CommerceCodeIntegration
        return CommerceCodeIntegration(repo, request.app.state.settings.data_dir / 'commerce-source.git').apply(project_id, plan_id, body)

    @router.get('/projects/{project_id}/code-dispositions', response_model=list[CodeDisposition])
    def code_dispositions(project_id: str):
        from muse.commerce.code_integration import CommerceCodeIntegration
        return CommerceCodeIntegration(repo, None).dispositions(project_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/code-disposition', response_model=CodeDisposition)
    def code_decision(project_id: str, plan_id: str, body: CodeDecisionInput):
        from muse.commerce.code_integration import CommerceCodeIntegration
        return CommerceCodeIntegration(repo, None).disposition(project_id, plan_id, body)

    @router.post('/projects/{project_id}/workflows', response_model=CommercePlan, status_code=201)
    def workflow(project_id: str, body: WorkflowInput, request: Request):
        return request.app.state.commerce_workflows.create_workflow(project_id, body.kind, body.prompt,
            body.client_request_id, body.expected_revision, max_requests=body.max_requests, import_id=body.import_id, theme_source_id=body.theme_source_id)

    def draft_service(request: Request):
        return CommerceDraftService(repo, request.app.state.commerce_workflows)

    def local_automation(request: Request):
        return LocalApplyService(repo, request.app.state.settings.data_dir / 'commerce-source.git')

    @router.get('/projects/{project_id}/plans/{plan_id}/follow-up-model-jobs', response_model=list[ModelSuggestionJob])
    def model_suggestion_jobs(project_id: str, plan_id: str, request: Request):
        return ModelSuggestionService(repo, request.app.state.settings).list(project_id, plan_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/follow-up-model-jobs', response_model=ModelSuggestionJob, status_code=201)
    def queue_model_suggestions(project_id: str, plan_id: str, body: ModelSuggestionInput, request: Request):
        return ModelSuggestionService(repo, request.app.state.settings).enqueue(project_id, plan_id, body)

    @router.get('/projects/{project_id}/plans/{plan_id}/local-apply-automation', response_model=LocalApplyAutomation | None)
    def get_local_automation(project_id: str, plan_id: str, request: Request):
        return local_automation(request).get(project_id, plan_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/local-apply-automation', response_model=LocalApplyAutomation)
    def arm_local_automation(project_id: str, plan_id: str, body: ArmLocalApply, request: Request):
        return local_automation(request).arm(project_id, plan_id, body)

    @router.post('/projects/{project_id}/plans/{plan_id}/local-apply-automation/cancel', response_model=LocalApplyAutomation)
    def cancel_local_automation(project_id: str, plan_id: str, body: AutomationControl, request: Request):
        return local_automation(request).cancel(project_id, plan_id, body.expected_revision)

    @router.post('/projects/{project_id}/task-drafts/batch', response_model=list[CommerceTaskDraft])
    def draft_batch(project_id: str, body: DraftBatchInput, request: Request):
        from muse.commerce.task_queue import CommerceTaskQueue
        return CommerceTaskQueue(repo, request.app.state.commerce_workflows).batch(project_id, body)

    @router.get('/projects/{project_id}/task-capacity')
    def task_capacity(project_id: str, request: Request):
        from muse.commerce.task_queue import CommerceTaskQueue
        return CommerceTaskQueue(repo, request.app.state.commerce_workflows).capacity(project_id)

    @router.get('/projects/{project_id}/plans/{plan_id}/follow-ups', response_model=list[FollowUpSuggestion])
    def follow_ups(project_id: str, plan_id: str, request: Request):
        return FollowUpService(repo, request.app.state.commerce_workflows).list(project_id, plan_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/follow-ups/accept', response_model=CommerceTaskDraft, status_code=201)
    def accept_follow_up(project_id: str, plan_id: str, body: FollowUpAccept, request: Request):
        return FollowUpService(repo, request.app.state.commerce_workflows).accept(project_id, plan_id, body)

    @router.post('/projects/{project_id}/plans/{plan_id}/follow-ups/accept-batch', response_model=list[CommerceTaskDraft], status_code=201)
    def accept_follow_up_batch(project_id: str, plan_id: str, body: FollowUpBatch, request: Request):
        return FollowUpService(repo, request.app.state.commerce_workflows).accept_batch(project_id, plan_id, body)

    @router.get('/projects/{project_id}/task-drafts', response_model=list[CommerceTaskDraft])
    def task_drafts(project_id: str, request: Request):
        return draft_service(request).list(project_id)

    @router.post('/projects/{project_id}/task-drafts', response_model=CommerceTaskDraft, status_code=201)
    def create_task_draft(project_id: str, body: TaskDraftInput, request: Request):
        return draft_service(request).create(project_id, body)

    @router.put('/projects/{project_id}/task-drafts/{draft_id}', response_model=CommerceTaskDraft)
    def edit_task_draft(project_id: str, draft_id: str, body: TaskDraftEdit, request: Request):
        return draft_service(request).edit(project_id, draft_id, body)

    @router.post('/projects/{project_id}/task-drafts/{draft_id}/rename', response_model=CommerceTaskDraft)
    def rename_task_draft(project_id: str, draft_id: str, body: TaskDraftRename, request: Request):
        return draft_service(request).rename(project_id, draft_id, body.title, body.expected_revision)

    @router.post('/projects/{project_id}/task-drafts/{draft_id}/archive', response_model=CommerceTaskDraft)
    def archive_task_draft(project_id: str, draft_id: str, body: TaskDraftControl, request: Request):
        return draft_service(request).archive(project_id, draft_id, body.expected_revision)

    @router.post('/projects/{project_id}/task-drafts/{draft_id}/restore', response_model=CommerceTaskDraft)
    def restore_task_draft(project_id: str, draft_id: str, body: TaskDraftControl, request: Request):
        return draft_service(request).restore(project_id, draft_id, body.expected_revision)

    @router.post('/projects/{project_id}/task-drafts/{draft_id}/start', response_model=CommerceTaskDraft)
    def start_task_draft(project_id: str, draft_id: str, body: TaskDraftStart, request: Request):
        return draft_service(request).start(project_id, draft_id, body.expected_revision, body.expected_project_revision)

    @router.get('/projects/{project_id}/plan-labels', response_model=list[CommercePlanLabel])
    def plan_labels(project_id: str, request: Request):
        return draft_service(request).list_labels(project_id)

    @router.post('/projects/{project_id}/plans/{plan_id}/rename', response_model=CommercePlanLabel)
    def rename_plan(project_id: str, plan_id: str, body: PlanRename, request: Request):
        return draft_service(request).rename_plan(project_id, plan_id, body.title, body.expected_revision)

    @router.get('/projects/{project_id}/plans/{plan_id}/preview', response_model=StorePreview)
    def preview(project_id: str, plan_id: str, revision: int = Query(ge=1)):
        from muse.commerce.preview_repository import PreviewRepository
        return PreviewRepository(repo).latest(project_id, plan_id, revision)

    @router.get('/projects/{project_id}/plans/{plan_id}/preview/{preview_id}/frames/{frame_id}', response_model=StorePreviewImage)
    def preview_frame(project_id: str, plan_id: str, preview_id: str, frame_id: str, revision: int = Query(ge=1)):
        from muse.commerce.preview_repository import PreviewRepository
        return PreviewRepository(repo).image(project_id, plan_id, preview_id, frame_id, revision)

    @router.post('/projects/{project_id}/plans/{plan_id}/advance', response_model=CommercePlan)
    def advance(project_id: str, plan_id: str, body: PlanControl, request: Request):
        repo.get_plan(plan_id, project_id=project_id)
        return request.app.state.commerce_workflows.advance(plan_id, body.expected_revision)

    @router.post('/projects/{project_id}/plans/{plan_id}/resume', response_model=CommercePlan)
    def resume(project_id: str, plan_id: str, body: PlanControl, request: Request):
        repo.get_plan(plan_id, project_id=project_id)
        return request.app.state.commerce_workflows.resume(plan_id, body.expected_revision)

    @router.get('/projects/{project_id}/plans/{plan_id}/outputs', response_model=list[dict])
    def outputs(project_id: str, plan_id: str):
        import json

        from sqlalchemy import text

        from muse.commerce.errors import CommerceFailure
        from muse.commerce.repository import digest
        plan = repo.get_plan(plan_id, project_id=project_id)
        with repo.db.transaction() as conn:
            records = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='commerce_output' ORDER BY id"),
                                   {'project': project_id, 'plan': plan_id}).mappings().all()
        values = []
        for record in records:
            value = json.loads(record['data'])
            step = next((step for step in plan.steps if step.id == value.get('step_id')), None)
            if (step is None or value.get('plan_id') != plan.id or value.get('task_id') != step.task_id
                    or digest(value.get('payload')) != record['digest'] or record['digest'] != step.output_hash):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            values.append(value)
        return values

    from muse.commerce.design_api import install_design_routes
    install_design_routes(router, repo)
    return router
