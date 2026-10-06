"""Merchant uploads, never arbitrary URLs, paths or model-supplied artifact references."""
import base64
import hashlib
import io

from PIL import Image, ImageOps
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ProjectMedia
from muse.commerce.products import validate_media
from muse.commerce.repository import digest, encode

MAX_PROJECT_MEDIA_BYTES = 100 * 1024 * 1024
MAX_PROJECT_IMAGES = 100


class MediaRepository:
    def __init__(self, commerce):
        self.commerce, self.db = commerce, commerce.db

    @staticmethod
    def _read(conn, project_id, media_id):
        import json
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='product_media'"),
                           {'id': media_id, 'project': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            payload = json.loads(row['data'])
            record = ProjectMedia.model_validate(payload['record'])
            content = base64.b64decode(payload['content_base64'], validate=True)
            if (digest(payload) != row['digest'] or record.project_id != project_id or record.id != media_id
                    or record.image.artifact_ref != media_id or len(content) != record.image.byte_size
                    or hashlib.sha256(content).hexdigest() != record.image.sha256):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise CommerceFailure('RESOURCE_CONFLICT') from None
        return record, content

    def upload(self, project_id, name, mime_type, data, request_id, expected_revision):
        import json
        try:
            validate_media(name, mime_type, data, 'upload-validation')
            with Image.open(io.BytesIO(data)) as source:
                picture = ImageOps.exif_transpose(source)
                if mime_type == 'image/jpeg':
                    picture = picture.convert('RGB')
                elif mime_type == 'image/png':
                    picture = picture.convert('RGBA' if 'A' in picture.getbands() else 'RGB')
                picture.info.clear()
                output = io.BytesIO()
                picture.save(output, format={'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WEBP'}[mime_type])
                content = output.getvalue()
                width, height = picture.size
            # Validate again: re-encoding can enlarge a compressed image.
            checked = validate_media(name, mime_type, content, 'upload-validation')
        except (ValueError, OSError):
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id) from None
        request_hash = digest([name, mime_type, hashlib.sha256(data).hexdigest(), expected_revision])
        receipt_id = digest([project_id, 'media_upload', request_id])
        identity = digest([project_id, 'image', checked.sha256])
        with self.db.transaction() as conn:
            project = self.commerce._project(conn, project_id, expected_revision)
            previous = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='media_upload_receipt'"),
                                    {'id': receipt_id}).mappings().first()
            if previous:
                if previous['digest'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return self._read(conn, project_id, json.loads(previous['data'])['media_id'])[0]
            rows = conn.execute(text("SELECT id,data FROM commerce_artifacts WHERE project_id=:project AND kind='product_media'"),
                                {'project': project_id}).mappings().all()
            existing = None
            total = 0
            for row in rows:
                record, _ = self._read(conn, project_id, row['id'])
                total += record.image.byte_size
                if record.image.name.casefold() == checked.name.casefold():
                    if row['id'] != identity:
                        raise CommerceFailure('RESOURCE_CONFLICT')
                    existing = record
                elif row['id'] == identity:
                    # Do not introduce an ambiguous second name for the same image.
                    raise CommerceFailure('RESOURCE_CONFLICT')
            if existing is None:
                if len(rows) >= MAX_PROJECT_IMAGES or total + len(content) > MAX_PROJECT_MEDIA_BYTES:
                    raise CommerceFailure('INPUT_INVALID', 422)
                existing = ProjectMedia(id=identity, project_id=project_id, project_revision=project.revision,
                    image=checked.model_copy(update={'artifact_ref': identity}), width=width, height=height)
                payload = {'record': existing.model_dump(mode='json'), 'content_base64': base64.b64encode(content).decode('ascii')}
                conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'product_media',:digest,:data)"),
                    {'id': identity, 'project': project_id, 'digest': digest(payload), 'data': encode(payload)})
                self.commerce.event(conn, project_id, 'product_image_uploaded', {'media_id': identity, 'sha256': checked.sha256})
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'media_upload_receipt',:digest,:data)"),
                {'id': receipt_id, 'project': project_id, 'digest': request_hash, 'data': encode({'media_id': identity})})
            return existing

    def list(self, project_id):
        with self.db.transaction() as conn:
            self.commerce._project(conn, project_id)
            ids = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND kind='product_media' ORDER BY rowid"),
                               {'project': project_id}).scalars().all()
            return [self._read(conn, project_id, identity)[0] for identity in ids]

    def content(self, project_id, media_id):
        with self.db.transaction() as conn:
            self.commerce._project(conn, project_id)
            return self._read(conn, project_id, media_id)
