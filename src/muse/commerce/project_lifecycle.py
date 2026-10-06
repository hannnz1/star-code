"""Local project lifecycle. Never contacts connectors or deletes workspace files."""
import json
import time
from sqlalchemy import text
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import StoreProject


class ProjectLifecycleMixin:
    def list_archived_projects(self):
        return [StoreProject.model_validate_json(row['data']) for row in self.db.rows(
            "SELECT p.data FROM commerce_projects p WHERE EXISTS (SELECT 1 FROM commerce_artifacts a "
            "WHERE a.project_id=p.id AND a.kind='project_archive') ORDER BY p.created_at,p.id")]

    def _lifecycle_project(self, conn, project_id, expected_revision):
        row = conn.execute(text('SELECT data,revision FROM commerce_projects WHERE id=:id'), {'id':project_id}).mappings().first()
        if not row: raise CommerceFailure('NOT_FOUND', 404)
        if row['revision'] != expected_revision: raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return StoreProject.model_validate_json(row['data'])

    def _require_idle(self, conn, project_id):
        params = {'id':project_id}
        # Descendants may continue even when the parent has already finished.
        active = conn.execute(text("""WITH RECURSIVE related(id) AS (
            SELECT root_task_id FROM commerce_plans WHERE project_id=:id AND root_task_id IS NOT NULL
            UNION SELECT id FROM tasks WHERE json_extract(checkpoint,'$.commerce.project_id')=:id
            UNION SELECT s.task_id FROM commerce_steps s JOIN commerce_plans p ON p.id=s.plan_id
                WHERE p.project_id=:id AND s.task_id IS NOT NULL
            UNION SELECT t.id FROM tasks t JOIN related r ON t.parent_task_id=r.id)
            SELECT 1 FROM tasks WHERE id IN (SELECT id FROM related)
            AND (status NOT IN ('SUCCEEDED','FAILED','CANCELLED') OR EXISTS
                (SELECT 1 FROM tool_calls c WHERE c.task_id=tasks.id AND c.status IN ('UNKNOWN','PREPARED','RUNNING'))) LIMIT 1"""), params).first()
        busy = bool(active)
        for row in conn.execute(text('SELECT data FROM commerce_plans WHERE project_id=:id'), params):
            value = json.loads(row[0])
            busy |= value.get('state') in {'BUILDING','VERIFYING','PUBLISHING','PARTIAL','NEEDS_RECONCILIATION'}
            busy |= any(step.get('status') == 'RUNNING' for step in value.get('steps', []))
        for row in conn.execute(text('SELECT kind,data FROM commerce_artifacts WHERE project_id=:id'), params):
            # Idempotency pointer, not an executable job. The job row is checked separately.
            if row[0] == 'verification_request': continue
            try: value = json.loads(row[1])
            except (ValueError, TypeError):
                raise CommerceFailure('PROJECT_BUSY', project_id=project_id) from None
            if not isinstance(value, dict): continue
            busy |= value.get('state') in {'QUEUED','RUNNING','RESERVED','UNKNOWN','CLEANUP_UNKNOWN','NEEDS_RECONCILIATION','PUBLISHING','PARTIAL','PREPARED'}
            busy |= value.get('status') in {'QUEUED','RUNNING','ARMED','APPLYING'}
            busy |= value.get('phase') == 'PUBLISHING'
            busy |= row[0] == 'verification_job' and bool(value.get('active'))
            # Preserve the only cleanup handle for provisioned Docker environments.
            busy |= row[0] == 'reference_job' and value.get('state') != 'CLEANED'
        busy |= bool(conn.execute(text("SELECT 1 FROM commerce_task_drafts WHERE project_id=:id AND json_extract(data,'$.status')='QUEUED' LIMIT 1"), params).first())
        busy |= bool(conn.execute(text("SELECT 1 FROM commerce_receipts r JOIN commerce_changesets c ON c.id=r.changeset_id WHERE c.project_id=:id AND r.state NOT IN ('SUCCEEDED','FAILED','STALE') LIMIT 1"), params).first())
        if busy: raise CommerceFailure('PROJECT_BUSY', project_id=project_id)

    def archive_project(self, project_id, expected_revision):
        from muse.commerce.repository import encode, digest
        with self.db.transaction() as conn:
            project = self._lifecycle_project(conn, project_id, expected_revision)
            if conn.execute(text("SELECT 1 FROM commerce_artifacts WHERE project_id=:id AND kind='project_archive'"), {'id':project_id}).first():
                return project
            self._require_idle(conn, project_id)
            saved = project.model_copy(update={'revision':project.revision + 1})
            marker = {'archived_at':time.time()}
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:key,:id,NULL,'project_archive',:digest,:data)"),
                         {'key':'project-archive-'+project_id, 'id':project_id, 'digest':digest(marker), 'data':encode(marker)})
            conn.execute(text('UPDATE commerce_projects SET revision=:revision,data=:data WHERE id=:id'),
                         {'revision':saved.revision, 'data':encode(saved), 'id':project_id})
            self.event(conn, project_id, 'project_archived', {'revision':saved.revision})
            return saved

    def restore_project(self, project_id, expected_revision):
        from muse.commerce.repository import encode
        with self.db.transaction() as conn:
            project = self._lifecycle_project(conn, project_id, expected_revision)
            removed = conn.execute(text("DELETE FROM commerce_artifacts WHERE project_id=:id AND kind='project_archive'"), {'id':project_id})
            if not removed.rowcount: return project
            saved = project.model_copy(update={'revision':project.revision + 1})
            conn.execute(text('UPDATE commerce_projects SET revision=:revision,data=:data WHERE id=:id'),
                         {'revision':saved.revision, 'data':encode(saved), 'id':project_id})
            self.event(conn, project_id, 'project_restored', {'revision':saved.revision})
            return saved

    def delete_project(self, project_id, expected_revision, confirmation_name):
        with self.db.transaction() as conn:
            project = self._lifecycle_project(conn, project_id, expected_revision)
            if confirmation_name != project.brief.brand_name: raise CommerceFailure('INPUT_INVALID', 422)
            self._require_idle(conn, project_id)
            params = {'id':project_id}
            # All business records in one SQLite transaction; runtime logs are preserved.
            for table in ('commerce_receipts','commerce_approvals'):
                conn.execute(text(f'DELETE FROM {table} WHERE changeset_id IN (SELECT id FROM commerce_changesets WHERE project_id=:id)'), params)
            conn.execute(text('DELETE FROM commerce_steps WHERE plan_id IN (SELECT id FROM commerce_plans WHERE project_id=:id)'), params)
            for table in ('commerce_design_heads','commerce_design_versions','commerce_artifacts','commerce_events','commerce_task_drafts','commerce_plan_labels',
                          'commerce_changesets','commerce_snapshots','commerce_plans','commerce_projects'):
                column = 'id' if table == 'commerce_projects' else 'project_id'
                conn.execute(text(f'DELETE FROM {table} WHERE {column}=:id'), params)
