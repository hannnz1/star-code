"""Fixed offline reference assets and actual daemon inspection contracts.

These helpers alone do not provision a store or attest Linux isolation. Only
the trusted reference runner may use them; they are not agent tools.
"""
import gzip
import hashlib
import io
import re
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from muse.commerce.environment import validate_lock
from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce.theme import seed_files

CONNECTOR_FILES = ('muse-connector.php', *('includes/' + name + '.php' for name in (
    'permissions', 'store-setup', 'shipping', 'snapshot', 'protocol', 'receipts', 'operations',
    'products', 'theme-deploy', 'navigation', 'pages', 'media')))
CMS_CAPS = {'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'SETUID', 'SETGID', 'NET_BIND_SERVICE'}
MAX_ASSET_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class ReferenceAssetBundle:
    source_digest: str
    file_count: int
    manifest: tuple = field(repr=False)
    compressed_tar: bytes = field(repr=False)


def load_reference_assets(lock, woocommerce_archive):
    try:
        validate_lock(lock)
        path = Path(woocommerce_archive).absolute()
        if (any(p.is_symlink() or p.is_junction() for p in (path, *path.parents))
                or not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024 * 1024):
            raise ValueError()
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != lock.get('woocommerce_sha256'):
            raise ValueError()
        files, seen, total = {}, set(), 0
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if not 1 <= len(archive.infolist()) <= 10000:
                raise ValueError()
            for info in archive.infolist():
                name = info.filename
                parts = PurePosixPath(name).parts
                if (not parts or parts[0] != 'woocommerce' or name.startswith('/') or '\\' in name
                        or any(p in {'.', '..'} or ':' in p for p in name.split('/') if p)
                        or stat.S_ISLNK(info.external_attr >> 16)
                        or not name.isascii() or name.casefold() in seen):
                    raise ValueError()
                seen.add(name.casefold())
                if info.is_dir():
                    continue
                if len(parts) < 2 or info.file_size > 16 * 1024 * 1024:
                    raise ValueError()
                total += info.file_size
                if total > MAX_ASSET_BYTES:
                    raise ValueError()
                files['wp-content/plugins/' + name] = archive.read(info)
        header = files.get('wp-content/plugins/woocommerce/woocommerce.php', b'')
        versions = re.findall(rb'\bVersion:\s*(\d+(?:\.\d+){1,2})\b', header[:16384])
        if versions != [lock['woocommerce'].encode()]:
            raise ValueError()
        installed = Path(__file__).parent / 'assets' / 'connector'
        connector = installed if installed.is_dir() else Path(__file__).resolve().parents[3] / 'wordpress' / 'muse-connector'
        for name in CONNECTOR_FILES:
            files['wp-content/plugins/muse-connector/' + name] = (connector / name).read_bytes()
        for name, data in seed_files().items():
            files['wp-content/themes/muse-storefront/' + name] = data
        files['wp-content/mu-plugins/muse-staging-safety.php'] = (Path(__file__).parent / 'assets/reference/staging-safety.php').read_bytes()
        manifest = tuple({'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'byte_size': len(data)}
                         for name, data in sorted(files.items()))
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as packed:
            for name, data in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size, info.uid, info.gid, info.mode, info.mtime = len(data), 33, 33, 0o644, 0
                packed.addfile(info, io.BytesIO(data))
        return ReferenceAssetBundle(digest(manifest), len(files), manifest, gzip.compress(stream.getvalue(), mtime=0))
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None


def reference_readback_manifest(bundle, code=None):
    """Fixed plugins remain pinned; deployed theme must match verified capture."""
    if code is None:
        return list(bundle.manifest)
    from muse.commerce.coding import verify_coding_artifact
    verify_coding_artifact(code)
    fixed = [dict(row) for row in bundle.manifest if not row['path'].startswith('wp-content/themes/')]
    return fixed + [{'path': 'wp-content/themes/muse-storefront/' + row['path'],
                     'sha256': row['sha256'], 'byte_size': row['bytes']} for row in code.package.files_manifest]


def reference_names(job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise CommerceFailure('INPUT_INVALID', 422)
    prefix = 'muse-ref-' + job_id
    return {'network': prefix + '-network', 'database_volume': prefix + '-database', 'site_volume': prefix + '-site',
            **{role: prefix + '-' + role for role in ('wordpress', 'database', 'cli')}}


def inspect_reference_resources(job_id, network, volumes, *, containers=None):
    try:
        names = reference_names(job_id)
        expected_volumes = {names['database_volume'], names['site_volume']}
        if (network['Name'] != names['network'] or not re.fullmatch(r'[a-f0-9]{64}', network['Id'])
                or network['Driver'] != 'bridge' or network['Scope'] != 'local'
                or network['Internal'] is not True or network['Attachable'] is not False
                or network['Ingress'] is not False or network.get('Options') not in ({}, None)
                or network['Labels'].get('muse.reference_job') != job_id
                or set(network.get('Containers') or {}) != set(containers or {})
                or not isinstance(volumes, list) or len(volumes) != 2
                or {volume['Name'] for volume in volumes} != expected_volumes):
            raise ValueError()
        for volume in volumes:
            if (volume['Driver'] != 'local' or volume['Scope'] != 'local'
                    or volume.get('Options') not in ({}, None)
                    or volume['Labels'].get('muse.reference_job') != job_id):
                raise ValueError()
        for identity, role in (containers or {}).items():
            if role not in {'wordpress', 'database', 'cli'} or network['Containers'][identity]['Name'] != names[role]:
                raise ValueError()
        return names['network']
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None


def inspect_reference_container(record, *, role, job_id, image_digest, image_id, port, private_root, loopback_proxy=False):
    try:
        names = reference_names(job_id)
        if role not in {'wordpress', 'database', 'cli'} or type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError()
        config, host, network = record['Config'], record['HostConfig'], record['NetworkSettings']
        ports = {'80/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(port)}]} if role == 'wordpress' and not loopback_proxy else {}
        expected_mounts = [('bind', str(Path(private_root) / 'database-password'), '/run/secrets/database_password', False)]
        if role == 'database':
            expected_mounts += [('bind', str(Path(private_root) / 'database-root-password'), '/run/secrets/database_root_password', False)]
        expected_mounts += [('volume', names['database_volume' if role == 'database' else 'site_volume'],
                            '/var/lib/mysql' if role == 'database' else '/var/www/html', True)]
        if role == 'wordpress':
            expected_mounts += [('volume', names['site_volume'], '/var/muse-volume', True)]
        if role != 'database':
            expected_subpaths = {'/var/www/html': 'site'}
            if role == 'wordpress':
                expected_subpaths['/var/muse-volume'] = None
            actual_subpaths = {m['Target']: m.get('VolumeOptions', {}).get('Subpath')
                              for m in host.get('Mounts', []) if m['Type'] == 'volume'
                              and m['Source'] == names['site_volume']}
            if actual_subpaths != expected_subpaths:
                raise ValueError()
        actual_mounts = [(m['Type'], m.get('Name') if m['Type'] == 'volume' else m.get('Source'), m['Destination'], m['RW'])
                         for m in record['Mounts']]
        if (not re.fullmatch(r'[a-f0-9]{64}', record['Id']) or record['Image'] != image_id
                or not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id)
                or config['Image'] != image_digest or not re.fullmatch(r'[a-zA-Z0-9._/:-]+@sha256:[a-f0-9]{64}', image_digest)
                or record['State']['Running'] is not True or config['User'] != ('33:33' if role == 'cli' else '')
                or config['Labels'].get('muse.reference_job') != job_id or config['Labels'].get('muse.reference_role') != role
                or host['Privileged'] is not False or host['ReadonlyRootfs'] is not True
                or set(host['CapDrop']) != {'ALL'} or {cap.removeprefix('CAP_') for cap in (host.get('CapAdd') or [])} != (set() if role == 'cli' else CMS_CAPS)
                or 'no-new-privileges:true' not in host['SecurityOpt'] or host['NetworkMode'] != names['network']
                or set(network['Networks']) != {names['network']}
                or {key: value for key, value in (network.get('Ports') or {}).items() if value is not None} != ports
                or (host.get('PortBindings') or {}) != ports
                or host['Memory'] != 536870912 or host['NanoCpus'] != 1000000000 or host['PidsLimit'] != 128
                or any(host.get(key, '') not in {'', 'private'} for key in ('PidMode', 'IpcMode', 'UTSMode', 'UsernsMode'))
                or any(host.get(key) for key in ('Devices', 'VolumesFrom', 'Links', 'ExtraHosts'))
                or sorted(actual_mounts) != sorted(expected_mounts)):
            raise ValueError()
        return record['Id']
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
