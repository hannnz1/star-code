"""Freeze structured edits with the existing conservative three-way code merge."""
import base64
from sqlalchemy import text
from muse.commerce.repository import digest
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CommercePlan


def merge_design_source(conn,repo,blueprint,products,head):
    from muse.commerce.code_bridge import theme_seed_files
    from muse.commerce.code_integration import CommerceCodeIntegration,source_files,merge_files,files_digest
    from muse.commerce.restore import ProjectRestorer
    from muse.commerce.theme import render_site_files,build_file_archive
    raw=conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),{'id':head.plan_id,'project':head.project_id}).scalar()
    if not raw:raise CommerceFailure('RESOURCE_CONFLICT')
    base=theme_seed_files(conn,CommercePlan.model_validate_json(raw))
    current=source_files(ProjectRestorer._theme_source(conn,head.project_id,head.source_id)[0])
    candidate=render_site_files(blueprint,products)
    merged,conflicts=merge_files(base,current,candidate)
    if conflicts:raise CommerceFailure('RESOURCE_CONFLICT',project_id=head.project_id)
    package,archive=build_file_archive(merged,code_revision=files_digest(merged)[:40],content_hash=digest({'blueprint':blueprint.model_dump(mode='json'),'products':[p.model_dump(mode='json') for p in products]}))
    identity=digest([head.project_id,'design-code-merge',head.revision,package.package_sha256])
    value={'package':package.model_dump(mode='json'),'archive_base64':base64.b64encode(archive).decode('ascii'),'deployment_verified':False}
    CommerceCodeIntegration._save(conn,identity,head.project_id,None,'restored_theme_source',value)
    return identity
