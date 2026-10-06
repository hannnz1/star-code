"""Bounded offline recovery. Never extract paths or restore execution authority.

New projects have no connections, snapshots, tasks, grants or active plans.
Theme bytes are unverified sources; independent staging/approval is required.
"""
import base64
import csv
import hashlib
import io
import json
import re
import stat
import time
import uuid
import zipfile

from PIL import Image
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.export import MAX_EXPORT, MAX_RECORDS
from muse.commerce.models import (
    ExportManifest,
    ImportedProducts,
    MediaInput,
    ProductDraft,
    ProjectMedia,
    RestoredProject,
    RestoredThemeSource,
    RestoredThemeSummary,
    SiteBrief,
    SitePackage,
    StoreProject,
)
from muse.commerce.products import COLUMNS, parse_products, validate_media
from muse.commerce.repository import digest, encode
from muse.commerce.theme import validate_site_archive

BASE_FILES = {'manifest.json', 'project.json', 'plans.json', 'products.json', 'README.txt'}


def _json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def _archive(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_EXPORT:
        raise ValueError('Invalid archive size')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if not 5 <= len(entries) <= 307 or sum(item.file_size for item in entries) > MAX_EXPORT:
            raise ValueError('Archive size exceeded')
        files = {}
        for item in entries:
            name = item.filename
            if (name in files or item.flag_bits & 1 or item.is_dir() or stat.S_ISLNK(item.external_attr >> 16)
                    or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or (name not in BASE_FILES | {'media.json', 'design.json'}
                        and not re.fullmatch(r'(?:media/[0-9]{4}\.(?:png|jpg|webp)|themes/[0-9]{4}\.(?:zip|json))', name))):
                raise ValueError('Unsupported export entry')
            files[name] = archive.read(item)
    if not BASE_FILES <= files.keys():
        raise ValueError('Incomplete archive')
    manifest_raw = _json(files['manifest.json'])
    manifest = ExportManifest.model_validate(manifest_raw)
    paths = set()
    for item in manifest_raw['files_manifest']:
        if (set(item) != {'path', 'sha256', 'bytes'} or type(item['bytes']) is not int
                or item['path'] in paths or item['path'] == 'manifest.json' or item['path'] not in files
                or len(files[item['path']]) != item['bytes']
                or hashlib.sha256(files[item['path']]).hexdigest() != item['sha256']):
            raise ValueError('Export checksum mismatch')
        paths.add(item['path'])
    if paths != files.keys() - {'manifest.json'}:
        raise ValueError('Incomplete checksum manifest')
    return files, manifest


class ProjectRestorer:
    def __init__(self, commerce):
        self.commerce, self.db = commerce, commerce.db

    def restore(self, workspace_id, archive, client_request_id):
        if (not isinstance(workspace_id, str) or not workspace_id or not isinstance(client_request_id, str)
                or not 1 <= len(client_request_id) <= 200):
            raise CommerceFailure('INPUT_INVALID', 422)
        try:
            prepared = self._prepare(archive)
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError,
                OSError, RuntimeError, zipfile.BadZipFile, OverflowError):
            raise CommerceFailure('INPUT_INVALID', 422) from None
        return self._persist(workspace_id, archive, client_request_id, prepared)

    @staticmethod
    def _prepare(archive):
        files, manifest = _archive(archive)
        project = _json(files['project.json'])
        if (set(project) != {'format_version', 'project_id', 'revision', 'platform', 'brief', 'deployment_verified'}
                or type(project['format_version']) is not int or project['format_version'] not in {1, 2, 3, 4}
                or type(project['revision']) is not int or project['revision'] < 1
                or project['platform'] != 'wordpress' or project['deployment_verified'] is not False
                or manifest.project_id != project['project_id'] or manifest.revision != project['revision']
                or manifest.required_versions != {'export_format': str(project['format_version'])}):
            raise ValueError('Invalid project identity')
        brief = SiteBrief.model_validate(project['brief'])
        plans = _json(files['plans.json'])
        products = _json(files['products.json'])
        if (not isinstance(plans, list) or not isinstance(products, list)
                or max(len(plans), len(products)) > MAX_RECORDS):
            raise ValueError('Invalid record count')
        media = _json(files['media.json']) if 'media.json' in files else []
        if (not isinstance(media, list) or len(media) > 100
                or (project['format_version'] not in {3,4} and bool(media) != (project['format_version'] == 2))):
            raise ValueError('Invalid media format')
        media_ids, names, hashes, media_paths = set(), set(), set(), set()
        images = []
        for entry in media:
            if set(entry) != {'media_id', 'image', 'width', 'height', 'path'}:
                raise ValueError('Invalid media index')
            image = MediaInput.model_validate(entry['image'])
            if (image.artifact_ref != entry['media_id'] or entry['path'] not in files
                    or entry['media_id'] in media_ids or image.name.casefold() in names or image.sha256 in hashes
                    or entry['path'] in media_paths or not re.fullmatch(r'media/[0-9]{4}\.(png|jpg|webp)', entry['path'])):
                raise ValueError('Ambiguous media reference')
            content = files[entry['path']]
            checked = validate_media(image.name, image.mime_type, content, image.artifact_ref)
            if checked != image:
                raise ValueError('Media hash mismatch')
            with Image.open(io.BytesIO(content)) as picture:
                if (type(entry['width']) is not int or type(entry['height']) is not int
                        or picture.size != (entry['width'], entry['height']) or picture.getexif()
                        or getattr(picture, 'text', {})
                        or any(picture.info.get(key) for key in ('exif', 'icc_profile', 'xmp', 'XML:com.adobe.xmp'))):
                    raise ValueError('Unclean image metadata')
            media_ids.add(entry['media_id']); names.add(image.name.casefold()); hashes.add(image.sha256)
            media_paths.add(entry['path'])
            images.append((entry, image, content))
        if media_paths != {name for name in files if name.startswith('media/')}:
            raise ValueError('Unindexed media')
        by_id = {image.artifact_ref: image for _, image, _ in images}
        design = None
        if ('design.json' in files) != (project['format_version'] == 4):
            raise ValueError('Design format differs')
        if 'design.json' in files:
            from muse.commerce.design_models import StoreDesignDocument
            design = StoreDesignDocument.model_validate(_json(files['design.json']))
            if design.project_id != project['project_id'] or design.project_revision != project['revision']:
                raise ValueError('Design project differs')
            if any(section.props.media_id and section.props.media_id not in by_id for section in design.home_sections):
                raise ValueError('Design image is missing')
        batches = []
        import_ids = set()
        for batch in products:
            if (set(batch) != {'import_id', 'project_revision', 'drafts', 'store_conflicts_checked'}
                    or batch['project_revision'] != project['revision'] or type(batch['project_revision']) is not int
                    or not isinstance(batch['import_id'], str) or batch['import_id'] in import_ids
                    or type(batch['store_conflicts_checked']) is not bool or not isinstance(batch['drafts'], list)
                    or not 1 <= len(batch['drafts']) <= 20):
                raise ValueError('Invalid product batch')
            drafts = [ProductDraft.model_validate(item) for item in batch['drafts']]
            stream = io.StringIO(newline='')
            writer = csv.writer(stream); writer.writerow(COLUMNS)
            selected = set()
            for product in drafts:
                if (product.currency != brief.currency or len(set(product.media_refs)) != len(product.media_refs)
                        or not set(product.media_refs) <= by_id.keys()):
                    raise ValueError('Invalid product facts or images')
                selected.update(product.media_refs)
                writer.writerow([product.sku, product.title, str(product.price), product.currency, product.stock,
                                 product.category, product.description, '|'.join(by_id[ref].name for ref in product.media_refs)])
            validated = parse_products(stream.getvalue().encode(), [by_id[ref] for ref in sorted(selected)], brief.currency)
            if validated.errors or len(validated.drafts) != len(drafts):
                raise ValueError('Invalid product facts')
            import_ids.add(batch['import_id']); batches.append(drafts)
        themes = []
        theme_paths = {name for name in files if name.startswith('themes/')}
        for name in sorted(theme_paths):
            if not name.endswith('.json'):
                continue
            metadata = _json(files[name])
            restored = set(metadata) == {'source_id', 'package', 'verified_for_deployment'}
            if (metadata.get('verified_for_deployment') is not False
                    or (restored and (project['format_version'] not in {3,4}
                        or not isinstance(metadata['source_id'], str) or not metadata['source_id']))
                    or (not restored and (set(metadata) != {'plan_id', 'plan_revision', 'package', 'verified_for_deployment'}
                        or type(metadata['plan_revision']) is not int or metadata['plan_revision'] < 1))):
                raise ValueError('Invalid theme metadata')
            package = SitePackage.model_validate(metadata['package'])
            payload = files[name.removesuffix('.json') + '.zip']
            validate_site_archive(payload, package)
            if not restored:
                matches = [plan for plan in plans if isinstance(plan, dict) and plan.get('id') == metadata['plan_id']]
                if (len(matches) != 1 or matches[0].get('kind') != 'build_site'
                        or matches[0].get('project_id') != project['project_id']
                        or matches[0].get('revision') != metadata['plan_revision']
                        or matches[0].get('code_revision') != package.code_revision
                        or matches[0].get('content_hash') != package.content_sha256):
                    raise ValueError('Theme source does not match exported plan')
            themes.append((package, payload))
        if len(theme_paths) != 2 * len(themes):
            raise ValueError('Unpaired theme package')
        return brief, images, batches, themes, design

    @staticmethod
    def _theme_source(conn, project_id, source_id, expected_digest=None):
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='restored_theme_source'"),
                           {'id': source_id, 'project': project_id}).mappings().first()
        if row is None:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            value = _json(row['data'].encode())
            package = SitePackage.model_validate(value['package'])
            content = base64.b64decode(value['archive_base64'], validate=True)
            if (set(value) != {'package', 'archive_base64', 'deployment_verified'} or digest(value) != row['digest']
                    or value['deployment_verified'] is not False
                    or (expected_digest is not None and expected_digest != row['digest'])):
                raise ValueError('Source changed')
            validate_site_archive(content, package)
            return RestoredThemeSource(id=source_id, project_id=project_id, package=package,
                                       archive_base64=value['archive_base64']), row['digest']
        except (ValueError, KeyError, TypeError, OSError):
            raise CommerceFailure('RESOURCE_CONFLICT') from None

    def list_theme_sources(self, project_id):
        with self.db.transaction() as conn:
            self.commerce._project(conn, project_id)
            identities = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND kind='restored_theme_source' ORDER BY id LIMIT :limit"),
                {'project': project_id, 'limit': MAX_RECORDS + 1}).scalars().all()
            if len(identities) > MAX_RECORDS:
                raise CommerceFailure('INPUT_INVALID', 422)
            return [RestoredThemeSummary.model_validate(self._theme_source(conn, project_id, identity)[0].model_dump(
                        mode='json', exclude={'archive_base64'})) for identity in identities]

    def theme_source(self, project_id, source_id):
        with self.db.transaction() as conn:
            self.commerce._project(conn, project_id)
            return self._theme_source(conn, project_id, source_id)[0]

    def _persist(self, workspace_id, archive, request_id, prepared):
        brief, images, batches, themes, design = prepared
        identity = 'restore-' + digest([workspace_id, request_id])
        fingerprint = digest([workspace_id, hashlib.sha256(archive).hexdigest()])
        with self.db.transaction() as conn:
            if not conn.execute(text('SELECT 1 FROM workspaces WHERE id=:id'), {'id': workspace_id}).first():
                raise CommerceFailure('NOT_FOUND', 404)
            row = conn.execute(text('SELECT * FROM commerce_projects WHERE request_id=:id'), {'id': identity}).mappings().first()
            if row:
                if row['request_digest'] != fingerprint:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                receipt = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE project_id=:project AND kind='project_restore_receipt'"),
                                       {'project': row['id']}).mappings().one()
                value = _json(receipt['data'].encode())
                if digest(value) != receipt['digest']:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return RestoredProject.model_validate(value)
            project = StoreProject(id=uuid.uuid4().hex, workspace_id=workspace_id, brief=brief)
            conn.execute(text('INSERT INTO commerce_projects VALUES(:id,:ws,:key,:digest,1,:data,:now)'),
                         {'id': project.id, 'ws': workspace_id, 'key': identity, 'digest': fingerprint,
                          'data': encode(project), 'now': time.time()})
            def insert(kind, key, value):
                conn.execute(text('INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,:kind,:digest,:data)'),
                             {'id': key, 'project': project.id, 'kind': kind, 'digest': digest(value), 'data': encode(value)})
            mapping = {}
            for entry, image, content in images:
                key = digest([project.id, 'image', image.sha256])
                record = ProjectMedia(id=key, project_id=project.id, project_revision=1,
                    image=image.model_copy(update={'artifact_ref': key}), width=entry['width'], height=entry['height'])
                insert('product_media', key, {'record': record.model_dump(mode='json'),
                                            'content_base64': base64.b64encode(content).decode('ascii')})
                mapping[entry['media_id']] = key
            if design is not None:
                restored_design = design.model_copy(deep=True)
                restored_design.project_id = project.id
                restored_design.project_revision = restored_design.revision = 1
                restored_design.blueprint_plan_id = 'restored-unbound'
                restored_design.blueprint_revision = 1
                for section in restored_design.home_sections:
                    if section.props.media_id:
                        section.props.media_id = mapping[section.props.media_id]
                conn.execute(text('INSERT INTO commerce_design_versions VALUES(:project,1,:data,:digest,:request,:fingerprint)'),
                    {'project':project.id,'data':encode(restored_design),'digest':digest(restored_design),
                     'request':'restore','fingerprint':fingerprint})
                conn.execute(text('INSERT INTO commerce_design_heads VALUES(:project,1)'), {'project':project.id})
            imports = []
            for ordinal, drafts in enumerate(batches):
                key = digest([project.id, 'restored_products', ordinal])
                remapped = [p.model_copy(update={'media_refs': [mapping[ref] for ref in p.media_refs]}) for p in drafts]
                record = ImportedProducts(id=key, project_id=project.id, project_revision=1,
                    csv_sha256=digest([p.model_dump(mode='json') for p in remapped]), result={'drafts': remapped})
                insert('product_import', key, record)
                imports.append(key)
            sources = []
            for ordinal, (package, payload) in enumerate(themes):
                key = digest([project.id, 'restored_theme', ordinal])
                insert('restored_theme_source', key, {'package': package.model_dump(mode='json'),
                    'archive_base64': base64.b64encode(payload).decode('ascii'), 'deployment_verified': False})
                sources.append(key)
            result = RestoredProject(project=project, import_ids=imports, media_ids=list(mapping.values()), theme_source_ids=sources)
            insert('project_restore_receipt', digest([project.id, 'restore_receipt']), result)
            self.commerce.event(conn, project.id, 'project_restored', {'archive_sha256': hashlib.sha256(archive).hexdigest(),
                'products_batches': len(imports), 'images': len(mapping), 'themes': len(sources), 'deployment_verified': False})
            return result
