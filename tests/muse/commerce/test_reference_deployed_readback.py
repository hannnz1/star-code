from scripts.commerce.verify_linux_workflow import prepare_roles
from tests.muse.commerce.test_reference_runner import inputs


def test_readback_manifest_preserves_fixed_assets_and_uses_sealed_theme(workflow, tmp_path):
    from muse.commerce.code_bridge import load_captured_code
    from muse.commerce.reference_environment import reference_readback_manifest
    service, tasks, plan, worker = workflow
    _, _, bundle, _ = inputs(workflow, tmp_path)
    prepared = prepare_roles(service, tasks, worker.settings, plan)
    code = load_captured_code(service.repo, prepared)
    manifest = reference_readback_manifest(bundle, code)
    fixed = [row for row in bundle.manifest if not row['path'].startswith('wp-content/themes/')]
    assert [row for row in manifest if not row['path'].startswith('wp-content/themes/')] == fixed
    theme = [{'path': 'wp-content/themes/muse-storefront/' + row['path'],
              'sha256': row['sha256'], 'byte_size': row['bytes']} for row in code.package.files_manifest]
    assert [row for row in manifest if row['path'].startswith('wp-content/themes/')] == theme
    assert theme != [row for row in bundle.manifest if row['path'].startswith('wp-content/themes/')]
    assert reference_readback_manifest(bundle, None) == list(bundle.manifest)
