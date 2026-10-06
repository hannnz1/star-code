import hashlib
import io
import zipfile
from copy import deepcopy

import pytest

from muse.commerce.errors import CommerceFailure


def archive(entries=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as packed:
        for name, content in (entries or {'woocommerce/woocommerce.php': b'<?php\n/* Version: 11.1.2 */'}).items():
            packed.writestr(name, content)
    return out.getvalue()


def manifest(content):
    return {'verified': True, 'wordpress': '7.1.2', 'woocommerce': '11.1.2',
            'woocommerce_sha256': hashlib.sha256(content).hexdigest(),
            'images': {role: role + '@sha256:' + 'a' * 64 for role in ('wordpress', 'database', 'cli')}}


def test_verified_offline_assets_are_fixed_bounded_and_exclude_test_faults(tmp_path):
    from muse.commerce.reference_environment import load_reference_assets
    data = archive()
    path = tmp_path / 'woo.zip'
    path.write_bytes(data)
    bundle = load_reference_assets(manifest(data), path)
    assert bundle.file_count == 29  # 1 fixture Woo + 12 Connector + 15 theme + 1 safety
    assert len(bundle.source_digest) == 64
    assert 'fixture' not in repr(bundle) and 'Version' not in repr(bundle)
    assert bundle.manifest == load_reference_assets(manifest(data), path).manifest
    assert all('fault' not in item['path'] for item in bundle.manifest)
    assert any(item['path'].endswith('mu-plugins/muse-staging-safety.php') for item in bundle.manifest)


@pytest.mark.parametrize('problem', ['unverified', 'hash', 'version', 'traversal', 'foreign', 'duplicate'])
def test_bad_offline_bundle_is_rejected_before_any_docker_command(tmp_path, problem):
    from muse.commerce.reference_environment import load_reference_assets
    entries = {'woocommerce/woocommerce.php': b'<?php\n/* Version: 11.1.2 */'}
    if problem == 'version': entries['woocommerce/woocommerce.php'] = b'<?php\n/* Version: 1.0.0 */'
    if problem == 'traversal': entries['woocommerce/../wp-config.php'] = b'bad'
    if problem == 'foreign': entries['other/plugin.php'] = b'bad'
    if problem == 'duplicate': entries['woocommerce/WooCommerce.php'] = b'bad'
    data = archive(entries)
    lock = manifest(data)
    if problem == 'unverified': lock['verified'] = False
    if problem == 'hash': lock['woocommerce_sha256'] = '0' * 64
    path = tmp_path / 'woo.zip'
    path.write_bytes(data)
    with pytest.raises(CommerceFailure): load_reference_assets(lock, path)


def inspected(role, job, private_root):
    from muse.commerce.reference_environment import reference_names
    names = reference_names(job)
    binds = [('database-password', '/run/secrets/database_password')]
    if role == 'database': binds += [('database-root-password', '/run/secrets/database_root_password')]
    mounts = [{'Type': 'bind', 'Source': str(private_root / name), 'Destination': target, 'RW': False} for name, target in binds]
    mounts += [{'Type': 'volume', 'Name': names['database_volume' if role == 'database' else 'site_volume'],
                'Destination': '/var/lib/mysql' if role == 'database' else '/var/www/html', 'RW': True}]
    volume_mounts = []
    if role != 'database':
        volume_mounts.append({'Type': 'volume', 'Source': names['site_volume'], 'Target': '/var/www/html',
                              'VolumeOptions': {'Subpath': 'site'}})
    if role == 'wordpress':
        mounts.append({'Type': 'volume', 'Name': names['site_volume'], 'Destination': '/var/muse-volume', 'RW': True})
        volume_mounts.append({'Type': 'volume', 'Source': names['site_volume'], 'Target': '/var/muse-volume',
                              'VolumeOptions': {}})
    ports = {'80/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '63660'}]} if role == 'wordpress' else {}
    return {'Id': 'b' * 64, 'Image': 'sha256:' + 'c' * 64, 'State': {'Running': True},
        'Config': {'Image': role + '@sha256:' + 'a' * 64, 'User': '33:33' if role == 'cli' else '',
                   'Labels': {'muse.reference_job': job, 'muse.reference_role': role}},
        'HostConfig': {'Privileged': False, 'ReadonlyRootfs': True, 'CapDrop': ['ALL'],
            'CapAdd': [] if role == 'cli' else ['CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'SETUID', 'SETGID', 'NET_BIND_SERVICE'],
            'SecurityOpt': ['no-new-privileges:true'], 'NetworkMode': names['network'],
            'Memory': 536870912, 'NanoCpus': 1000000000, 'PidsLimit': 128,
            'PortBindings': ports, 'Mounts': volume_mounts}, 'Mounts': mounts,
        'NetworkSettings': {'Ports': ports, 'Networks': {names['network']: {}}}}


@pytest.mark.parametrize('role', ['wordpress', 'database', 'cli'])
def test_reference_inspection_is_role_specific_and_does_not_accept_host_access(tmp_path, role):
    from muse.commerce.reference_environment import inspect_reference_container
    job = 'd' * 32
    record = inspected(role, job, tmp_path)
    kwargs = {'role': role, 'job_id': job, 'image_digest': role + '@sha256:' + 'a' * 64,
              'image_id': 'sha256:' + 'c' * 64, 'port': 63660, 'private_root': tmp_path}
    assert inspect_reference_container(record, **kwargs) == 'b' * 64
    for field, changed in [('Privileged', True), ('ReadonlyRootfs', False), ('NetworkMode', 'host'),
                           ('PidMode', 'host'), ('Devices', [{}]), ('CapAdd', ['SYS_ADMIN']), ('Memory', 0)]:
        broken = deepcopy(record)
        broken['HostConfig'][field] = changed
        with pytest.raises(CommerceFailure): inspect_reference_container(broken, **kwargs)
    for changed in [ {'Type': 'bind', 'Source': '/var/run/docker.sock', 'Destination': '/var/run/docker.sock', 'RW': True},
                    {'Type': 'volume', 'Name': 'merchant-site', 'Destination': '/var/www/html', 'RW': True} ]:
        broken = deepcopy(record)
        broken['Mounts'].append(changed)
        with pytest.raises(CommerceFailure): inspect_reference_container(broken, **kwargs)


def test_private_network_and_volume_inspection_rejects_external_driver_or_host_bind():
    from muse.commerce.reference_environment import (
        inspect_reference_resources,
        reference_names,
    )
    job = 'd' * 32
    names = reference_names(job)
    network = {'Name': names['network'], 'Id': 'e' * 64, 'Driver': 'bridge', 'Scope': 'local',
               'Internal': True, 'Attachable': False, 'Ingress': False, 'Options': {},
               'Labels': {'muse.reference_job': job}, 'Containers': {}}
    volumes = [{'Name': names[key], 'Driver': 'local', 'Options': {}, 'Scope': 'local',
                'Labels': {'muse.reference_job': job}} for key in ('database_volume', 'site_volume')]
    assert inspect_reference_resources(job, network, volumes) == names['network']
    for key, value in [('Internal', False), ('Driver', 'overlay'), ('Options', {'external': 'yes'}),
                       ('Containers', {'foreign': {'Name': 'merchant'}}), ('Labels', {})]:
        broken = deepcopy(network)
        broken[key] = value
        with pytest.raises(CommerceFailure): inspect_reference_resources(job, broken, volumes)
    for changes in [{'Driver': 'nfs'}, {'Options': {'type': 'none', 'device': '/home', 'o': 'bind'}},
                    {'Name': 'merchant-data'}, {'Labels': {}}]:
        broken = deepcopy(volumes)
        broken[0].update(changes)
        with pytest.raises(CommerceFailure): inspect_reference_resources(job, network, broken)


def test_docker_29_capability_names_and_unpublished_ports_keep_same_boundary(tmp_path):
    from muse.commerce.reference_environment import inspect_reference_container
    job = 'd' * 32
    record = inspected('database', job, tmp_path)
    record['HostConfig']['CapAdd'] = ['CAP_' + cap for cap in record['HostConfig']['CapAdd']]
    record['NetworkSettings']['Ports'] = {'3306/tcp': None}
    kwargs = {'role': 'database', 'job_id': job, 'image_digest': 'database@sha256:' + 'a' * 64,
              'image_id': 'sha256:' + 'c' * 64, 'port': 63660, 'private_root': tmp_path}
    assert inspect_reference_container(record, **kwargs) == 'b' * 64
    record['NetworkSettings']['Ports']['3306/tcp'] = [{'HostIp': '0.0.0.0', 'HostPort': '3306'}]
    with pytest.raises(CommerceFailure):
        inspect_reference_container(record, **kwargs)

