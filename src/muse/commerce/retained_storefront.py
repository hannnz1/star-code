"""Product launches preserve the exact, independently published site source."""
import base64
from sqlalchemy import text
from muse.commerce.models import CommercePlan
from muse.commerce.repository import digest
from muse.commerce.errors import CommerceFailure


def retain_published_storefront(conn, repo, project, snapshot):
    from muse.commerce.code_bridge import load_captured_code
    from muse.commerce.code_integration import CommerceCodeIntegration
    rows = conn.execute(text("SELECT data FROM commerce_plans WHERE project_id=:project AND json_extract(data,'$.state')='SUCCEEDED' ORDER BY rowid DESC"), {'project':project.id})
    for raw, in rows:
        previous = CommercePlan.model_validate_json(raw)
        if previous.kind != 'build_site' or not previous.blueprint.required_settings.get('store_design'):
            continue
        settings=previous.blueprint.required_settings
        if settings.get('currency')!=project.brief.currency or settings.get('language')!=project.brief.language:
            # Retaining code must not silently retain obsolete merchant facts.
            # Changed language/currency needs a new reviewed site build first.
            raise CommerceFailure('RESOURCE_CONFLICT',project_id=project.id)
        code = load_captured_code(repo, previous, connection=conn)
        hashes = {item['path']:item['sha256'] for item in code.package.files_manifest}
        if hashes != snapshot.theme_identity.get('files_sha256'):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project.id)
        identity = digest([project.id, 'retained-storefront', code.source_digest])
        CommerceCodeIntegration._save(conn, identity, project.id, None, 'restored_theme_source', {
            'package':code.package.model_dump(mode='json'), 'archive_base64':base64.b64encode(code.archive).decode(),
            'deployment_verified':False})
        blueprint = previous.blueprint.model_copy(deep=True)
        from muse.commerce.site import build_site_blueprint
        current_setup=build_site_blueprint(project.brief,snapshot)
        blueprint.required_settings['missing_fields']=current_setup.required_settings['missing_fields']
        blueprint.required_settings['buyer_flow_verified']=False
        for key in ('restored_theme_source','local_code_base_revision','repair_context'):
            blueprint.required_settings.pop(key,None)
        blueprint.required_settings['retain_existing_theme'] = True
        return blueprint, identity
    return None


def validate_retained_theme(workflow, blueprint, package, snapshot):
    if workflow=='launch_products' and blueprint.required_settings.get('retain_existing_theme'):
        expected = {item['path']:item['sha256'] for item in package.files_manifest}
        if expected != snapshot.theme_identity.get('files_sha256'):
            raise ValueError('Product launch must preserve the installed site source')
