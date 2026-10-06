"""Read-only, bounded exports of merchant inputs and deterministic theme sources.

No runtime credentials, raw shop snapshots, customers, orders, grants or task
prompts are read. This is an offline handoff, not an automatic restoration tool.
"""
import base64
import hashlib
import io
import zipfile

from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    CommercePlan,
    ExportManifest,
    ImportedProducts,
    ProjectExport,
    StoreProject,
)
from muse.commerce.repository import digest, encode
from muse.commerce.theme import build_site_archive

MAX_EXPORT = 16 * 1024 * 1024
MAX_RECORDS = 100


class ProjectExporter:
    def __init__(self, repo):
        self.repo = repo

    def export_project(self, project_id: str, revision: int) -> ExportManifest:
        return self.download_project(project_id, revision).manifest

    def download_project(self, project_id: str, revision: int) -> ProjectExport:
        if type(revision) is not int or revision < 1:
            raise CommerceFailure('INPUT_INVALID', 422)
        try:
            return self._build(project_id, revision)
        except (ValueError, TypeError):
            raise CommerceFailure('INPUT_INVALID', 422) from None
        except OSError:
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503) from None

    def _build(self, project_id, revision):
        # One transaction prevents mixing project versions during concurrent edits.
        with self.repo.db.transaction() as conn:
            row = conn.execute(text('SELECT data,revision FROM commerce_projects WHERE id=:id'), {'id': project_id}).mappings().first()
            if row is None:
                raise CommerceFailure('NOT_FOUND', 404)
            project = StoreProject.model_validate_json(row['data'])
            if row['revision'] != revision or project.revision != revision or project.id != project_id:
                raise CommerceFailure('RESOURCE_CONFLICT')
            plan_rows = conn.execute(text('SELECT id,data FROM commerce_plans WHERE project_id=:id ORDER BY id LIMIT :limit'),
                                     {'id': project_id, 'limit': MAX_RECORDS + 1}).mappings().all()
            product_rows = conn.execute(text("SELECT id,data,digest FROM commerce_artifacts WHERE project_id=:id AND kind='product_import' ORDER BY id LIMIT :limit"),
                                        {'id': project_id, 'limit': MAX_RECORDS + 1}).mappings().all()
            if max(len(plan_rows), len(product_rows)) > MAX_RECORDS:
                raise CommerceFailure('INPUT_INVALID', 422)
            plans = [CommercePlan.model_validate_json(row['data']) for row in plan_rows]
            products = [ImportedProducts.model_validate_json(row['data']) for row in product_rows]
            for row, plan in zip(plan_rows, plans, strict=True):
                if plan.project_id != project_id or plan.id != row['id']:
                    raise CommerceFailure('RESOURCE_CONFLICT')
            for row, product in zip(product_rows, products, strict=True):
                if product.project_id != project_id or product.id != row['id'] or digest(product) != row['digest']:
                    raise CommerceFailure('RESOURCE_CONFLICT')
            from muse.commerce.media import MediaRepository
            references = {reference for product in products if product.project_revision == revision
                          for draft in product.result.drafts for reference in draft.media_refs}
            from muse.commerce.design_repository import DesignRepository
            design = DesignRepository.read(conn, project_id)
            if design is not None:
                if design.project_revision != revision:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                references.update(section.props.media_id for section in design.home_sections if section.props.media_id)
            images = []
            for reference in sorted(references):
                images.append(MediaRepository._read(conn, project_id, reference))
                if sum(len(content) for _, content in images) > MAX_EXPORT:
                    raise CommerceFailure('INPUT_INVALID', 422)
            captured_code = {}
            from muse.commerce.code_bridge import load_captured_code
            for plan in plans:
                # Capture and plan are read in the same transaction as the project.
                exists = conn.execute(text("SELECT 1 FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='theme_code_draft'"),
                    {'project': project_id, 'plan': plan.id}).scalar()
                if exists and plan.code_revision:
                    captured_code[plan.id] = load_captured_code(self.repo, plan, connection=conn)
            from muse.commerce.restore import ProjectRestorer
            restored_rows = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND kind='restored_theme_source' ORDER BY id LIMIT :limit"),
                {'project': project_id, 'limit': MAX_RECORDS + 1}).scalars().all()
            if len(restored_rows) > MAX_RECORDS:
                raise CommerceFailure('INPUT_INVALID', 422)
            restored_sources = [ProjectRestorer._theme_source(conn, project_id, identity)[0] for identity in restored_rows]
        # Export explicit public merchant data; never dump the database or workspace.
        files = {}
        def add(name, content):
            if len(content) + sum(map(len, files.values())) > MAX_EXPORT:
                raise CommerceFailure('INPUT_INVALID', 422)
            files[name] = content
        def add_json(name, value):
            add(name, (encode(value) + '\n').encode('utf-8'))
        format_version = 4 if design is not None else (3 if restored_sources else (2 if images else 1))
        if design is not None:
            add_json('design.json', design.model_dump(mode='json'))
        add_json('project.json', {'format_version': format_version, 'project_id': project.id, 'revision': revision,
                                 'platform': project.platform, 'brief': project.brief.model_dump(mode='json'),
                                 'deployment_verified': False})
        add_json('plans.json', [plan.model_dump(mode='json', exclude={'steps'}) for plan in plans])
        add_json('products.json', [{'import_id': product.id, 'project_revision': product.project_revision,
                                   'drafts': [item.model_dump(mode='json') for item in product.result.drafts],
                                   'store_conflicts_checked': product.store_conflicts_checked}
                                  for product in products if product.project_revision == revision])
        media_index = []
        for ordinal, (record, content) in enumerate(images, 1):
            suffix = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[record.image.mime_type]
            path = f'media/{ordinal:04d}.{suffix}'
            add(path, content)
            media_index.append({'media_id': record.id, 'image': record.image.model_dump(mode='json'),
                                'width': record.width, 'height': record.height, 'path': path})
        if images:
            add_json('media.json', media_index)
        index = 0
        for plan in plans:
            if plan.kind != 'build_site' or plan.blueprint is None or plan.code_revision is None:
                continue
            if plan.id in captured_code:
                captured = captured_code[plan.id]
                package, archive = captured.package, captured.archive
            else:
                package, archive = build_site_archive(plan.blueprint, plan.products, code_revision=plan.code_revision)
            if package.content_sha256 != plan.content_hash:
                raise CommerceFailure('REVIEW_STALE')
            index += 1
            # Fixed ordinal paths, never a merchant/Agent-controlled name.
            prefix = f'themes/{index:04d}'
            add(prefix + '.zip', archive)
            add_json(prefix + '.json', {'plan_id': plan.id, 'plan_revision': plan.revision,
                                       'package': package.model_dump(mode='json'), 'verified_for_deployment': False})
        for source in restored_sources:
            index += 1
            prefix = f'themes/{index:04d}'
            add(prefix + '.zip', base64.b64decode(source.archive_base64, validate=True))
            add_json(prefix + '.json', {'source_id': source.id, 'package': source.package.model_dump(mode='json'),
                                       'verified_for_deployment': False})
        add('README.txt', (
            ('MUSE offline project export, format ' + str(format_version) + '.\n').encode('ascii') +
            b'Contains merchant inputs, plan history, current-revision product drafts and reproducible theme sources.\n'
            b'Offline import creates a new unverified project; no deployment approval, platform compatibility or purchase verification is provided.\n'
            b'Stale plans are history, not release candidates. Theme source revisions require independent verification.\n'
            b'Configure credentials separately. Verify exact WordPress/WooCommerce versions, SKU conflicts, staging and purchase flow before use.\n'
            b'Customers, orders, credentials, runtime prompts and execution permits are excluded.\n'
            b'Merchant-supplied text is preserved; remove private content you entered before sharing this archive.\n'
        ))
        manifest = ExportManifest(project_id=project.id, revision=revision, required_versions={'export_format': str(format_version)},
                                  files_manifest=[{'path': name, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
                                                  for name, content in sorted(files.items())])
        add_json('manifest.json', manifest)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
        return ProjectExport(manifest=manifest, archive_base64=base64.b64encode(output.getvalue()).decode('ascii'))
