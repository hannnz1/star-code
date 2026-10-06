import json

import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_reference_environment import inspected
from tests.muse.commerce.test_reference_runner import inputs


async def test_partial_bootstrap_is_unknown_and_cannot_repeat_credentials_or_install(workflow, tmp_path, monkeypatch):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, bundle, lock = inputs(workflow, tmp_path)
    current = jobs.begin(job.id, expected_revision=job.revision)
    root = tmp_path / 'private'
    directory = root / job.id
    directory.mkdir(parents=True, mode=0o700)
    runner = DockerReferenceRunner(jobs, root, lock)
    runner.executable = 'fixture-docker'
    monkeypatch.setattr('muse.commerce.reference_runner.platform.system', lambda: 'Linux')
    commands = []
    async def cli(*args, **kwargs):
        commands.append(args)
        raise TimeoutError()
    monkeypatch.setattr(runner, '_cli', cli)
    # Without verified resource preparation metadata bootstrap must do nothing.
    with pytest.raises(CommerceFailure): await runner.bootstrap(current, bundle, currency='USD', language='en-US')
    assert commands == []
    assert jobs.read(job.project_id, job.id).state == 'UNKNOWN'
    assert not (directory / 'connection.json').exists()


@pytest.mark.parametrize('problem', ['none', 'reply_lost', 'assets_changed', 'unsafe_gateway', 'safety_temporary'])
async def test_bootstrap_ready_requires_exact_resource_asset_and_safety_readback(workflow, tmp_path, monkeypatch, problem):
    """Explicit fake Docker/CMS contracts, not Linux deployment evidence."""
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, bundle, lock = inputs(workflow, tmp_path)
    current = jobs.begin(job.id, expected_revision=job.revision)
    directory = tmp_path / 'private' / job.id
    directory.mkdir(parents=True, mode=0o700)
    runner = DockerReferenceRunner(jobs, directory.parent, lock)
    runner.executable = 'fixture-docker'
    monkeypatch.setattr('muse.commerce.reference_runner.platform.system', lambda: 'Linux')
    records = {role: inspected(role, job.id, directory) for role in ('database', 'wordpress', 'cli')}
    for index, record in enumerate(records.values()): record['Id'] = str(index + 1) * 64
    metadata = {'job_id': job.id, 'asset_digest': bundle.source_digest,
                'containers': {role: record['Id'] for role, record in records.items()},
                'images': {role: record['Image'] for role, record in records.items()}}
    runner._write_private(directory / 'prepared.json', metadata)
    names = job.resource_names
    network = {'Name': names['network'], 'Id': 'e' * 64, 'Driver': 'bridge', 'Scope': 'local',
        'Internal': True, 'Attachable': False, 'Ingress': False, 'Options': {}, 'Labels': {'muse.reference_job': job.id},
        'Containers': {record['Id']: {'Name': names[role]} for role, record in records.items()}}
    volumes = [{'Name': names[key], 'Driver': 'local', 'Scope': 'local', 'Options': {},
                'Labels': {'muse.reference_job': job.id}} for key in ('database_volume', 'site_volume')]
    writes = []
    async def cli(*args, **kwargs):
        if args[0] == 'info': return b'\"linux\"'
        if args[0] == 'exec' and 'MUSE_REFERENCE_READINESS' in args[-1]: return b'true'
        if args[0] == 'inspect':
            return json.dumps([next(record for role, record in records.items() if names[role] == args[1] or record['Id'] == args[1])]).encode()
        if args[:2] == ('network', 'inspect'): return json.dumps([network]).encode()
        if args[:2] == ('volume', 'inspect'): return json.dumps(volumes).encode()
        assert args[:2] == ('exec', '-i')
        writes.append(args[3])
        if args[3] == '/bin/tar': return b''
        if 'Exact fixed-file readback' in args[5]:
            return b'[]' if problem == 'assets_changed' else json.dumps(bundle.manifest).encode()
        if problem == 'reply_lost': raise TimeoutError()
        return json.dumps({'service_user_id': 2, 'username': 'muse_reference_service',
            'application_password': 'unit-private-not-real-password', 'job_id': job.id}).encode()
    safety_reads = []
    async def safety(connection):
        safety_reads.append(connection)
        if problem == "safety_temporary" and len(safety_reads) == 1:
            raise TimeoutError()
        assert connection.environment == 'staging' and connection.base_url == 'http://127.0.0.1:63660'
        return {'job_id': job.id, 'environment': 'staging', 'wordpress_version': lock['wordpress'],
            'woocommerce_version': lock['woocommerce'], 'email_disabled': True, 'external_requests_disabled': True,
            'indexing_disabled': True, 'cron_disabled': True, 'offline_gateway_only': problem != 'unsafe_gateway'}
    monkeypatch.setattr(runner, '_cli', cli)
    monkeypatch.setattr(runner, '_read_safety', safety)
    if problem == 'none':
        result = await runner.bootstrap(current, bundle, currency='USD', language='en-US')
        assert result['site_ready'] is True and result['assets_verified'] is True
        assert 'application_password' not in json.dumps(result)
        assert jobs.read(job.project_id, job.id).state == 'READY'
    else:
        with pytest.raises(CommerceFailure): await runner.bootstrap(current, bundle, currency='USD', language='en-US')
        assert jobs.read(job.project_id, job.id).state == 'UNKNOWN'
    before = len(writes)
    with pytest.raises(CommerceFailure): await runner.bootstrap(jobs.read(job.project_id, job.id), bundle, currency='USD', language='en-US')
    assert len(writes) == before
    if problem == 'safety_temporary':
        result = await runner.verify(jobs.read(job.project_id, job.id), bundle)
        assert result['site_ready'] is True
        assert writes[before:] == ['/usr/local/bin/php']  # fixed readback, no tar/install
        assert jobs.read(job.project_id, job.id).state == 'READY'
        assert 'application_password' not in json.dumps(result)

