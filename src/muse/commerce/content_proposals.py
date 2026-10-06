"""Frozen wording proposals. Only the authenticated merchant API can confirm."""
import csv
import hashlib
import io
from typing import Literal

from pydantic import Field, ValidationError
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.media import MediaRepository
from muse.commerce.models import (
    CommercePlan,
    Contract,
    ImportedProducts,
    ProductDraft,
    StoreProject,
)
from muse.commerce.products import COLUMNS, parse_products
from muse.commerce.repository import digest, encode

FIXED_FIELDS = ('sku', 'price', 'currency', 'stock', 'category', 'media_refs', 'source_facts')


class ContentConfirmation(Contract):
    project: StoreProject
    batch: ImportedProducts


class ContentProposal(Contract):
    id: str
    project_id: str
    plan_id: str
    project_revision: int = Field(ge=1)
    plan_revision: int = Field(ge=1)
    content_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    original: list[ProductDraft] = Field(min_length=1, max_length=20)
    candidates: list[ProductDraft] = Field(min_length=1, max_length=20)
    status: Literal['PENDING', 'CONFIRMED'] = 'PENDING'
    confirmation: ContentConfirmation | None = None
    confirmed_plan_revision: int | None = Field(default=None, ge=1)


class ContentProposalRepository:
    def __init__(self, repo):
        self.repo, self.db = repo, repo.db

    @staticmethod
    def _read(conn, project_id, plan_id, identity):
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='content_proposal'"),
            {'id': identity, 'project': project_id, 'plan': plan_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
        try:
            value = ContentProposal.model_validate_json(row['data'])
            source = [value.project_id, value.plan_id, value.project_revision,
                      [p.model_dump(mode='json') for p in value.original],
                      [p.model_dump(mode='json') for p in value.candidates]]
            if (value.id != identity or value.project_id != project_id or value.plan_id != plan_id
                    or digest(value) != row['digest']
                    or digest(source) != value.content_digest):
                raise ValueError()
            return value
        except (ValueError, TypeError, ValidationError):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id) from None

    def latest(self, project_id, plan_id):
        with self.db.engine.connect() as conn:
            plan_row = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
                {'id': plan_id, 'project': project_id}).scalar()
            if not plan_row:
                raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
            plan = CommercePlan.model_validate_json(plan_row)
            identity = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND plan_id=:plan AND kind='content_proposal' ORDER BY rowid DESC LIMIT 1"),
                {'project': project_id, 'plan': plan_id}).scalar()
            value = self._read(conn, project_id, plan_id, identity)
            if value.status == 'PENDING':
                # Other roles may finish while the merchant reviews wording.
                # Refresh the expected plan version, never the frozen content.
                return value.model_copy(update={'plan_revision': plan.revision})
            return value

    def offer(self, conn, plan, candidates):
        """Called only after the workflow has validated its leased content actor."""
        if (not candidates or len(candidates) != len(plan.products)
                or any(getattr(a, f) != getattr(b, f) for a, b in zip(plan.products, candidates, strict=True) for f in FIXED_FIELDS)):
            raise CommerceFailure('FACTS_INCOMPLETE', project_id=plan.project_id)
        project = self.repo._project(conn, plan.project_id)
        # Reuse the actual CSV validator; whitespace/formulas/oversized batches
        # must not become an unconfirmable pending proposal.
        self._csv(conn, project, candidates)
        identity = digest([plan.id, 'content_proposal'])
        content_digest = digest([project.id, plan.id, project.revision,
            [p.model_dump(mode='json') for p in plan.products], [p.model_dump(mode='json') for p in candidates]])
        old = conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': identity}).scalar()
        if old:
            value = self._read(conn, project.id, plan.id, identity)
            if value.status != 'PENDING' or value.content_digest != content_digest:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project.id)
            return False
        value = ContentProposal(id=identity, project_id=project.id, plan_id=plan.id,
            project_revision=project.revision, plan_revision=plan.revision + 1,
            content_digest=content_digest, original=plan.products, candidates=candidates)
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'content_proposal',:digest,:data)"),
            {'id': identity, 'project': project.id, 'plan': plan.id, 'digest': digest(value), 'data': encode(value)})
        self.repo.event(conn, project.id, 'content_confirmation_required', {'plan_id': plan.id, 'proposal_id': identity, 'content_digest': content_digest})
        return True

    @staticmethod
    def _csv(conn, project, products):
        media_ids = list(dict.fromkeys(ref for product in products for ref in product.media_refs))
        images = [MediaRepository._read(conn, project.id, ref)[0].image for ref in media_ids]
        names = {image.artifact_ref: image.name for image in images}
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(COLUMNS)
        for p in products:
            writer.writerow([p.sku, p.title, str(p.price), p.currency, str(p.stock), p.category,
                             p.description, '|'.join(names[ref] for ref in p.media_refs)])
        raw = stream.getvalue().encode('utf-8')
        result = parse_products(raw, images, project.brief.currency)
        if (result.errors or len(result.drafts) != len(products)
                or any(a.model_dump(exclude={'source_facts'}) != b.model_dump(exclude={'source_facts'})
                       for a, b in zip(result.drafts, products, strict=True))):
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project.id)
        return raw, result, media_ids

    def confirm(self, project_id, plan_id, identity, project_revision, plan_revision, content_digest):
        with self.db.transaction() as conn:
            value = self._read(conn, project_id, plan_id, identity)
            if (value.project_revision != project_revision or value.plan_revision > plan_revision
                    or value.content_digest != content_digest):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            project = self.repo._project(conn, project_id)
            if value.status == 'CONFIRMED':
                if (value.confirmation is None or project.revision != value.confirmation.project.revision
                        or value.confirmed_plan_revision != plan_revision):
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return value.confirmation
            row = conn.execute(text('SELECT data,root_task_id FROM commerce_plans WHERE id=:id AND project_id=:project'),
                {'id': plan_id, 'project': project_id}).mappings().first()
            plan = CommercePlan.model_validate_json(row['data']) if row else None
            root = self.repo.runtime._task(conn, row['root_task_id']) if row and row['root_task_id'] else None
            if (project.revision != project_revision or plan is None or plan.revision != plan_revision
                    or plan.state != 'NEEDS_INPUT' or plan.error_code != 'FACTS_INCOMPLETE'
                    or plan.products != value.original or root is None or root['cancel_requested']
                    or root['status'] in {'FAILED', 'CANCELLED'}):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            raw, result, media_ids = self._csv(conn, project, value.candidates)
            updated = project.model_copy(update={'revision': project.revision + 1})
            batch = ImportedProducts(id=digest([identity, 'confirmed_import']), project_id=project_id,
                project_revision=updated.revision, csv_sha256=hashlib.sha256(raw).hexdigest(), result=result)
            conn.execute(text('UPDATE commerce_projects SET revision=:revision,data=:data WHERE id=:id'),
                {'id': project_id, 'revision': updated.revision, 'data': encode(updated)})
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'product_import',:digest,:data)"),
                {'id': batch.id, 'project': project_id, 'digest': digest(batch), 'data': encode(batch)})
            binding = {'media_ids': media_ids}
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'product_import_media',:digest,:data)"),
                {'id': digest([batch.id, 'media_binding']), 'project': project_id, 'digest': digest(binding), 'data': encode(binding)})
            self.repo._invalidate(conn, project_id)
            confirmation = ContentConfirmation(project=updated, batch=batch)
            saved = value.model_copy(update={'status': 'CONFIRMED', 'confirmation': confirmation,
                                             'confirmed_plan_revision': plan_revision})
            conn.execute(text('UPDATE commerce_artifacts SET digest=:digest,data=:data WHERE id=:id'),
                {'id': identity, 'digest': digest(saved), 'data': encode(saved)})
            self.repo.event(conn, project_id, 'content_confirmed', {'proposal_id': identity, 'import_id': batch.id,
                'project_revision': updated.revision, 'content_digest': content_digest})
            return confirmation
