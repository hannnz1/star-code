"""Transactional design revisions with replay-safe, project-scoped saves."""
from sqlalchemy import text
from contextlib import nullcontext
from muse.commerce.design_models import StoreDesignDocument, DesignSection, SectionProps
from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest, encode


class DesignRepository:
    def __init__(self, repo):
        self.repo = repo

    @staticmethod
    def read(conn, project_id):
        raw = conn.execute(text('SELECT v.data,v.digest FROM commerce_design_versions v JOIN commerce_design_heads h ON h.project_id=v.project_id AND h.revision=v.revision WHERE v.project_id=:id'), {'id':project_id}).first()
        if not raw: return None
        doc = StoreDesignDocument.model_validate_json(raw[0])
        if digest(doc) != raw[1]: raise CommerceFailure('RESOURCE_CONFLICT')
        return doc

    def get(self, project_id):
        with self.repo.db.transaction() as conn:
            self.repo._project(conn, project_id)
            return self.read(conn, project_id)

    def get_or_create(self, project_id, expected_project_revision):
        with self.repo.db.transaction() as conn:
            project = self.repo._project(conn, project_id, expected_project_revision)
            # Prepare and save together: a rejected design must not leave a new
            # blueprint or event behind while a remote write is unresolved.
            self.repo.create_site_blueprint(project_id, 'visual-editor-init-'+str(expected_project_revision), expected_project_revision, _connection=conn)
            plan = self.repo.current_site_draft(conn, project_id)
            previous = self.read(conn, project_id)
            if previous and previous.project_revision == project.revision and previous.blueprint_plan_id == plan.id and previous.blueprint_revision == plan.revision:
                return previous
            if previous:
                doc = previous.model_copy(deep=True)
                doc.project_revision = project.revision
                doc.blueprint_plan_id, doc.blueprint_revision = plan.id, plan.revision
                doc.revision += 1
            else:
                zh = project.brief.language.startswith('zh')
                titles = ['欢迎来到 '+project.brief.brand_name,'探索分类','推荐商品','品牌故事','常见问题'] if zh else ['Welcome to '+project.brief.brand_name,'Explore categories','Featured products','Our story','Frequently asked questions']
                kinds = ['hero','categories','products','story','faq']
                doc = StoreDesignDocument(project_id=project_id,project_revision=project.revision,revision=1,
                    blueprint_plan_id=plan.id,blueprint_revision=plan.revision,
                    home_sections=[DesignSection(id=kind,kind=kind,props=SectionProps(title=title)) for kind,title in zip(kinds,titles)])
            self._persist(conn,doc,'init:'+str(doc.revision),digest(doc))
            return doc

    def _persist(self, conn, doc, request_id, fingerprint):
        # Preserve reconciliation handles for writes already in flight.
        unsafe = conn.execute(text("SELECT 1 FROM commerce_plans WHERE project_id=:id AND json_extract(data,'$.state') IN ('PUBLISHING','PARTIAL','NEEDS_RECONCILIATION') LIMIT 1"), {'id':doc.project_id}).first()
        unsafe = unsafe or conn.execute(text("SELECT 1 FROM commerce_artifacts WHERE project_id=:id AND (json_extract(CASE WHEN json_valid(data) THEN data ELSE '{}' END,'$.state') IN ('UNKNOWN','CLEANUP_UNKNOWN','NEEDS_RECONCILIATION','PUBLISHING','PARTIAL') OR json_extract(CASE WHEN json_valid(data) THEN data ELSE '{}' END,'$.phase') IN ('PUBLISHING','NEEDS_RECONCILIATION')) LIMIT 1"), {'id':doc.project_id}).first()
        if unsafe: raise CommerceFailure('PROJECT_BUSY', project_id=doc.project_id)
        conn.execute(text('INSERT INTO commerce_design_versions VALUES(:project,:revision,:data,:digest,:request,:fingerprint)'),
            {'project':doc.project_id,'revision':doc.revision,'data':encode(doc),'digest':digest(doc),'request':request_id,'fingerprint':fingerprint})
        conn.execute(text('INSERT INTO commerce_design_heads VALUES(:project,:revision) ON CONFLICT(project_id) DO UPDATE SET revision=excluded.revision'),
            {'project':doc.project_id,'revision':doc.revision})
        self.repo._invalidate(conn,doc.project_id)
        # Standalone structure source is not an executable workflow: preserve its validity.
        from muse.commerce.models import CommercePlan
        raw=conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id'),{'id':doc.blueprint_plan_id}).scalar()
        source=CommercePlan.model_validate_json(raw)
        if source.state == 'STALE' and not source.steps:
            source.state='NEEDS_INPUT';source.revision=doc.blueprint_revision
            conn.execute(text('UPDATE commerce_plans SET data=:data,revision=:revision WHERE id=:id'),{'data':encode(source),'revision':source.revision,'id':source.id})
        self.repo.event(conn,doc.project_id,'design_saved',{'revision':doc.revision,'digest':digest(doc)})

    def save(self, project_id, expected_project_revision, expected_revision, client_request_id, document, *, _connection=None):
        with self.repo.db.transaction() if _connection is None else nullcontext(_connection) as conn:
            project=self.repo._project(conn,project_id,expected_project_revision)
            fingerprint=digest([expected_project_revision,expected_revision,document.model_dump(mode='json')])
            old=conn.execute(text('SELECT data,request_digest FROM commerce_design_versions WHERE project_id=:id AND request_id=:key'),{'id':project_id,'key':'save:'+client_request_id}).mappings().first()
            if old:
                if old['request_digest'] != fingerprint: raise CommerceFailure('RESOURCE_CONFLICT')
                return StoreDesignDocument.model_validate_json(old['data'])
            current=self.read(conn,project_id)
            plan=self.repo.current_site_draft(conn,project_id)
            if (not current or current.revision != expected_revision or document.revision != expected_revision
                or document.project_id != project_id or document.project_revision != project.revision
                or not plan or current.blueprint_plan_id != plan.id or current.blueprint_revision != plan.revision
                or document.blueprint_plan_id != current.blueprint_plan_id or document.blueprint_revision != current.blueprint_revision):
                raise CommerceFailure('RESOURCE_CONFLICT')
            from muse.commerce.media import MediaRepository
            for section in document.home_sections:
                if section.props.media_id:
                    try: MediaRepository._read(conn,project_id,section.props.media_id)
                    except CommerceFailure: raise CommerceFailure('INPUT_INVALID',422) from None
            doc=document.model_copy(deep=True);doc.revision=expected_revision+1
            self._persist(conn,doc,'save:'+client_request_id,fingerprint)
            return doc
