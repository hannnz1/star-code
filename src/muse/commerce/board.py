"""Reversible board metadata; never mutates execution or release approval."""
import time

from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan, CommercePlanArchive
from muse.commerce.repository import digest, encode

TERMINAL_PLANS = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE'}


class CommerceBoardRepository:
    def __init__(self, repo):
        self.repo = repo

    def list_archives(self, project_id):
        self.repo.get_project(project_id)
        result = []
        for row in self.repo.db.rows(
            "SELECT data,digest FROM commerce_artifacts WHERE project_id=:project AND kind='plan_archive' ORDER BY id",
            {'project': project_id},
        ):
            value = CommercePlanArchive.model_validate_json(row['data'])
            if digest(value.model_dump(mode='json')) != row['digest']:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            result.append(value)
        return result

    def archive(self, project_id, items, archived):
        if len({item.plan_id for item in items}) != len(items):
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
        with self.repo.db.transaction() as conn:
            self.repo._project(conn, project_id)
            prepared = []
            for item in items:
                raw = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
                                   {'id': item.plan_id, 'project': project_id}).scalar()
                if not raw:
                    raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
                plan = CommercePlan.model_validate_json(raw)
                if plan.revision != item.expected_plan_revision or (archived and plan.state not in TERMINAL_PLANS):
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                identity = digest([project_id, plan.id, 'board-archive'])
                row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='plan_archive'"),
                                   {'id': identity}).mappings().first()
                previous = CommercePlanArchive.model_validate_json(row['data']) if row else None
                if row and digest(previous.model_dump(mode='json')) != row['digest']:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                if (previous.revision if previous else 0) != item.expected_revision or (not archived and not previous):
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                prepared.append((identity, CommercePlanArchive(plan_id=plan.id, project_id=project_id,
                    archived=archived, revision=item.expected_revision + 1, updated_at=time.time())))
            for identity, value in prepared:
                conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'plan_archive',:digest,:data) "
                                  'ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,data=excluded.data'),
                             {'id': identity, 'project': project_id, 'plan': value.plan_id,
                              'digest': digest(value.model_dump(mode='json')), 'data': encode(value)})
                self.repo.event(conn, project_id, 'plan_archived' if archived else 'plan_restored',
                                {'plan_id': value.plan_id, 'revision': value.revision})
            return [value for _, value in prepared]
