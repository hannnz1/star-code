"""Revision-bound connection references and immutable, sanitized context captures."""
import time
import uuid

from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan, StoreContext, StoreProject


class ConnectionRepositoryMixin:
    @staticmethod
    def _project(conn, project_id, expected_revision=None):
        if conn.execute(text("SELECT 1 FROM commerce_artifacts WHERE project_id=:id AND kind='project_archive'"), {'id':project_id}).first():
            raise CommerceFailure('PROJECT_ARCHIVED', project_id=project_id)
        row = conn.execute(text('SELECT data,revision FROM commerce_projects WHERE id=:id'), {'id': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
        if expected_revision is not None and row['revision'] != expected_revision:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return StoreProject.model_validate_json(row['data'])

    def _invalidate(self, conn, project_id):
        from muse.commerce.repository import encode
        from muse.contracts import TERMINAL
        for row in conn.execute(text('SELECT data,root_task_id FROM commerce_plans WHERE project_id=:id'), {'id': project_id}).mappings():
            plan = CommercePlan.model_validate_json(row['data'])
            if plan.state not in {'CANCELLED', 'SUCCEEDED', 'FAILED', 'STALE'}:
                updated = plan.model_copy(update={'state': 'STALE', 'revision': plan.revision + 1})
                conn.execute(text('UPDATE commerce_plans SET revision=:revision,data=:data WHERE id=:id'),
                    {'id': plan.id, 'revision': updated.revision, 'data': encode(updated)})
                if row['root_task_id']:
                    root = self.runtime._task(conn, row['root_task_id'])
                    self.runtime._cancel_descendants(conn, root['id'], time.time())
                    if root['status'] not in TERMINAL:
                        self.runtime._state(conn, root['id'], 'RUNNING' if root['status'] == 'RUNNING' else 'CANCELLED',
                                            time.time(), cancel_requested=1)
        conn.execute(text("UPDATE commerce_approvals SET status='revoked' WHERE status='approved' AND changeset_id IN (SELECT id FROM commerce_changesets WHERE project_id=:id)"), {'id': project_id})

    def binding_receipt(self, project_id, request_id, request_digest):
        from muse.commerce.repository import digest
        identity = digest([project_id, 'connection_binding', request_id])
        rows = self.db.rows("SELECT digest,data FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='connection_binding'",
                            {'id': identity, 'project': project_id})
        if not rows:
            return None
        if rows[0]['digest'] != request_digest:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return StoreProject.model_validate_json(rows[0]['data'])

    def attach_connection(self, project_id, reference, request_id, expected_revision):
        from muse.commerce.repository import digest, encode
        request_digest = digest([reference.connector_ref, expected_revision])
        identity = digest([project_id, 'connection_binding', request_id])
        with self.db.transaction() as conn:
            existing = conn.execute(text("SELECT digest,data FROM commerce_artifacts WHERE id=:id AND kind='connection_binding'"), {'id': identity}).mappings().first()
            if existing:
                if existing['digest'] != request_digest:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return StoreProject.model_validate_json(existing['data'])
            project = self._project(conn, project_id, expected_revision)
            if reference.project_id != project_id:
                raise CommerceFailure('PERMISSION_DENIED', 403, project_id=project_id)
            refs = [ref for ref in project.environment_refs if ref.environment != reference.environment] + [reference]
            updated = project.model_copy(update={'revision': project.revision + 1, 'environment_refs': refs})
            conn.execute(text('UPDATE commerce_projects SET revision=:revision,data=:data WHERE id=:id'),
                {'id': project_id, 'revision': updated.revision, 'data': encode(updated)})
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'connection_binding',:digest,:data)"),
                {'id': identity, 'project': project_id, 'digest': request_digest, 'data': encode(updated)})
            self._invalidate(conn, project_id)
            self.event(conn, project_id, 'connection_bound', {'connection_id': reference.id, 'environment': reference.environment,
                                                          'project_revision': updated.revision})
            return updated

    @staticmethod
    def _context(conn, project, environment):
        from muse.commerce.repository import digest
        connection = next((ref for ref in project.environment_refs if ref.environment == environment), None)
        if connection is None:
            return None
        for row in conn.execute(text("SELECT data FROM commerce_artifacts WHERE project_id=:id AND kind='store_context' ORDER BY rowid DESC"), {'id': project.id}).mappings():
            context = StoreContext.model_validate_json(row['data'])
            if (context.connection_ref == connection.connector_ref and context.connection_hash == digest(connection)
                    and context.snapshot.environment == environment):
                return context
        return None

    def get_context(self, project_id, environment):
        with self.db.engine.connect() as conn:
            project = self._project(conn, project_id)
            context = self._context(conn, project, environment)
            if context is None:
                raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
            return context

    def save_context(self, project_id, connection_id, snapshot, capabilities, expected_revision):
        from muse.commerce.repository import digest, encode
        with self.db.transaction() as conn:
            project = self._project(conn, project_id, expected_revision)
            ref = next((r for r in project.environment_refs if r.environment == snapshot.environment), None)
            if ref is None or ref.connector_ref != connection_id or snapshot.project_id != project_id:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            fingerprint = digest(snapshot)
            previous = self._context(conn, project, snapshot.environment)
            if previous and previous.snapshot_hash == fingerprint and previous.capabilities == capabilities:
                return previous
            updated = project.model_copy(update={'revision': project.revision + 1})
            context = StoreContext(snapshot_id=uuid.uuid4().hex, snapshot_hash=fingerprint, project_revision=updated.revision,
                                   connection_ref=connection_id, connection_hash=digest(ref), snapshot=snapshot, capabilities=capabilities)
            conn.execute(text('INSERT INTO commerce_snapshots VALUES(:id,:project,:env,:digest,:data,:now)'),
                {'id': context.snapshot_id, 'project': project_id, 'env': snapshot.environment,
                 'digest': fingerprint, 'data': encode(snapshot), 'now': time.time()})
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'store_context',:digest,:data)"),
                {'id': context.snapshot_id, 'project': project_id, 'digest': digest(context), 'data': encode(context)})
            conn.execute(text('UPDATE commerce_projects SET revision=:revision,data=:data WHERE id=:id'),
                {'id': project_id, 'revision': updated.revision, 'data': encode(updated)})
            self._invalidate(conn, project_id)
            self.event(conn, project_id, 'context_refreshed', {'snapshot_id': context.snapshot_id, 'snapshot_hash': fingerprint,
                                                            'environment': snapshot.environment, 'project_revision': updated.revision})
            return context
