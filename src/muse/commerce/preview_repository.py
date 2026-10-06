"""Private diagnostic captures, with read-only merchant access. No approval.

Only a trusted backend calls save; there is no upload or mark-verified endpoint.
Browser evidence is deliberately insufficient to issue publication authority.
"""
import base64
import hashlib
import io
import json
import re

from PIL import Image
from sqlalchemy import text

from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    CommercePlan,
    StorePreview,
    StorePreviewFrame,
    StorePreviewImage,
)
from muse.commerce.preview import (
    MAX_CAPTURE_BYTES,
    MAX_FRAME_BYTES,
    StagePreviewCapture,
)
from muse.commerce.release import release_source_hash
from muse.commerce.repository import digest, encode
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce.verification_target import VerificationTargetRepository

CHECKS = {'pages', 'layout_desktop', 'layout_tablet', 'layout_mobile', 'links'}


class PreviewRepository:
    def __init__(self, repo):
        self.repo = repo

    def _source(self, conn, project_id, plan_id, revision):
        project = self.repo._project(conn, project_id)
        row = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:plan AND project_id=:project'),
                           {'plan': plan_id, 'project': project_id}).scalar()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
        plan = CommercePlan.model_validate_json(row)
        if (type(revision) is not int or plan.revision != revision or plan.state in {'STALE', 'CANCELLED'}):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        target = VerificationTargetRepository(VerificationJobRepository(self.repo))._target(conn, project_id, plan_id)
        if target is None:
            target = next((ref for ref in project.environment_refs if ref.environment == 'staging'), None)
        if target is None:
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        code = load_captured_code(self.repo, plan, connection=conn)
        return plan, code, {'project_hash': digest(project), 'plan_source_hash': release_source_hash(plan),
                            'target': target.model_dump(mode='json')}

    @staticmethod
    def _png(frame, content):
        if (not isinstance(content, bytes) or len(content) > MAX_FRAME_BYTES
                or hashlib.sha256(content).hexdigest() != frame.sha256):
            raise ValueError('Image bytes differ')
        with Image.open(io.BytesIO(content)) as image:
            if image.format != 'PNG' or image.size != (frame.width, frame.height):
                raise ValueError('Image geometry differs')
            image.verify()

    def save(self, project_id, plan_id, revision, capture):
        with self.repo.db.transaction() as conn:
            plan, code, binding = self._source(conn, project_id, plan_id, revision)
            try:
                if (not isinstance(capture, StagePreviewCapture) or capture.site_verified is not False
                        or capture.source_digest != code.source_digest or type(capture.passed) is not bool
                        or capture.connection_id != binding['target']['connector_ref']
                        or capture.target_url != binding['target']['public_url']
                        or not re.fullmatch(r'[a-f0-9]{64}', capture.snapshot_hash)
                        or set(capture.checks) != CHECKS or any(type(v) is not bool for v in capture.checks.values())
                        or any(not re.fullmatch(r'[A-Z_]+(?::(?:home|shop|product|cart|checkout|about|contact):(?:390|768|1440))?', d)
                               for d in capture.diagnostics) or len(capture.diagnostics) > 100):
                    raise ValueError('Invalid capture binding')
                wanted = {(p.kind, width, None) for p in plan.blueprint.pages if p.kind != 'product' for width in (390, 768, 1440)}
                wanted |= {('product', width, p.sku) for p in plan.products for width in (390, 768, 1440)}
                if not any(product.stock >= 1 for product in plan.products) and binding['target']['connector_ref'].startswith('ref-'):
                    from muse.commerce.buyer_fixture import (
                        BuyerFixtureRepository,
                        read_disposable_product,
                    )
                    from muse.commerce.release_approval import (
                        ProductReleaseApprovalRepository as Records,
                    )
                    ref_id = binding['target']['connector_ref'][4:]
                    row, fixture = Records._read(conn, BuyerFixtureRepository.key(project_id, plan_id, ref_id), 'buyer_fixture_binding')
                    if row['project_id'] != project_id or row['plan_id'] != plan_id:
                        raise ValueError('Fixture scope differs')
                    probe = read_disposable_product(fixture['proof'], project_id=project_id, job_id=ref_id,
                        currency=plan.blueprint.required_settings['currency'])
                    wanted |= {('product', width, probe.draft.sku) for width in (390, 768, 1440)}
                seen, frames, images, total = set(), [], [], 0
                for frame in capture.frames:
                    slot = (frame.kind, frame.width, frame.sku)
                    if slot not in wanted or slot in seen or type(frame.width) is not int or frame.height != 900:
                        raise ValueError('Unexpected screenshot')
                    seen.add(slot); total += len(frame.content)
                    if total > MAX_CAPTURE_BYTES:
                        raise ValueError('Capture exceeds limit')
                    self._png(frame, frame.content)
                    identity = digest([plan_id, 'preview-frame', code.source_digest, frame.sha256, slot])
                    summary = StorePreviewFrame(id=identity, kind=frame.kind, width=frame.width,
                        height=frame.height, sha256=frame.sha256, sku=frame.sku)
                    frames.append(summary)
                    images.append(StorePreviewImage(frame=summary, png_base64=base64.b64encode(frame.content).decode()))
                if capture.passed != (all(capture.checks.values()) and seen == wanted):
                    raise ValueError('Pass summary contradicts evidence')
                report = StorePreview(id='0' * 64, project_id=project_id, plan_id=plan_id, plan_revision=revision,
                    source_digest=code.source_digest, snapshot_hash=capture.snapshot_hash, frames=frames,
                    checks=capture.checks, diagnostics=list(capture.diagnostics), passed=capture.passed)
                report.id = digest([binding, report.model_dump(mode='json', exclude={'id'})])
                value = {'binding': binding, 'report': report.model_dump(mode='json')}
                count = conn.execute(text("SELECT COUNT(*) FROM commerce_artifacts WHERE plan_id=:plan AND kind='commerce_preview'"),
                                     {'plan': plan_id}).scalar()
                exists = conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': report.id}).scalar()
                if count >= 10 and not exists:
                    raise ValueError('Capture retention exceeded')
                for identity, kind, payload in [(report.id, 'commerce_preview', value),
                    *((image.frame.id, 'commerce_preview_frame', image.model_dump(mode='json')) for image in images)]:
                    conn.execute(text('INSERT OR IGNORE INTO commerce_artifacts VALUES(:id,:project,:plan,:kind,:digest,:data)'),
                        {'id': identity, 'project': project_id, 'plan': plan_id, 'kind': kind,
                         'digest': digest(payload), 'data': encode(payload)})
                return report
            except (ValueError, TypeError, AttributeError, OSError):
                raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id) from None

    def _report(self, conn, project_id, plan_id, revision, identity=None):
        plan, code, binding = self._source(conn, project_id, plan_id, revision)
        sql = "SELECT id,data,digest FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='commerce_preview'"
        if identity is not None:
            sql += ' AND id=:id'
        sql += ' ORDER BY rowid DESC LIMIT 1'
        row = conn.execute(text(sql), {'project': project_id, 'plan': plan_id, 'id': identity}).mappings().first()
        if row is None:
            raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
        try:
            value = json.loads(row['data']); report = StorePreview.model_validate(value['report'])
            if (set(value) != {'binding', 'report'} or digest(value) != row['digest'] or value['binding'] != binding
                    or report.id != row['id'] or report.project_id != project_id or report.plan_id != plan_id
                    or report.source_digest != code.source_digest
                    or report.id != digest([binding, report.model_dump(mode='json', exclude={'id'})])):
                raise ValueError('Stored preview differs')
            return report.model_copy(update={'plan_revision': plan.revision})
        except (ValueError, TypeError, KeyError):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id) from None

    def latest(self, project_id, plan_id, revision):
        with self.repo.db.transaction() as conn:
            return self._report(conn, project_id, plan_id, revision)

    def image(self, project_id, plan_id, preview_id, frame_id, revision):
        with self.repo.db.transaction() as conn:
            report = self._report(conn, project_id, plan_id, revision, preview_id)
            frame = next((frame for frame in report.frames if frame.id == frame_id), None)
            if frame is None:
                raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
            row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='commerce_preview_frame'"),
                               {'id': frame_id, 'project': project_id, 'plan': plan_id}).mappings().first()
            try:
                if row is None:
                    raise ValueError('Screenshot missing')
                value = json.loads(row['data']); image = StorePreviewImage.model_validate(value)
                if digest(value) != row['digest'] or image.frame != frame:
                    raise ValueError('Screenshot differs')
                self._png(frame, base64.b64decode(image.png_base64, validate=True))
                return image
            except (ValueError, TypeError, OSError):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id) from None
