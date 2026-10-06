"""Strict merchant artifacts, separate from general coding TaskRequest."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from muse.commerce.errors import ErrorCode

Environment = Literal['staging', 'live', 'live-test']
CommerceRole = Literal['store_manager', 'site_developer', 'product_content']
CommerceState = Literal['NEEDS_INPUT', 'PLANNING', 'BUILDING', 'VERIFYING', 'REVIEW_REQUIRED',
                        'APPROVED', 'PUBLISHING', 'SUCCEEDED', 'PARTIAL', 'NEEDS_RECONCILIATION',
                        'STALE', 'BLOCKED', 'FAILED', 'CANCELLED']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class CommerceTaskDraft(Contract):
    id: str
    project_id: str
    kind: Literal['build_site', 'launch_products']
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=10000)
    max_requests: int = Field(ge=1, le=100, strict=True)
    import_id: str | None = None
    theme_source_id: str | None = None
    proposed_steps: list[str] = Field(default_factory=list, max_length=6)
    project_revision: int = Field(ge=1)
    code_base_revision: int = Field(default=0, ge=0)
    revision: int = Field(default=1, ge=1)
    status: Literal['DRAFT', 'QUEUED', 'ARCHIVED', 'STARTED'] = 'DRAFT'
    dependency_plan_ids: list[str] = Field(default_factory=list, max_length=20)
    queue_reason: str | None = None
    auto_apply_local: bool = False
    plan_id: str | None = None
    source_plan_id: str | None = None
    source_plan_revision: int | None = Field(default=None, ge=1)
    suggestion_id: str | None = None
    created_at: float
    updated_at: float


class CommercePlanLabel(Contract):
    plan_id: str
    project_id: str
    title: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    updated_at: float


class CommercePlanArchive(Contract):
    plan_id: str
    project_id: str
    archived: bool
    revision: int = Field(ge=1)
    updated_at: float


class CommerceCodeHead(Contract):
    project_id: str
    plan_id: str
    source_id: str
    code_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    revision: int = Field(ge=1)
    updated_at: float


class CodeIntegrationReview(Contract):
    project_id: str
    plan_id: str
    plan_revision: int
    project_revision: int
    head_revision: int
    review_digest: str
    source_digest: str
    changed_files: list[str]
    conflict_files: list[str]
    diff: str
    applicable: bool
    reason: Literal['ready', 'conflicts', 'no_changes', 'plan_ineligible', 'dismissed']


class CodeDisposition(Contract):
    project_id: str
    plan_id: str
    source_digest: str
    status: Literal['APPLIED', 'DISMISSED', 'PENDING']
    revision: int = Field(ge=1)


class SiteBrief(Contract):
    brand_name: str = Field(min_length=1, max_length=160)
    language: str = Field(min_length=2, max_length=24, pattern=r'^[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{2,8})*$')
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    audience: str = Field(default='', max_length=4000)
    style: str = Field(default='', max_length=4000)
    merchant_supplied_policies: dict[str, str] = Field(default_factory=dict, max_length=10)


class EnvironmentRef(Contract):
    id: str
    project_id: str
    environment: Environment
    public_url: str
    connector_ref: str


class StorePreviewFrame(Contract):
    id: str = Field(pattern=r'^[a-f0-9]{64}$')
    kind: Literal['home', 'shop', 'product', 'cart', 'checkout', 'about', 'contact']
    width: Literal[390, 768, 1440]
    height: Literal[900] = 900
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    sku: str | None = None


class StorePreview(Contract):
    id: str = Field(pattern=r'^[a-f0-9]{64}$')
    project_id: str
    plan_id: str
    plan_revision: int = Field(ge=1)
    source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    snapshot_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    frames: list[StorePreviewFrame] = Field(max_length=78)
    checks: dict[str, bool]
    diagnostics: list[str] = Field(max_length=100)
    passed: bool
    site_verified: Literal[False] = False


class StorePreviewImage(Contract):
    frame: StorePreviewFrame
    png_base64: str = Field(max_length=7 * 1024 * 1024)


class StoreProject(Contract):
    id: str
    workspace_id: str
    platform: Literal['wordpress'] = 'wordpress'
    revision: int = Field(default=1, ge=1)
    brief: SiteBrief
    environment_refs: list[EnvironmentRef] = Field(default_factory=list)


class StoreSnapshot(Contract):
    project_id: str
    environment: Environment
    resource_fingerprints: dict[str, str] = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)
    pages: list[dict] = Field(default_factory=list)
    products: list[dict] = Field(default_factory=list)
    theme_identity: dict = Field(default_factory=dict)


PageKind = Literal['home', 'shop', 'product', 'cart', 'checkout', 'about', 'contact']


class BlueprintPage(Contract):
    kind: PageKind
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    title: str = Field(min_length=1, max_length=160)


class NavigationItem(Contract):
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    label: str = Field(min_length=1, max_length=160)


class SiteBlueprint(Contract):
    pages: list[BlueprintPage] = Field(min_length=7, max_length=7)
    navigation: list[NavigationItem] = Field(default_factory=list, max_length=7)
    design_tokens: dict = Field(default_factory=dict)
    required_settings: dict = Field(default_factory=dict)

    @field_validator('pages')
    @classmethod
    def unique_pages(cls, pages):
        if len({p.kind for p in pages}) != 7 or len({p.slug for p in pages}) != 7:
            raise ValueError('Each of the seven page kinds needs a distinct slug')
        return pages


class MediaInput(Contract):
    name: str = Field(min_length=1, max_length=200)
    mime_type: Literal['image/png', 'image/jpeg', 'image/webp']
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    byte_size: int = Field(gt=0, le=10 * 1024 * 1024)
    artifact_ref: str


class ProjectMedia(Contract):
    id: str
    project_id: str
    project_revision: int = Field(ge=1)
    image: MediaInput
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ProductDraft(Contract):
    sku: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    stock: int = Field(ge=0, strict=True)
    description: str = Field(default='', max_length=20000)
    category: str = Field(default='', max_length=160)
    source_facts: dict[str, str] = Field(default_factory=dict)
    media_refs: list[str] = Field(default_factory=list, max_length=5)


class CommerceStep(Contract):
    id: str
    role: CommerceRole
    dependencies: list[str] = Field(default_factory=list)
    task_id: str | None = None
    status: Literal['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'] = 'PENDING'
    output_hash: str | None = None
    correction_attempts: int = Field(default=0, ge=0, le=1)


class CommercePlan(Contract):
    id: str
    project_id: str
    kind: Literal['build_site', 'launch_products']
    revision: int = Field(default=1, ge=1)
    state: CommerceState = 'PLANNING'
    snapshot_hash: str | None = None
    blueprint: SiteBlueprint | None = None
    products: list[ProductDraft] = Field(default_factory=list, max_length=20)
    code_revision: str | None = None
    content_hash: str | None = None
    steps: list[CommerceStep] = Field(default_factory=list)
    error_code: ErrorCode | None = None

    @field_validator('products')
    @classmethod
    def unique_skus(cls, products):
        keys = [p.sku.casefold() for p in products]
        if len(set(keys)) != len(keys):
            raise ValueError('Duplicate product SKU')
        return products


OperationKind = Literal['install_theme_package', 'update_owned_page', 'set_owned_navigation',
                        'create_product_draft', 'publish_product', 'publish_owned_page', 'set_storefront_options', 'create_owned_page',
                        'create_owned_media', 'set_owned_shipping', 'set_owned_store_navigation']


class ChangeOperation(Contract):
    operation_id: str
    kind: OperationKind
    resource_key: str
    expected_fingerprint: str | None = None
    payload: dict


class ChangeSet(Contract):
    id: str
    plan_id: str
    project_id: str
    environment: Environment
    operations: list[ChangeOperation]
    resource_preconditions: dict[str, str] = Field(default_factory=dict)
    package_hash: str | None = None
    content_hash: str
    digest: str


class VerificationReport(Contract):
    id: str
    changeset_digest: str
    code_revision: str | None
    snapshot_hash: str
    passed: bool
    checks: list[dict]
    evidence_refs: list[str] = Field(default_factory=list)


class SitePackage(Contract):
    code_revision: str
    files_manifest: list[dict]
    package_sha256: str
    immutable_code_sha256: str
    content_sha256: str


class ThemeCodeReview(Contract):
    plan_id: str
    plan_revision: int = Field(ge=1)
    code_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    package_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    files_manifest: list[dict]
    diff: str
    site_verified: Literal[False] = False
    published: Literal[False] = False


class PreviewRef(Contract):
    id: str
    plan_id: str
    environment_ref: str
    url: str
    code_revision: str
    content_sha256: str
    snapshot_hash: str


class ApprovalGrant(Contract):
    id: str
    changeset_digest: str
    project_id: str
    environment: Environment
    resource_preconditions: dict[str, str]
    verification_hash: str
    expires_at: float
    status: Literal['approved', 'revoked', 'consumed'] = 'approved'


class PublishReceipt(Contract):
    id: str
    changeset_digest: str
    state: Literal['SUCCEEDED', 'PARTIAL', 'NEEDS_RECONCILIATION', 'FAILED', 'STALE']
    operation_receipts: list[dict] = Field(default_factory=list)
    next_action: str


class PlatformCapabilities(Contract):
    wordpress_version: str
    woocommerce_version: str
    theme_id: str
    supported_operations: list[OperationKind]
    missing_requirements: list[str] = Field(default_factory=list)


class StoreContext(Contract):
    snapshot_id: str
    snapshot_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    project_revision: int = Field(ge=1)
    connection_ref: str
    connection_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    snapshot: StoreSnapshot
    capabilities: PlatformCapabilities


class ImportIssue(Contract):
    row: int
    field: str
    code: str
    message: str


class ProductImportResult(Contract):
    drafts: list[ProductDraft] = Field(default_factory=list)
    errors: list[ImportIssue] = Field(default_factory=list)


class ImportedProducts(Contract):
    id: str
    project_id: str
    project_revision: int
    csv_sha256: str
    store_conflicts_checked: bool = False
    result: ProductImportResult


class ExportManifest(Contract):
    project_id: str
    revision: int
    files_manifest: list[dict]
    required_versions: dict[str, str]


class ProjectExport(Contract):
    manifest: ExportManifest
    archive_base64: str = Field(max_length=24 * 1024 * 1024)


class RestoredProject(Contract):
    project: StoreProject
    import_ids: list[str] = Field(default_factory=list)
    media_ids: list[str] = Field(default_factory=list)
    theme_source_ids: list[str] = Field(default_factory=list)
    deployment_verified: Literal[False] = False
    requires_new_approval: Literal[True] = True


class RestoredThemeSummary(Contract):
    id: str
    project_id: str
    package: SitePackage
    deployment_verified: Literal[False] = False


class RestoredThemeSource(RestoredThemeSummary):
    archive_base64: str = Field(max_length=8 * 1024 * 1024)
