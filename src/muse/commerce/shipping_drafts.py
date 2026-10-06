"""Revision-bound shipping source using the existing structure and design ledger."""
from sqlalchemy import text

from muse.commerce.design_repository import DesignRepository
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan
from muse.commerce.repository import digest, encode
from muse.commerce.shipping_rules import ShippingRules


class ShippingDraftRepository:
    def __init__(self, repo):
        self.repo = repo

    def get(self, project_id):
        with self.repo.db.transaction() as conn:
            self.repo._project(conn, project_id)
            return self.repo.current_site_draft(conn, project_id)

    def save(self, project_id, project_revision, plan_id, plan_revision, request_id, rules):
        rules = ShippingRules.model_validate(rules.model_dump(mode='json'))
        return self.save_source(project_id, project_revision, plan_id, plan_revision, request_id, 'shipping_rules', rules)

    def save_source(self, project_id, project_revision, plan_id, plan_revision, request_id, setting, value):
        if setting not in {'shipping_rules', 'category_navigation'}:
            raise ValueError('Unsupported draft source')
        kind = 'shipping_save' if setting == 'shipping_rules' else 'category_navigation_save'
        identity = digest([project_id, kind, request_id])
        fingerprint = digest([project_revision, plan_id, plan_revision, setting, value.model_dump(mode='json')])
        with self.repo.db.transaction() as conn:
            project = self.repo._project(conn, project_id, project_revision)
            replay = conn.execute(text("SELECT digest,data FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind=:kind"),
                                  {'id': identity, 'project': project_id, 'kind': kind}).first()
            if replay:
                if replay[0] != fingerprint:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return CommercePlan.model_validate_json(replay[1])
            current = self.repo.current_site_draft(conn, project_id)
            if current is None or current.id != plan_id or current.revision != plan_revision:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            if setting == 'shipping_rules' and value.currency != project.brief.currency:
                raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
            if setting == 'category_navigation':
                from muse.commerce.category_navigation import validate_category_source
                validate_category_source(conn, project, value)
            unsafe = conn.execute(text("SELECT 1 FROM commerce_plans WHERE project_id=:id AND json_extract(data,'$.state') IN ('PUBLISHING','PARTIAL','NEEDS_RECONCILIATION') LIMIT 1"), {'id': project_id}).first()
            unsafe = unsafe or conn.execute(text("SELECT 1 FROM commerce_artifacts WHERE project_id=:id AND (json_extract(CASE WHEN json_valid(data) THEN data ELSE '{}' END,'$.state') IN ('UNKNOWN','CLEANUP_UNKNOWN','NEEDS_RECONCILIATION','PUBLISHING','PARTIAL') OR json_extract(CASE WHEN json_valid(data) THEN data ELSE '{}' END,'$.phase') IN ('PUBLISHING','NEEDS_RECONCILIATION')) LIMIT 1"), {'id': project_id}).first()
            if unsafe:
                raise CommerceFailure('PROJECT_BUSY', project_id=project_id)
            current.blueprint.required_settings[setting] = value.model_dump(mode='json')
            current.revision += 1
            current.content_hash = digest({'project_revision': project_revision, 'blueprint': current.blueprint.model_dump(mode='json')})
            self.repo._invalidate(conn, project_id)
            conn.execute(text('UPDATE commerce_plans SET data=:data,revision=:revision WHERE id=:id AND project_id=:project'),
                         {'id': current.id, 'project': project_id, 'data': encode(current), 'revision': current.revision})
            design = DesignRepository.read(conn, project_id)
            if design is not None:
                design.revision += 1
                design.blueprint_revision = current.revision
                DesignRepository(self.repo)._persist(conn, design, kind+':'+identity, fingerprint)
            conn.execute(text('INSERT INTO commerce_artifacts(id,project_id,plan_id,kind,digest,data) VALUES(:id,:project,:plan,:kind,:digest,:data)'),
                         {'id': identity, 'project': project_id, 'kind': kind, 'digest': fingerprint,
                          'plan': current.id, 'data': encode(current)})
            self.repo.event(conn, project_id, kind+'_saved', {'plan_id': current.id, 'revision': current.revision})
            return current
