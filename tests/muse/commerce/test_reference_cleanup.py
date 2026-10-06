import json

import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_reference_runner import inputs


def cleanup_fixture(workflow, tmp_path, monkeypatch, *, foreign=None, lost=False):
    from muse.commerce.reference_runner import DockerReferenceRunner
    jobs, job, _, lock = inputs(workflow, tmp_path)
    job = jobs.begin(job.id, expected_revision=job.revision)
    monkeypatch.setattr('muse.commerce.reference_runner.platform.system', lambda: 'Linux')
    runner = DockerReferenceRunner(jobs, tmp_path / 'private', lock)
    runner.executable = 'fixture-docker'
    names = job.resource_names
    identities = {role: str(index) * 64 for index, role in enumerate(('cli', 'wordpress', 'database'), 1)}
    records = {}
    for role, identity in identities.items():
        records[('container', names[role])] = {'Id': identity, 'Name': '/' + names[role],
            'Config': {'Labels': {'muse.reference_job': job.id, 'muse.reference_role': role}},
            'Mounts': [{'Type': 'volume', 'Name': names['database_volume' if role == 'database' else 'site_volume']}]}
    records[('network', names['network'])] = {'Id': 'e' * 64, 'Name': names['network'], 'Driver': 'bridge', 'Scope': 'local',
        'Internal': True, 'Attachable': False, 'Ingress': False, 'Options': {},
        'Labels': {'muse.reference_job': job.id},
        'Containers': {identity: {'Name': names[role]} for role, identity in identities.items()}}
    for key in ('database_volume', 'site_volume'):
        records[('volume', names[key])] = {'Name': names[key], 'Driver': 'local', 'Scope': 'local', 'Options': {},
            'Labels': {'muse.reference_job': job.id}}
    if foreign == 'label': records[('container', names['wordpress'])]['Config']['Labels']['muse.reference_job'] = 'f' * 32
    if foreign == 'network': records[('network', names['network'])]['Containers']['f' * 64] = {'Name': 'merchant'}
    if foreign == 'volume': records[('volume', names['site_volume'])]['Options'] = {'device': '/merchant', 'o': 'bind'}
    commands = []
    async def cli(*args, **kwargs):
        commands.append(args)
        if args[0] == 'info': return b'"linux"'
        if args[1] == 'ls':
            value = next(arg for arg in args if arg.startswith(('name=', 'volume=')))
            if value.startswith('volume='):
                return ('f' * 64).encode() if foreign == 'user' else b''
            name = value[5:]
            return name.encode() if (args[0], name) in records else b''
        if args[1] == 'inspect': return json.dumps([records[(args[0], args[2])]]).encode()
        if args[1] == 'rm':
            target = args[-1]
            name = next((key for key, record in records.items() if key[0] == args[0] and record.get('Id') == target), (args[0], target))
            record = records.pop(name)
            if args[0] == 'container': records[('network', names['network'])]['Containers'].pop(record['Id'], None)
            if lost: raise TimeoutError()
            return b''
        raise AssertionError(args)
    monkeypatch.setattr(runner, '_cli', cli)
    return runner, jobs, job, commands, records


async def test_cleanup_removes_only_owned_ids_and_requires_absence_readback(workflow, tmp_path, monkeypatch):
    runner, jobs, job, commands, records = cleanup_fixture(workflow, tmp_path, monkeypatch)
    result = await runner.cleanup(job)
    assert result.state == 'CLEANED' and jobs.read(job.project_id, job.id).state == 'CLEANED'
    assert not records
    removals = [command for command in commands if command[1] == 'rm']
    assert len(removals) == 6
    assert all(len(command[-1]) == 64 for command in removals if command[0] in {'container', 'network'})
    assert not any('prune' in command for command in commands)


async def test_cleanup_allows_changing_container_runtime_statistics(workflow, tmp_path, monkeypatch):
    runner, _, job, _, _ = cleanup_fixture(workflow, tmp_path, monkeypatch)
    original = runner._cleanup_inventory
    reads = 0
    async def inventory(current):
        nonlocal reads
        reads += 1
        records = await original(current)
        for role in ('cli', 'wordpress', 'database'):
            if role in records:
                records[role]['State'] = {'Health': {'FailingStreak': reads}}
                records[role]['NetworkSettings'] = {'SandboxID': str(reads)}
                records[role]['Mounts'].append({'Type': 'bind',
                    'Source': str(runner.root / job.id / 'database-password'), 'RW': False})
                if reads % 2:
                    records[role]['Mounts'].reverse()
        return records
    monkeypatch.setattr(runner, '_cleanup_inventory', inventory)
    assert (await runner.cleanup(job)).state == 'CLEANED'


async def test_cleanup_still_rejects_changed_container_configuration(workflow, tmp_path, monkeypatch):
    runner, jobs, job, commands, _ = cleanup_fixture(workflow, tmp_path, monkeypatch)
    original = runner._cleanup_inventory
    reads = 0
    async def inventory(current):
        nonlocal reads
        reads += 1
        records = await original(current)
        if reads > 1:
            records['cli']['Config']['Image'] = 'foreign-image'
        return records
    monkeypatch.setattr(runner, '_cleanup_inventory', inventory)
    with pytest.raises(CommerceFailure):
        await runner.cleanup(job)
    assert jobs.read(job.project_id, job.id).state == 'CLEANUP_UNKNOWN'
    assert not any(command[1] == 'rm' for command in commands)


@pytest.mark.parametrize('foreign', ['label', 'network', 'volume', 'user'])
async def test_cleanup_refuses_foreign_resources_before_any_removal(workflow, tmp_path, monkeypatch, foreign):
    runner, jobs, job, commands, _ = cleanup_fixture(workflow, tmp_path, monkeypatch, foreign=foreign)
    with pytest.raises(CommerceFailure): await runner.cleanup(job)
    assert jobs.read(job.project_id, job.id).state == 'CLEANUP_UNKNOWN'
    assert not any(command[1] == 'rm' for command in commands)


async def test_lost_cleanup_reply_retains_fence_and_explicit_resume_inspects_remaining(workflow, tmp_path, monkeypatch):
    runner, jobs, job, commands, records = cleanup_fixture(workflow, tmp_path, monkeypatch, lost=True)
    with pytest.raises(CommerceFailure): await runner.cleanup(job)
    current = jobs.read(job.project_id, job.id)
    assert current.state == 'CLEANUP_UNKNOWN' and len(records) == 5
    # Explicit resumption must inspect the already removed resource, not resend
    # a removal against a name that may now refer to another resource.
    count = len(commands)
    with pytest.raises(CommerceFailure): await runner.cleanup(current)
    following = commands[count:]
    assert ('container', 'inspect', job.resource_names['cli']) not in following
    assert len(records) == 4



@pytest.mark.parametrize('tamper', ['none', 'command', 'environment', 'mount', 'tmpfs'])
async def test_owned_interrupted_initializer_is_recoverable_and_cleanable(workflow, tmp_path, monkeypatch, tamper):
    runner, _jobs, job, commands, records = cleanup_fixture(workflow, tmp_path, monkeypatch)
    image = runner.lock['images']['cli']
    # The pending helper occupies only the fixed CLI name and owned site volume.
    record = records[('container', job.resource_names['cli'])]
    record['Config'].update(Image=image, User='0:0', Entrypoint=['php'],
        Cmd=['-r', "foreach (['site' => 0755, 'packages' => 0700] as $name => $mode) { $path = '/muse-volume/' . $name; if (file_exists($path) || !mkdir($path, $mode) || !chown($path, 33) || !chgrp($path, 33)) { exit(2); } }"],
        Env=[], WorkingDir='/var/www/html')
    record['Config']['Labels']['muse.reference_role'] = 'volume-initializer'
    record['Image'] = 'sha256:' + 'a' * 64
    record['HostConfig'] = {'NetworkMode': 'none', 'Privileged': False, 'ReadonlyRootfs': True,
        'CapDrop': ['ALL'], 'CapAdd': ['CHOWN', 'DAC_OVERRIDE'], 'SecurityOpt': ['no-new-privileges:true'],
        'Memory': 67108864, 'NanoCpus': 1000000000, 'PidsLimit': 32, 'PortBindings': {},
        'Tmpfs': {'/var/www/html': 'rw,noexec,nosuid,nodev,size=1m'},
        'Mounts': [{'Type': 'volume', 'Source': job.resource_names['site_volume'], 'Target': '/muse-volume'}]}
    record['Mounts'] = [{'Type': 'volume', 'Name': job.resource_names['site_volume'],
                          'Destination': '/muse-volume', 'RW': True}]
    records[('network', job.resource_names['network'])]['Containers'].pop(record['Id'])
    original_cli = runner._cli
    async def cli(*args, **kwargs):
        if args[:2] == ('image', 'inspect'):
            return json.dumps([{'Id': record['Image'], 'RepoDigests': [image],
                'Config': {'Env': [], 'WorkingDir': '/var/www/html'}}]).encode()
        return await original_cli(*args, **kwargs)
    monkeypatch.setattr(runner, '_cli', cli)
    if tamper == 'command': record['Config']['Cmd'] = ['-r', 'exit(0);']
    if tamper == 'environment': record['Config']['Env'] = ['LD_PRELOAD=/foreign.so']
    if tamper == 'mount': record['HostConfig']['Mounts'][0]['Source'] = 'merchant-site'
    if tamper == 'tmpfs': record['HostConfig']['Tmpfs']['/var/www/html'] = 'rw,exec,size=1g'
    if tamper != 'none':
        with pytest.raises(CommerceFailure): await runner.recover(job)
        with pytest.raises(CommerceFailure): await runner.cleanup(job)
        assert not any(command[1] == 'rm' for command in commands)
        return
    recovered = await runner.recover(job)
    assert 'cli' in recovered['present_resources'] and recovered['site_ready'] is False
    assert (await runner.cleanup(job)).state == 'CLEANED'
    assert not records


