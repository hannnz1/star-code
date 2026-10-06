from pathlib import Path

from tests.muse.commerce.test_reference_runner import inputs


def test_disposable_theme_storage_shares_filesystem_without_public_alias(workflow, tmp_path):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, _, lock = inputs(workflow, tmp_path)
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    args = runner._run_arguments(job, 'wordpress', tmp_path / 'private')
    volume = job.resource_names['site_volume']
    assert f'type=volume,src={volume},dst=/var/www/html,volume-subpath=site' in args
    assert f'type=volume,src={volume},dst=/var/muse-volume' in args
    assert not any('tmpfs' in value and 'packages' in value for value in args)
    bootstrap = (Path(__file__).resolve().parents[3] / 'src/muse/commerce/assets/reference/bootstrap.php').read_text()
    assert "define('MUSE_PACKAGE_STORAGE', '/var/muse-volume/packages')" in bootstrap
    assert "'MUSE_PACKAGE_STORAGE', 'MUSE_DEPLOY_THEME_ROOT', 'MUSE_SERVICE_USER_ID'" in bootstrap


def test_private_package_mount_cannot_alias_public_site_subpath(tmp_path):
    import pytest

    from muse.commerce.errors import CommerceFailure
    from muse.commerce.reference_environment import inspect_reference_container
    from tests.muse.commerce.test_reference_environment import inspected
    record = inspected('wordpress', 'd' * 32, tmp_path)
    record['HostConfig']['Mounts'][-1]['VolumeOptions']['Subpath'] = 'site'
    with pytest.raises(CommerceFailure):
        inspect_reference_container(record, role='wordpress', job_id='d' * 32,
            image_digest='wordpress@sha256:' + 'a' * 64, image_id='sha256:' + 'c' * 64,
            port=63660, private_root=tmp_path)

