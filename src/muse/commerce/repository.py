"""Revision-bound merchant projects backed by the runtime's SQLite store."""
import hashlib
import json
import time
import uuid
from contextlib import nullcontext

from sqlalchemy import text

from muse.commerce.connections import ConnectionRepositoryMixin
from muse.commerce.project_lifecycle import ProjectLifecycleMixin
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    CommercePlan,
    ImportedProducts,
    SiteBrief,
    StoreProject,
    StoreSnapshot,
)


def encode(value) -> str:
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


class CommerceRepository(ProjectLifecycleMixin, ConnectionRepositoryMixin):
    def __init__(self, runtime):
        self.runtime, self.db = runtime, runtime.db

    def create_project(self, workspace_id: str, brief: SiteBrief, client_request_id: str) -> StoreProject:
        fingerprint = digest({'workspace_id': workspace_id, 'brief': brief.model_dump(mode='json')})
        with self.db.transaction() as conn:
            existing = conn.execute(text('SELECT * FROM commerce_projects WHERE request_id=:key'),
                                    {'key': client_request_id}).mappings().first()
            if existing:
                if existing['request_digest'] != fingerprint:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return StoreProject.model_validate_json(existing['data'])
            if not conn.execute(text('SELECT 1 FROM workspaces WHERE id=:id'), {'id': workspace_id}).first():
                raise CommerceFailure('NOT_FOUND', 404)
            project = StoreProject(id=uuid.uuid4().hex, workspace_id=workspace_id, brief=brief)
            conn.execute(text('INSERT INTO commerce_projects VALUES(:id,:ws,:key,:digest,1,:data,:now)'),
                         {'id': project.id, 'ws': workspace_id, 'key': client_request_id,
                          'digest': fingerprint, 'data': encode(project), 'now': time.time()})
            self.event(conn, project.id, 'project_created', {'revision': 1})
            return project

    def get_project(self, project_id: str) -> StoreProject:
        if self.db.rows("SELECT 1 FROM commerce_artifacts WHERE project_id=:id AND kind='project_archive'", {'id':project_id}):
            raise CommerceFailure('PROJECT_ARCHIVED', project_id=project_id)
        rows = self.db.rows('SELECT data FROM commerce_projects WHERE id=:id', {'id': project_id})
        if not rows:
            raise CommerceFailure('NOT_FOUND', 404)
        return StoreProject.model_validate_json(rows[0]['data'])

    def list_projects(self) -> list[StoreProject]:
        return [StoreProject.model_validate_json(row['data'])
                for row in self.db.rows("SELECT p.data FROM commerce_projects p WHERE NOT EXISTS (SELECT 1 FROM commerce_artifacts a WHERE a.project_id=p.id AND a.kind='project_archive') ORDER BY p.created_at,p.id")]

    def update_brief(self, project_id: str, brief: SiteBrief, expected_revision: int) -> StoreProject:
        with self.db.transaction() as conn:
            row = conn.execute(text('SELECT * FROM commerce_projects WHERE id=:id'), {'id': project_id}).mappings().first()
            if not row:
                raise CommerceFailure('NOT_FOUND', 404)
            if row['revision'] != expected_revision:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            project = StoreProject.model_validate_json(row['data']).model_copy(
                update={'brief': brief, 'revision': expected_revision + 1})
            conn.execute(text('UPDATE commerce_projects SET revision=:revision,data=:data WHERE id=:id'),
                         {'revision': project.revision, 'data': encode(project), 'id': project_id})
            self._invalidate(conn, project_id)
            self.event(conn, project_id, 'brief_updated', {'revision': project.revision})
            return project

    def save_plan(self, plan: CommercePlan, expected_revision: int) -> CommercePlan:
        with self.db.transaction() as conn:
            if not conn.execute(text('SELECT 1 FROM commerce_projects WHERE id=:id'), {'id': plan.project_id}).first():
                raise CommerceFailure('NOT_FOUND', 404)
            current = conn.execute(text('SELECT * FROM commerce_plans WHERE id=:id'), {'id': plan.id}).mappings().first()
            if current and (current['project_id'] != plan.project_id or current['revision'] != expected_revision):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
            if current is None and expected_revision != 0:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
            saved = plan.model_copy(update={'revision': expected_revision + 1})
            if current:
                conn.execute(text('UPDATE commerce_plans SET revision=:revision,data=:data WHERE id=:id'),
                             {'id': saved.id, 'revision': saved.revision, 'data': encode(saved)})
            else:
                conn.execute(text('INSERT INTO commerce_plans VALUES(:id,:project,:request,:digest,:revision,:data,NULL)'),
                             {'id': saved.id, 'project': saved.project_id, 'request': saved.id, 'digest': digest(saved),
                              'revision': saved.revision, 'data': encode(saved)})
            self.event(conn, plan.project_id, 'plan_saved', {'plan_id': saved.id, 'revision': saved.revision})
            return saved

    def get_plan(self, plan_id: str, *, project_id: str) -> CommercePlan:
        rows = self.db.rows('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project',
                            {'id': plan_id, 'project': project_id})
        if not rows:
            raise CommerceFailure('NOT_FOUND', 404)
        return CommercePlan.model_validate_json(rows[0]['data'])

    def list_plans(self, project_id: str) -> list[CommercePlan]:
        self.get_project(project_id)
        return [CommercePlan.model_validate_json(row['data'])
                for row in self.db.rows('SELECT data FROM commerce_plans WHERE project_id=:id ORDER BY rowid', {'id': project_id})]

    def import_products(self, project_id: str, csv_text: str, request_id: str, expected_revision: int, *, media_ids=()) -> ImportedProducts:
        from muse.commerce.products import parse_products
        raw = csv_text.encode('utf-8')
        csv_hash = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256(encode([project_id, 'product_import', request_id]).encode()).hexdigest()
        media_ids = list(media_ids)
        if len(media_ids) > 100 or len(set(media_ids)) != len(media_ids):
            raise CommerceFailure('INPUT_INVALID', 422)
        binding_id = digest([identity, 'media_binding'])
        with self.db.transaction() as conn:
            row = conn.execute(text('SELECT data,revision FROM commerce_projects WHERE id=:id'), {'id': project_id}).mappings().first()
            if not row:
                raise CommerceFailure('NOT_FOUND', 404)
            if row['revision'] != expected_revision:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            existing = conn.execute(text("SELECT data FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='product_import'"),
                                    {'id': identity, 'project': project_id}).scalar()
            if existing:
                previous = ImportedProducts.model_validate_json(existing)
                binding = conn.execute(text("SELECT data FROM commerce_artifacts WHERE id=:id AND kind='product_import_media'"), {'id': binding_id}).scalar()
                previous_media = json.loads(binding)['media_ids'] if binding else []
                if previous.csv_sha256 != csv_hash or previous.project_revision != expected_revision or previous_media != media_ids:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return previous
            project = StoreProject.model_validate_json(row['data'])
            from muse.commerce.media import MediaRepository
            images = [MediaRepository._read(conn, project_id, media_id)[0].image for media_id in media_ids]
            # Image facts are locally validated; remote SKU absence still needs publication-time proof.
            result = parse_products(raw, images, project.brief.currency)
            if result.errors:
                error = CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
                error.public.field_errors = [item.model_dump() for item in result.errors]
                raise error
            record = ImportedProducts(id=identity, project_id=project_id, project_revision=expected_revision,
                                      csv_sha256=csv_hash, result=result)
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'product_import',:digest,:data)"),
                         {'id': identity, 'project': project_id, 'digest': digest(record), 'data': encode(record)})
            binding = {'media_ids': media_ids}
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'product_import_media',:digest,:data)"),
                         {'id': binding_id, 'project': project_id, 'digest': digest(binding), 'data': encode(binding)})
            self.event(conn, project_id, 'products_imported', {'import_id': record.id, 'count': len(result.drafts),
                       'project_revision': expected_revision, 'store_conflicts_checked': False})
            return record

    def list_product_imports(self, project_id: str) -> list[ImportedProducts]:
        self.get_project(project_id)
        return [ImportedProducts.model_validate_json(row['data']) for row in self.db.rows(
            "SELECT data FROM commerce_artifacts WHERE project_id=:id AND kind='product_import' ORDER BY rowid", {'id': project_id})]

    def create_site_blueprint(self, project_id: str, request_id: str, expected_revision: int, *, _connection=None) -> CommercePlan:
        from muse.commerce.site import build_site_blueprint
        identity = hashlib.sha256(encode([project_id, 'build_site', request_id]).encode()).hexdigest()
        with self.db.transaction() if _connection is None else nullcontext(_connection) as conn:
            project = self._project(conn, project_id, expected_revision)
            existing = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
                                    {'id': identity, 'project': project_id}).scalar()
            if existing and CommercePlan.model_validate_json(existing).state in {'STALE', 'CANCELLED'}:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            current = self.current_site_draft(conn, project_id)
            if current:
                return current
            context = self._context(conn, project, 'staging')
            snapshot = context.snapshot if context else StoreSnapshot(project_id=project_id, environment='staging')
            # A snapshot can ground the draft, but does not imply staging or purchase verification.
            blueprint = build_site_blueprint(project.brief, snapshot)
            plan = CommercePlan(id=identity, project_id=project_id, kind='build_site', state='NEEDS_INPUT', blueprint=blueprint,
                                snapshot_hash=context.snapshot_hash if context else None,
                                content_hash=digest({'project_revision': expected_revision, 'brief': project.brief.model_dump(mode='json'),
                                                     'blueprint': blueprint.model_dump(mode='json')}))
            conn.execute(text('INSERT INTO commerce_plans VALUES(:id,:project,:request,:digest,1,:data,NULL)'),
                         {'id': plan.id, 'project': project_id, 'request': identity, 'digest': digest(plan), 'data': encode(plan)})
            self.event(conn, project_id, 'blueprint_prepared', {'plan_id': plan.id, 'project_revision': expected_revision,
                                                              'state': 'NEEDS_INPUT', 'content_hash': plan.content_hash})
            return plan

    @staticmethod
    def current_site_draft(conn, project_id: str) -> CommercePlan | None:
        rows = conn.execute(text('SELECT data FROM commerce_plans WHERE project_id=:id AND root_task_id IS NULL ORDER BY rowid DESC'),
                            {'id': project_id}).scalars()
        for raw in rows:
            plan = CommercePlan.model_validate_json(raw)
            if plan.kind == 'build_site' and plan.blueprint and not plan.steps and plan.state == 'NEEDS_INPUT':
                return plan
        return None

    def edit_site_blueprint(self, project_id, plan_id, expected_revision, expected_plan_revision, pages, navigation):
        with self.db.transaction() as conn:
            self._project(conn, project_id, expected_revision)
            current = self.current_site_draft(conn, project_id)
            if current is None or current.id != plan_id or current.revision != expected_plan_revision:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            current.blueprint.pages = pages
            current.blueprint.navigation = navigation
            current.revision += 1
            current.content_hash = digest({'project_revision': expected_revision, 'blueprint': current.blueprint.model_dump(mode='json')})
            conn.execute(text('UPDATE commerce_plans SET data=:data,revision=:revision WHERE id=:id AND project_id=:project'),
                         {'data': encode(current), 'revision': current.revision, 'id': current.id, 'project': project_id})
            self.event(conn, project_id, 'blueprint_edited', {'plan_id': current.id, 'revision': current.revision,
                       'project_revision': expected_revision, 'content_hash': current.content_hash})
            return current

    @staticmethod
    def event(conn, project_id: str, kind: str, data: dict):
        sequence = conn.execute(text('SELECT COALESCE(MAX(sequence),0)+1 FROM commerce_events WHERE project_id=:id'),
                                {'id': project_id}).scalar_one()
        conn.execute(text('INSERT INTO commerce_events VALUES(:id,:sequence,:kind,:data,:now)'),
                     {'id': project_id, 'sequence': sequence, 'kind': kind, 'data': encode(data), 'now': time.time()})

    def events(self, project_id: str, after: int = 0) -> list[dict]:
        self.get_project(project_id)
        rows = self.db.rows('SELECT sequence,kind,data,created_at FROM commerce_events WHERE project_id=:id AND sequence>:after ORDER BY sequence',
                            {'id': project_id, 'after': after})
        return [{**row, 'data': json.loads(row['data'])} for row in rows]
