"""Project facts are untrusted data; no shop value grants tool authority."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from muse.commerce.environment import validate_lock
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Environment, PlatformCapabilities, StoreSnapshot
from muse.commerce.repository import digest


class RemoteRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra='ignore')


class RemotePage(RemoteRecord):
    id: int = Field(gt=0)
    slug: str
    title: str
    content: str = Field(max_length=256 * 1024)
    status: str
    muse_project_id: str | None = None
    template: str | None = None


class RemoteCategory(RemoteRecord):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2048)


class RemoteProduct(RemoteRecord):
    id: int = Field(gt=0)
    sku: str
    name: str
    price: str
    stock_quantity: int | None = Field(ge=0)
    description: str = Field(default='', max_length=256 * 1024)
    status: str | None = None
    type: str | None = None
    muse_project_id: str | None = None
    regular_price: str | None = None
    sale_price: str | None = None
    manage_stock: bool | None = None
    stock_status: str | None = None
    backorders: str | None = None
    catalog_visibility: str | None = None
    category_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=200)
    categories: list[RemoteCategory] = Field(default_factory=list, max_length=200)
    image_id: int = Field(default=0, ge=0)
    gallery_image_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=200)


class RemoteSettings(RemoteRecord):
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    shipping_configuration: dict | None = None
    language: str = Field(min_length=2, max_length=24)
    permalink_structure: str | None = None
    shipping_confirmed: bool | None = None
    payment_confirmed: bool | None = None
    blog_public: int | None = None
    home_page_id: int = Field(default=0, ge=0)
    shop_page_id: int = Field(default=0, ge=0)
    cart_page_id: int = Field(default=0, ge=0)
    checkout_page_id: int = Field(default=0, ge=0)
    show_on_front: str | None = None
    coming_soon: bool | None = None
    store_pages_only: bool | None = None


class RemoteTemplate(RemoteRecord):
    id: str = Field(min_length=1)
    content: str = Field(max_length=256 * 1024)
    slug: str | None = None
    type: str | None = None
    source: str | None = None


class RemoteGlobalStyles(RemoteRecord):
    styles: dict
    settings: dict = Field(default_factory=dict)
    version: int | None = None


class RemoteTheme(RemoteRecord):
    stylesheet: str = Field(min_length=1)
    version: str | None = None
    effective_templates: list[RemoteTemplate] = Field(max_length=200)
    global_styles: RemoteGlobalStyles
    files_sha256: dict[str, str | None] = Field(default_factory=dict)
    owned_navigation: dict = Field(default_factory=dict)


class RemoteSnapshot(RemoteRecord):
    pages: list[RemotePage] = Field(max_length=200)
    products: list[RemoteProduct] = Field(max_length=200)
    settings: RemoteSettings
    theme_identity: RemoteTheme


def normalize_snapshot(raw: dict, project_id: str, environment: Environment) -> StoreSnapshot:
    try:
        validated = RemoteSnapshot.model_validate(raw).model_dump(exclude_unset=True)
        pages, products, settings, theme = (validated[key] for key in ('pages', 'products', 'settings', 'theme_identity'))
        template_ids = [item['id'] for item in theme['effective_templates']]
        if len(set(template_ids)) != len(template_ids):
            raise ValueError('Duplicate template identity')
        theme['effective_templates'].sort(key=lambda item: item['id'])
        fingerprints = {'settings': digest(settings), 'theme': digest(theme)}
        if settings.get('shipping_configuration') is not None:
            fingerprints['shipping:muse-storefront'] = digest(settings['shipping_configuration'])
        categories = {}
        for product in products:
            for category in product.get('categories', []):
                key = 'category:' + str(category['id'])
                if 'slug' in category and 'url' in category:
                    if key in categories and categories[key] != category:
                        raise ValueError('Contradictory category facts')
                    categories[key] = category
        fingerprints.update({key:digest(value) for key,value in categories.items()})
        if 'owned_navigation' in theme:
            fingerprints['navigation:muse-storefront'] = digest(theme['owned_navigation'])
        for kind, items in [('page', pages), ('product', products)]:
            seen = set()
            for item in items:
                identity = item['id']
                if type(identity) is not int or identity <= 0 or identity in seen:
                    raise ValueError('invalid identity')
                seen.add(identity)
                fingerprints[f'{kind}:{identity}'] = digest(item)
        return StoreSnapshot(project_id=project_id, environment=environment, pages=pages, products=products,
                             settings=settings, theme_identity=theme, resource_fingerprints=fingerprints)
    except (KeyError, ValueError, TypeError, AttributeError):
        raise CommerceFailure('READ_TEMPORARY_FAILURE', 502, project_id=project_id) from None


def require_capabilities(raw: dict, lock: dict) -> PlatformCapabilities:
    try:
        capabilities = PlatformCapabilities.model_validate(raw)
    except ValidationError:
        raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422) from None
    if (lock.get('verified') is not True or capabilities.missing_requirements
            or capabilities.wordpress_version != lock.get('wordpress')
            or capabilities.woocommerce_version != lock.get('woocommerce')
            or capabilities.theme_id != 'muse-storefront'):
        raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
    try:
        validate_lock(lock)
    except ValueError:
        raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422) from None
    return capabilities
