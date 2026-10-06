import json

import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_reference_environment import archive, manifest


def inputs(workflow, tmp_path):
    from muse.commerce.reference_environment import load_reference_assets
    from muse.commerce.reference_jobs import ReferenceJobRepository
    service, _, plan, _ = workflow
    data = archive()
    path = tmp_path / 'woo.zip'
    path.write_bytes(data)
    lock = manifest(data)
    bundle = load_reference_assets(lock, path)
    jobs = ReferenceJobRepository(service.repo)
    project = service.repo.get_project(plan.project_id)
    job = jobs.reserve(project.id, project.revision, 'runner', bundle.source_digest, 63660)
    return jobs, job, bundle, lock


async def test_no_linux_or_daemon_never_launches_or_records_ready(workflow, tmp_path, monkeypatch):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, bundle, lock = inputs(workflow, tmp_path)
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    monkeypatch.setattr('muse.commerce.reference_runner.platform.system', lambda: 'Windows')
    with pytest.raises(CommerceFailure): await runner.prepare(job, bundle)
    assert jobs.read(job.project_id, job.id).state == 'RESERVED'


async def test_timeout_after_resource_creation_persists_unknown_and_no_second_launch(workflow, tmp_path, monkeypatch):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, bundle, lock = inputs(workflow, tmp_path)
    monkeypatch.setattr('muse.commerce.reference_runner.platform.system', lambda: 'Linux')
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    runner.executable = 'fixture-docker'
    commands = []
    async def cli(*args, **kwargs):
        commands.append(args)
        if args[0] == 'info': return b'"linux"'
        if args[:2] == ('image', 'inspect'):
            return json.dumps([{'Id': 'sha256:' + 'c' * 64, 'Os': 'linux', 'RepoDigests': [args[2]]}]).encode()
        if args[:2] == ('network', 'ls') or args[:2] == ('volume', 'ls') or args[:2] == ('container', 'ls'): return b''
        if args[:2] == ('network', 'create'): raise TimeoutError()
        raise AssertionError(args)
    monkeypatch.setattr(runner, '_cli', cli)
    with pytest.raises(CommerceFailure): await runner.prepare(job, bundle)
    current = jobs.read(job.project_id, job.id)
    assert current.state == 'UNKNOWN'
    count = len(commands)
    with pytest.raises(CommerceFailure): await runner.prepare(current, bundle)
    assert len(commands) == count
    assert not any(command[0] == 'run' for command in commands)


async def test_existing_external_resource_refuses_before_unknown_or_creation(workflow, tmp_path, monkeypatch):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, bundle, lock = inputs(workflow, tmp_path)
    monkeypatch.setattr('muse.commerce.reference_runner.platform.system', lambda: 'Linux')
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    runner.executable = 'fixture-docker'
    commands = []
    async def cli(*args, **kwargs):
        commands.append(args)
        if args[0] == 'info': return b'"linux"'
        if args[:2] == ('image', 'inspect'):
            return json.dumps([{'Id': 'sha256:' + 'c' * 64, 'Os': 'linux', 'RepoDigests': [args[2]]}]).encode()
        if args[:2] == ('network', 'ls'): return job.resource_names['network'].encode()
        raise AssertionError(args)
    monkeypatch.setattr(runner, '_cli', cli)
    with pytest.raises(CommerceFailure): await runner.prepare(job, bundle)
    assert jobs.read(job.project_id, job.id).state == 'RESERVED'
    assert not any('create' in command or command[0] == 'run' for command in commands)


async def test_unknown_recovery_only_lists_and_inspects_never_creates_or_cleans(workflow, tmp_path, monkeypatch):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, _bundle, lock = inputs(workflow, tmp_path)
    current = jobs.begin(job.id, expected_revision=job.revision)
    monkeypatch.setattr('muse.commerce.reference_runner.platform.system', lambda: 'Linux')
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    runner.executable = 'fixture-docker'
    commands = []
    async def cli(*args, **kwargs):
        commands.append(args)
        if args[0] == 'info': return b'"linux"'
        if args[1] == 'ls': return b''
        raise AssertionError(args)
    monkeypatch.setattr(runner, '_cli', cli)
    result = await runner.recover(current)
    assert result['site_ready'] is False and set(result['absent_names']) == set(job.resource_names.values())
    assert jobs.read(job.project_id, job.id).state == 'UNKNOWN'
    assert all(command[0] == 'info' or command[1] == 'ls' for command in commands)

def test_password_mount_is_readable_inside_container_but_host_directory_is_private(workflow, tmp_path, monkeypatch):
    import stat

    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, _, lock = inputs(workflow, tmp_path)
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    runner.root.mkdir()
    modes = []
    original = __import__('os').chmod
    def chmod(path, mode):
        modes.append(mode)
        original(path, mode)
    monkeypatch.setattr('muse.commerce.reference_runner.os.chmod', chmod)
    directory = runner._secret_directory(job)
    assert modes == [0o444, 0o444]
    for name in ('database-password', 'database-root-password'):
        assert stat.S_IMODE((directory / name).stat().st_mode) & 0o444 == 0o444

async def test_fixed_readiness_checks_cms_files_and_database_before_install(workflow, tmp_path, monkeypatch):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, _, lock = inputs(workflow, tmp_path)
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    commands = []
    async def cli(*args, **kwargs):
        commands.append(args)
        assert 'MUSE_REFERENCE_READINESS' in args[-1]
        assert args[:5] == ('exec', 'd' * 64, '/usr/local/bin/php', '-r', args[-1])
        return b'true'
    monkeypatch.setattr(runner, '_cli', cli)
    await runner._wait_ready(job, 'd' * 64)
    assert len(commands) == 1 and jobs.read(job.project_id, job.id).state == 'RESERVED'
