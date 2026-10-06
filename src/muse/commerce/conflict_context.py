"""Frozen repair evidence, separate from the new task's editable code baseline."""
import io
import zipfile

from muse.commerce.code_bridge import load_captured_code, theme_seed_files
from muse.commerce.code_integration import CommerceCodeIntegration, source_files
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan
from muse.commerce.repository import digest
from muse.commerce.restore import ProjectRestorer
from muse.commerce.theme import ALLOWED_FILES
from sqlalchemy import text


def capture_repair_context(repo, conn, draft):
    if not draft.source_plan_id or not draft.suggestion_id:
        return None
    if draft.suggestion_id != digest([draft.source_plan_id, 'conflict']):
        return None
    raw = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
                       {'id': draft.source_plan_id, 'project': draft.project_id}).scalar()
    if not raw:
        raise CommerceFailure('RESOURCE_CONFLICT', project_id=draft.project_id)
    source = CommercePlan.model_validate_json(raw)
    if source.revision != draft.source_plan_revision:
        raise CommerceFailure('RESOURCE_CONFLICT', project_id=draft.project_id)
    review, _, _ = CommerceCodeIntegration(repo, None)._review(conn, draft.project_id, source.id, source.revision)
    if review.reason != 'conflicts':
        raise CommerceFailure('RESOURCE_CONFLICT', project_id=draft.project_id)
    artifact = load_captured_code(repo, source, connection=conn)
    base = theme_seed_files(conn, source)
    head = CommerceCodeIntegration.head(conn, draft.project_id)
    current = source_files(ProjectRestorer._theme_source(conn, draft.project_id, head.source_id)[0]) if head else base
    with zipfile.ZipFile(io.BytesIO(artifact.archive)) as archive:
        candidate = {name: archive.read('muse-storefront/' + name) for name in ALLOWED_FILES}
    files = {name: {'base': base[name].decode(), 'current': current[name].decode(), 'candidate': candidate[name].decode()}
             for name in review.conflict_files}
    return {'untrusted_reference': True, 'source_plan_id': source.id, 'source_plan_revision': source.revision,
            'head_revision': review.head_revision, 'review_digest': review.review_digest,
            'source_digest': artifact.source_digest, 'conflicts': files}


def read_repair_file(repo, conn, plan, name):
    reference = plan.blueprint.required_settings.get('repair_context')
    if not reference or name not in ALLOWED_FILES:
        raise CommerceFailure('NOT_FOUND', 404, project_id=plan.project_id)
    raw = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='conflict_repair_context'"),
                       {'id': reference['id'], 'project': plan.project_id, 'plan': plan.id}).mappings().first()
    import json
    context = json.loads(raw['data']) if raw else None
    if not context or digest(context) != raw['digest'] or raw['digest'] != reference['digest']:
        raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
    if name not in context['conflicts']:
        raise CommerceFailure('NOT_FOUND', 404, project_id=plan.project_id)
    return {'untrusted_reference': True, 'source_plan_id': context['source_plan_id'],
            'head_revision': context['head_revision'], 'name': name, **context['conflicts'][name]}
