"""Closed media creation from merchant uploads, never a URL or host filename.

The factory loads the project's cleaned stored bytes. This module does not
approve, sign, send, overwrite, associate a product or refresh a fingerprint.
"""
import base64
import hashlib
import io
from typing import Literal, Self

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from muse.commerce.errors import CommerceFailure
from muse.commerce.media import MediaRepository
from muse.commerce.models import ChangeOperation
from muse.commerce.products import validate_media
from muse.commerce.repository import digest


class ImageDescriptor(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    mime_type: Literal['image/png', 'image/jpeg', 'image/webp']
    byte_size: int = Field(gt=0, le=10 * 1024 * 1024)
    width: int = Field(gt=0, le=20_000_000)
    height: int = Field(gt=0, le=20_000_000)


class RemoteAttachment(ImageDescriptor):
    id: int = Field(gt=0)
    media_ref: str = Field(pattern=r'^[a-f0-9]{64}$')
    muse_project_id: str = Field(min_length=1, max_length=100)
    status: Literal['inherit', 'draft', 'publish', 'private', 'trash']
    parent_id: int = Field(ge=0)
    title: str = Field(max_length=200)
    alt: str = Field(max_length=1000)


class MediaPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    media_ref: str = Field(pattern=r'^[a-f0-9]{64}$')
    image: ImageDescriptor
    content_base64: str = Field(min_length=1, max_length=14 * 1024 * 1024)

    @model_validator(mode='after')
    def exact_clean_bytes(self) -> Self:
        content = base64.b64decode(self.content_base64, validate=True)
        image = self.image
        if (base64.b64encode(content).decode('ascii') != self.content_base64
                or len(content) != image.byte_size or hashlib.sha256(content).hexdigest() != image.sha256
                or image.width * image.height > 20_000_000):
            raise ValueError('Image bytes differ from frozen metadata')
        extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[image.mime_type]
        validate_media('image.' + extension, image.mime_type, content, 'validated-wire')
        with Image.open(io.BytesIO(content)) as picture:
            if picture.size != (image.width, image.height) or any(key in picture.info for key in ('exif', 'icc_profile', 'xmp')):
                raise ValueError('Image dimensions or private metadata differ')
        return self


def prepare_media_operation(repository, project_id, media_id, absence_proof, operation_id):
    try:
        record, content = MediaRepository(repository).content(project_id, media_id)
        image = record.image
        state = {'sha256': image.sha256, 'exists': False}
        key = 'media-sha256:' + image.sha256
        proof = absence_proof
        if (record.id != digest([project_id, 'image', image.sha256]) or record.project_id != project_id
                or not isinstance(proof, dict) or set(proof) != {'resource_key', 'fingerprint', 'state'}
                or proof['resource_key'] != key or proof['state'] != state or proof['state'].get('exists') is not False
                or proof['fingerprint'] != digest(state)):
            raise ValueError('Project image or original absence proof differs')
        payload = {'media_ref': record.id, 'image': {'sha256': image.sha256, 'mime_type': image.mime_type,
            'byte_size': image.byte_size, 'width': record.width, 'height': record.height},
            'content_base64': base64.b64encode(content).decode('ascii')}
        from muse.commerce_connector.operations import validate_operation
        return validate_operation(ChangeOperation(operation_id=operation_id, kind='create_owned_media', resource_key=key,
                                  expected_fingerprint=proof['fingerprint'], payload=payload))
    except CommerceFailure:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        raise CommerceFailure('INPUT_INVALID', 422) from None


def resolve_created_media(connection, operation, receipt, proof):
    """A matched success receipt binds one exact initial attachment version."""
    from muse.commerce_connector.operation_ledger import OperationRecord
    from muse.commerce_connector.operations import operation_digest, validate_operation
    from muse.commerce_connector.wordpress import WordPressConnection
    try:
        if not isinstance(connection, WordPressConnection) or not isinstance(receipt, OperationRecord):
            raise TypeError('Invalid media creation evidence')
        operation = validate_operation(operation)
        if operation.kind != 'create_owned_media':
            raise ValueError('Not a media creation')
        payload = MediaPayload.model_validate(operation.payload)
        if (payload.media_ref != digest([connection.project_id, 'image', payload.image.sha256])
                or operation.expected_fingerprint != digest({'sha256': payload.image.sha256, 'exists': False})
                or receipt.state != 'SUCCEEDED'
                or receipt.project_id != connection.project_id or receipt.connection_id != connection.connection_id
                or receipt.environment != connection.environment or receipt.operation_id != operation.operation_id
                or receipt.operation_digest != operation_digest(operation) or receipt.resource_key != operation.resource_key
                or not isinstance(proof, dict) or set(proof) != {'resource_key', 'state', 'fingerprint'}
                or proof['resource_key'] != operation.resource_key or not isinstance(proof['state'], dict)
                or set(proof['state']) != {'sha256', 'exists', 'attachment'}
                or proof['state']['sha256'] != payload.image.sha256 or proof['state']['exists'] is not True
                or proof['fingerprint'] != digest(proof['state']) or receipt.fingerprint != proof['fingerprint']):
            raise ValueError('Creation does not match current readback')
        entity = RemoteAttachment.model_validate(proof['state']['attachment'])
        expected = {**payload.image.model_dump(), 'id': entity.id, 'media_ref': payload.media_ref,
            'muse_project_id': connection.project_id, 'status': 'inherit', 'parent_id': 0,
            'title': 'MUSE image ' + payload.image.sha256, 'alt': ''}
        if entity.model_dump() != expected:
            raise ValueError('Created attachment changed')
        return entity
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommerceFailure('REVIEW_STALE') from None


def prepare_product_with_media(repository, project_id, product, connection, sku_proof, media_evidence, operation_id):
    """Materialize image IDs only from cleaned project bytes and creation receipts.

    The broker must include each attachment proof in signed preconditions. This
    factory is neither an approval nor a public model-facing ID endpoint.
    """
    from muse.commerce.models import ProductDraft
    from muse.commerce_connector.operations import validate_operation
    try:
        if (not isinstance(product, ProductDraft) or connection.project_id != project_id
                or not product.media_refs or len(set(product.media_refs)) != len(product.media_refs)
                or not isinstance(media_evidence, list) or len(media_evidence) != len(product.media_refs)):
            raise ValueError('Invalid product media source')
        bindings = {}
        for operation, receipt, proof in media_evidence:
            remote = resolve_created_media(connection, operation, receipt, proof)
            record, content = MediaRepository(repository).content(project_id, remote.media_ref)
            if (remote.media_ref in bindings or record.image.sha256 != remote.sha256
                    or hashlib.sha256(content).hexdigest() != remote.sha256
                    or record.width != remote.width or record.height != remote.height
                    or record.image.mime_type != remote.mime_type or record.image.byte_size != remote.byte_size):
                raise ValueError('Remote image differs from merchant upload')
            bindings[remote.media_ref] = remote
        if set(bindings) != set(product.media_refs):
            raise ValueError('Unapproved or missing image')
        state = {'sku': product.sku.strip().casefold(), 'exists': False}
        key = 'sku:' + hashlib.sha256(state['sku'].encode()).hexdigest()
        if (not isinstance(sku_proof, dict) or set(sku_proof) != {'resource_key', 'state', 'fingerprint'}
                or sku_proof['resource_key'] != key or sku_proof['state'] != state
                or sku_proof['state']['exists'] is not False or sku_proof['fingerprint'] != digest(state)):
            raise ValueError('Original SKU absence differs')
        return validate_operation(ChangeOperation(operation_id=operation_id, kind='create_product_draft',
            resource_key=key, expected_fingerprint=sku_proof['fingerprint'], payload={
                'product': product.model_dump(mode='json'),
                'media_bindings': [bindings[ref].model_dump(mode='json') for ref in product.media_refs]}))
    except CommerceFailure:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommerceFailure('REVIEW_STALE') from None
