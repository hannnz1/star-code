"""Docker inspection contract tests are not a real Linux boundary attestation."""
import copy

import pytest


async def test_host_cli_does_not_search_inherited_windows_or_secret_paths(tmp_path, monkeypatch):
    import asyncio
    import os
    from types import SimpleNamespace

    from muse.commerce.isolation import DockerCodingSession
    monkeypatch.setenv('PATH', '/mnt/c/private-plugin-path:/usr/bin')
    monkeypatch.setenv('DOCKER_HOST', 'tcp://untrusted.invalid:2375')
    monkeypatch.setenv('OPENAI_API_KEY', 'never-forward')
    captured = {}
    class Input:
        def close(self):
            pass
    async def wait():
        return 0
    async def spawn(*args, **kwargs):
        captured.update(kwargs)
        stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
        stdout.feed_data(b'linux')
        stdout.feed_eof()
        stderr.feed_eof()
        return SimpleNamespace(stdin=Input(), stdout=stdout, stderr=stderr, wait=wait, returncode=0)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    session = DockerCodingSession(tmp_path, {})
    session.executable = '/usr/bin/docker'
    assert await session._cli('info') == b'linux'
    assert captured['env']['PATH'] == os.defpath
    assert set(captured['env']) <= {'PATH', 'LANG', 'LC_ALL'}

from muse.commerce.errors import CommerceFailure


def inspected():
    return {'Id': 'c' * 64, 'Image': 'sha256:' + 'a' * 64, 'State': {'Running': True},
            'Config': {'User': '65532:65532', 'Labels': {'muse.coding_job': 'job'},
                       'Entrypoint': ['/usr/local/bin/python'],
                       'Env': ['PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/tmp']},
            'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'NetworkMode': 'none',
                'CapDrop': ['ALL'], 'CapAdd': None, 'SecurityOpt': ['no-new-privileges:true'],
                'Binds': None, 'Devices': [], 'Mounts': [], 'PortBindings': {},
                'PidsLimit': 32, 'Memory': 134217728, 'NanoCpus': 1000000000,
                'Tmpfs': {'/workspace': 'rw,noexec,nosuid,nodev,size=8m,uid=65532,gid=65532,mode=700',
                          '/tmp': 'rw,noexec,nosuid,nodev,size=8m,uid=65532,gid=65532,mode=700'}},
            'Mounts': [], 'NetworkSettings': {'Ports': {}}}


def test_hardened_inspection_is_accepted_without_calling_it_an_os_probe():
    from muse.commerce.isolation import inspect_boundary
    identity = inspect_boundary(inspected(), job_id='job', image_id='sha256:' + 'a' * 64)
    assert identity == 'c' * 64


@pytest.mark.parametrize('section,key,value', [
    ('Config', 'User', 'root'), ('Config', 'Labels', {'muse.coding_job': 'other'}),
    ('Config', 'Env', ['OPENAI_API_KEY=never-propagate']),
    ('HostConfig', 'ReadonlyRootfs', False), ('HostConfig', 'Privileged', True),
    ('HostConfig', 'NetworkMode', 'bridge'), ('HostConfig', 'CapAdd', ['SYS_ADMIN']),
    ('HostConfig', 'SecurityOpt', []), ('HostConfig', 'Binds', ['/private:/private']),
    ('HostConfig', 'Devices', [{'PathOnHost': '/dev/sda'}]),
    ('HostConfig', 'PortBindings', {'80/tcp': [{'HostPort': '8080'}]}),
    ('HostConfig', 'PidsLimit', 0), ('HostConfig', 'Memory', 0),
    ('HostConfig', 'Tmpfs', {'/workspace': 'rw'}),
    ('HostConfig', 'PidMode', 'host'), ('HostConfig', 'IpcMode', 'host'),
    ('HostConfig', 'UTSMode', 'host'), ('HostConfig', 'UsernsMode', 'host'),
    ('State', 'Running', False), ('NetworkSettings', 'Ports', {'80/tcp': [{}]}),
])
def test_weakened_or_secret_bearing_execution_is_rejected(section, key, value):
    from muse.commerce.isolation import inspect_boundary
    record = copy.deepcopy(inspected())
    record[section][key] = value
    with pytest.raises(CommerceFailure) as error:
        inspect_boundary(record, job_id='job', image_id='sha256:' + 'a' * 64)
    assert error.value.public.code == 'EXECUTION_BOUNDARY_UNAVAILABLE'


def test_wrong_image_and_mounted_docker_socket_are_rejected():
    from muse.commerce.isolation import inspect_boundary
    record = inspected()
    record['Mounts'] = [{'Source': '/var/run/docker.sock', 'Destination': '/var/run/docker.sock'}]
    with pytest.raises(CommerceFailure):
        inspect_boundary(record, job_id='job', image_id='sha256:' + 'a' * 64)
    with pytest.raises(CommerceFailure):
        inspect_boundary(inspected(), job_id='job', image_id='sha256:' + 'b' * 64)


@pytest.mark.asyncio
async def test_unverified_image_never_starts_a_coding_container(tmp_path):
    from muse.commerce.isolation import DockerCodingSession
    session = DockerCodingSession(tmp_path, {'verified': False, 'images': {}})
    with pytest.raises(CommerceFailure) as error:
        await session.start({})
    assert error.value.public.code == 'EXECUTION_BOUNDARY_UNAVAILABLE'
    assert not tmp_path.joinpath('docker-config').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('attack', ['hardlink', 'directory_file', 'wrong_owner'])
async def test_private_docker_config_rejects_links_or_wrong_owner_before_cli(tmp_path, monkeypatch, attack):
    import os

    from muse.commerce import isolation
    from muse.commerce.models import SiteBrief, StoreSnapshot
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.theme import render_site_files
    monkeypatch.setattr(isolation.platform, 'system', lambda: 'Linux')
    calls = []
    class Probe(isolation.DockerCodingSession):
        async def _cli(self, *args, **kwargs):
            calls.append(args)
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
    root = tmp_path / 'private'; root.mkdir()
    victim = tmp_path / 'credential-fixture.json'; victim.write_text('private-fixture', encoding='utf-8')
    config = root / 'docker-config'
    if attack == 'directory_file': config.write_text('private-fixture', encoding='utf-8')
    else:
        config.mkdir()
        if attack == 'hardlink': os.link(victim, config / 'config.json')
        else: monkeypatch.setattr(isolation.os, 'geteuid', lambda: root.stat().st_uid + 1, raising=False)
    session = Probe(root, {'verified': True, 'images': {'coding': 'coding@sha256:' + 'a' * 64}})
    blueprint = build_site_blueprint(SiteBrief(brand_name='Fixture', language='en', currency='USD'),
                                     StoreSnapshot(project_id='project', environment='staging'))
    with pytest.raises(CommerceFailure): await session.start(render_site_files(blueprint, []))
    assert victim.read_text(encoding='utf-8') == 'private-fixture'
    assert not calls
