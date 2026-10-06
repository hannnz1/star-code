"""Closed operation wire contracts. Validation alone never grants write access."""
import base64
import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation, ProductDraft, SitePackage
from muse.commerce.theme import validate_site_archive
from muse.commerce_connector.media import MediaPayload, RemoteAttachment

Hash = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
PositiveId = Annotated[int, Field(gt=0, strict=True)]


class Payload(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PagePayload(Payload):
    page_id: PositiveId
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=256 * 1024)

    @field_validator('title', 'content')
    @classmethod
    def plain_text(cls, value):
        if '<' in value or '>' in value or '\x00' in value:
            raise ValueError('Only plain merchant text is supported')
        return value


class PagePublish(Payload):
    page_id: PositiveId


class PageCreate(Payload):
    slug: str = Field(pattern=r'^[a-z][a-z0-9-]{0,63}$')
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=256 * 1024)
    template: Literal['page', 'page-cart', 'page-checkout', 'page-about', 'page-contact']

    @field_validator('title', 'content')
    @classmethod
    def plain_text(cls, value):
        if '<' in value or '>' in value or '\x00' in value:
            raise ValueError('Only plain merchant text is supported')
        return value


class ProductPublish(Payload):
    product_id: PositiveId


class ProductPayload(Payload):
    product: ProductDraft
    media_bindings: list[RemoteAttachment] = Field(default_factory=list, max_length=5)

    @field_validator('product', mode='before')
    @classmethod
    def exact_price(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get('price'), str):
            raise ValueError('Price must be an exact decimal string')  # noqa: TRY004 - Pydantic validation boundary
        if not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,6})?', value['price']):
            raise ValueError('Price exceeds the import precision or format')
        if isinstance(value.get('stock'), int) and value['stock'] > 2147483647:
            raise ValueError('Stock exceeds the platform integer limit')
        return value

    @model_validator(mode='after')
    def exact_media(self):
        refs = self.product.media_refs
        if (refs != [item.media_ref for item in self.media_bindings] or len(set(refs)) != len(refs)
                or len({item.id for item in self.media_bindings}) != len(refs)
                or any(item.status != 'inherit' or item.parent_id != 0 or item.alt != ''
                    or item.title != 'MUSE image ' + item.sha256
                    or item.media_ref != hashlib.sha256(json.dumps([item.muse_project_id, 'image', item.sha256],
                        ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    for item in self.media_bindings)):
            raise ValueError('Exact owned media versions are required')
        return self

    @field_validator('product')
    @classmethod
    def plain_content(cls, value):
        for text in (value.title, value.description, value.category):
            if '<' in text or '>' in text or '\x00' in text:
                raise ValueError('Only plain merchant text is supported')
        return value


class NavigationItem(Payload):
    page_id: PositiveId
    label: str = Field(min_length=1, max_length=160, pattern=r'^[^<>\x00]+$')


class NavigationPayload(Payload):
    items: list[NavigationItem] = Field(min_length=1, max_length=7)

    @field_validator('items')
    @classmethod
    def unique_pages(cls, items):
        if len({item.page_id for item in items}) != len(items):
            raise ValueError('Duplicate page')
        return items


class StorefrontPayload(Payload):
    home_page_id: PositiveId
    shop_page_id: PositiveId
    cart_page_id: PositiveId
    checkout_page_id: PositiveId


class CategoryNavigationTarget(Payload):
    category_id: PositiveId
    label: str = Field(min_length=1, max_length=160, pattern=r'^[^<>\x00]+$')


class StoreNavigationPayload(Payload):
    items: list[NavigationItem | CategoryNavigationTarget] = Field(min_length=1, max_length=16)

    @field_validator('items')
    @classmethod
    def distinct(cls, items):
        identities = [('page',item.page_id) if isinstance(item, NavigationItem) else ('category',item.category_id) for item in items]
        if len(set(identities)) != len(items):
            raise ValueError('Duplicate navigation target')
        return items


class ShippingPayload(Payload):
    from muse.commerce.shipping_rules import ShippingRules as _ShippingRules
    rules: _ShippingRules


class ThemePayload(Payload):
    package: SitePackage
    archive_base64: str = Field(min_length=1, max_length=7 * 1024 * 1024)


_MODELS = {
    'update_owned_page': PagePayload, 'publish_owned_page': PagePublish,
    'publish_product': ProductPublish, 'create_product_draft': ProductPayload,
    'set_owned_navigation': NavigationPayload, 'set_storefront_options': StorefrontPayload,
    'install_theme_package': ThemePayload,
    'create_owned_page': PageCreate,
    'create_owned_media': MediaPayload,
    'set_owned_shipping': ShippingPayload,
    'set_owned_store_navigation': StoreNavigationPayload,
}


def operation_digest(operation: ChangeOperation) -> str:
    """Same exact canonical wire representation used by the durable ledger."""
    raw = json.dumps(operation.model_dump(mode='json'), ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def validate_operation(operation: ChangeOperation) -> ChangeOperation:
    try:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', operation.operation_id):
            raise ValueError('Invalid operation identity')
        if not operation.expected_fingerprint or not re.fullmatch(r'[a-f0-9]{64}', operation.expected_fingerprint):
            raise ValueError('An explicit resource precondition is required')
        payload = _MODELS[operation.kind].model_validate(operation.payload)
        if operation.kind == 'create_owned_page':
            expected = 'page-slug:' + hashlib.sha256(payload.slug.encode('utf-8')).hexdigest()
        elif operation.kind in ('update_owned_page', 'publish_owned_page'):
            expected = f'page:{payload.page_id}'
        elif operation.kind == 'publish_product':
            expected = f'product:{payload.product_id}'
        elif operation.kind == 'create_product_draft':
            sku_hash = hashlib.sha256(payload.product.sku.strip().casefold().encode('utf-8')).hexdigest()
            expected = 'sku:' + sku_hash
        elif operation.kind in {'set_owned_navigation', 'set_owned_store_navigation'}:
            expected = 'navigation:muse-storefront'
        elif operation.kind == 'set_owned_shipping':
            expected = 'shipping:muse-storefront'
        elif operation.kind == 'create_owned_media':
            expected = 'media-sha256:' + payload.image.sha256
        elif operation.kind == 'set_storefront_options':
            expected = 'settings'
            ids = (payload.home_page_id, payload.shop_page_id, payload.cart_page_id, payload.checkout_page_id)
            if len(set(ids)) != 4:
                raise ValueError('Storefront pages must be distinct')
        else:
            expected = 'theme:muse-storefront'
            metadata = payload.package
            if not re.fullmatch(r'[a-f0-9]{40}', metadata.code_revision):
                raise ValueError('Full source revision required')
            for value in (metadata.package_sha256, metadata.immutable_code_sha256, metadata.content_sha256):
                if not re.fullmatch(r'[a-f0-9]{64}', value):
                    raise ValueError('Invalid package hash')
            validate_site_archive(base64.b64decode(payload.archive_base64, validate=True), metadata)
        if operation.resource_key != expected:
            raise ValueError('Resource differs from payload')
        operation_digest(operation)
        return operation.model_copy(deep=True)
    except (ValueError, TypeError, KeyError, ValidationError, UnicodeError):
        raise CommerceFailure('INPUT_INVALID', 422) from None
