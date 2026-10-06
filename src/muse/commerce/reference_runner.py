"""Host-controlled Docker resource preparation. Does not mark CMS ready.

Missing bootstrap/readback stays UNKNOWN. This runner never installs from the
network, launches arbitrary commands, or automatically repeats a launch.
"""
import asyncio
import ipaddress
import json
import os
import platform
import re
import secrets
import stat
from pathlib import Path

import httpx

from muse.commerce.environment import validate_lock
from muse.commerce.errors import CommerceFailure
from muse.commerce.isolation import DockerCodingSession, _prepare_cli_config
from muse.commerce.reference_environment import (
    CMS_CAPS,
    ReferenceAssetBundle,
    inspect_reference_container,
    inspect_reference_resources,
    reference_readback_manifest,
)
from muse.commerce.repository import digest
from muse.commerce_connector.wordpress import WordPressConnection

_VOLUME_INIT_CODE = (
    "foreach (['site' => 0755, 'packages' => 0700] as $name => $mode) { "
    "$path = '/muse-volume/' . $name; if (file_exists($path) || !mkdir($path, $mode) "
    "|| !chown($path, 33) || !chgrp($path, 33)) { exit(2); } }")


class DockerReferenceRunner(DockerCodingSession):
    def __init__(self, jobs, private_root, versions_lock):
        super().__init__(private_root, versions_lock)
        self.jobs = jobs
        self.preview_proxies = {}

    async def _ensure_preview_proxy(self, job, metadata):
        if self.lock.get('loopback_preview_proxy') is not True:
            return
        from muse.commerce.preview_proxy import LoopbackPreviewProxy
        records = json.loads(await self._cli('inspect', metadata['containers']['wordpress']))
        if len(records) != 1:
            raise ValueError()
        record = records[0]
        inspect_reference_container(record, role='wordpress', job_id=job.id,
            image_digest=self.lock['images']['wordpress'], image_id=metadata['images']['wordpress'],
            port=job.port, private_root=self.root / job.id, loopback_proxy=True)
        networks = json.loads(await self._cli('network', 'inspect', job.resource_names['network']))
        if (len(networks) != 1 or networks[0]['Internal'] is not True
                or networks[0]['Labels'].get('muse.reference_job') != job.id):
            raise ValueError()
        address = record['NetworkSettings']['Networks'][job.resource_names['network']]['IPAddress']
        ip = ipaddress.IPv4Address(address)
        subnets = [ipaddress.ip_network(value['Subnet']) for value in networks[0]['IPAM']['Config'] if value.get('Subnet')]
        if not any(ip in subnet for subnet in subnets):
            raise ValueError()
        existing = self.preview_proxies.get(job.id)
        if existing:
            if existing.address != address or existing.port != job.port or existing.server is None:
                raise ValueError()
            return
        proxy = LoopbackPreviewProxy(address, job.port)
        await proxy.start()
        self.preview_proxies[job.id] = proxy

    async def _preflight(self, job, bundle):
        try:
            validate_lock(self.lock)
            if (platform.system() != 'Linux' or self.executable is None or job.state != 'RESERVED'
                    or not isinstance(bundle, ReferenceAssetBundle) or bundle.source_digest != job.asset_digest
                    or self.root.is_symlink() or any(p.is_symlink() or p.is_junction() for p in self.root.parents)):
                raise ValueError()
            _prepare_cli_config(self.root)
            if json.loads(await self._cli('info', '--format', '{{json .OSType}}')) != 'linux':
                raise ValueError()
            images = {}
            for role in ('wordpress', 'database', 'cli'):
                image = self.lock['images'][role]
                values = json.loads(await self._cli('image', 'inspect', image))
                if (len(values) != 1 or values[0]['Os'] != 'linux' or image not in values[0].get('RepoDigests', [])):
                    raise ValueError()
                images[role] = values[0]['Id']
            for resource, name in [('network', job.resource_names['network']),
                    ('volume', job.resource_names['database_volume']), ('volume', job.resource_names['site_volume']),
                    *[('container', job.resource_names[role]) for role in ('database', 'wordpress', 'cli')]]:
                args = ['--all'] if resource == 'container' else []
                output = await self._cli(resource, 'ls', *args, '--filter', 'name=' + name, '--format', '{{.Name}}' if resource != 'container' else '{{.Names}}')
                if output.strip():
                    raise ValueError()
            return images
        except (ValueError, TypeError, KeyError, OSError, TimeoutError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    def _secret_directory(self, job):
        directory = self.root / job.id
        if directory.exists() or directory.is_symlink() or directory.is_junction():
            raise CommerceFailure('RESOURCE_CONFLICT')
        directory.mkdir(mode=0o700)
        for name in ('database-password', 'database-root-password'):
            fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(secrets.token_urlsafe(48).encode())
                stream.flush()
                os.fsync(stream.fileno())
            # The containing host directory is owner-only. Docker mounts this
            # exact file read-only into services running under other UIDs; 0600
            # would prevent Apache/CLI from reading their database password.
            os.chmod(directory / name, 0o444)
        return directory

    def _run_arguments(self, job, role, directory):
        names = job.resource_names
        args = ['run', '--detach', '--name', names[role], '--pull=never',
                '--label', 'muse.reference_job=' + job.id, '--label', 'muse.reference_role=' + role,
                '--network', names['network'], '--read-only', '--cap-drop=ALL',
                '--security-opt=no-new-privileges:true', '--memory=512m', '--cpus=1', '--pids-limit=128',
                '--mount', 'type=bind,src=' + str(directory / 'database-password') + ',dst=/run/secrets/database_password,readonly',
                '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=64m']
        if role != 'cli':
            for cap in sorted(CMS_CAPS): args += ['--cap-add', cap]
        if role == 'database':
            args += ['--mount', 'type=bind,src=' + str(directory / 'database-root-password') + ',dst=/run/secrets/database_root_password,readonly',
                '--mount', 'type=volume,src=' + names['database_volume'] + ',dst=/var/lib/mysql',
                '--tmpfs', '/run/mysqld:rw,nosuid,nodev,size=16m',
                '--env', 'MARIADB_DATABASE=wordpress', '--env', 'MARIADB_USER=wordpress',
                '--env', 'MARIADB_PASSWORD_FILE=/run/secrets/database_password',
                '--env', 'MARIADB_ROOT_PASSWORD_FILE=/run/secrets/database_root_password']
        else:
            args += ['--mount', 'type=volume,src=' + names['site_volume'] + ',dst=/var/www/html,volume-subpath=site',
                '--env', 'WORDPRESS_DB_HOST=' + names['database'], '--env', 'WORDPRESS_DB_NAME=wordpress',
                '--env', 'WORDPRESS_DB_USER=wordpress', '--env', 'WORDPRESS_DB_PASSWORD_FILE=/run/secrets/database_password']
            if role == 'wordpress':
                if self.lock.get('loopback_preview_proxy') is not True:
                    args += ['--publish', '127.0.0.1:' + str(job.port) + ':80']
                args += ['--tmpfs', '/run/apache2:rw,nosuid,nodev,size=16m', '--tmpfs', '/var/lock/apache2:rw,nosuid,nodev,size=16m',
                    '--mount', 'type=volume,src=' + names['site_volume'] + ',dst=/var/muse-volume',
                    '--env', "WORDPRESS_CONFIG_EXTRA=define('DISALLOW_FILE_EDIT', true); define('DISABLE_WP_CRON', true); define('WP_AUTO_UPDATE_CORE', false);"]
            else:
                args += ['--user=33:33', '--entrypoint=/bin/sh']
        args.append(self.lock['images'][role])
        if role == 'cli': args += ['-c', 'sleep 900']
        return args

    async def prepare(self, job, bundle):
        # Refresh DB before any side effect. Repeated UNKNOWN jobs are handled
        # by inspect-only recovery, never by prepare().
        current = self.jobs.read(job.project_id, job.id)
        if current != job or job.state != 'RESERVED':
            raise CommerceFailure('RESOURCE_CONFLICT')
        images = await self._preflight(job, bundle)
        directory = self._secret_directory(job)
        started = self.jobs.begin(job.id, expected_revision=job.revision)
        names = job.resource_names
        try:
            labels = ('--label', 'muse.reference_job=' + job.id)
            await self._cli('network', 'create', '--internal', *labels, names['network'])
            for key in ('database_volume', 'site_volume'):
                await self._cli('volume', 'create', *labels, names[key])
            networks = json.loads(await self._cli('network', 'inspect', names['network']))
            volumes = json.loads(await self._cli('volume', 'inspect', names['database_volume'], names['site_volume']))
            if not isinstance(networks, list) or len(networks) != 1:
                raise ValueError()
            inspect_reference_resources(job.id, networks[0], volumes)
            # Fixed trusted initializer only: sibling subpaths share a filesystem
            # for atomic rename, while Apache cannot address the private journal.
            await self._cli('run', '--rm', '--name', names['cli'], '--pull=never',
                '--label', 'muse.reference_job=' + job.id, '--label', 'muse.reference_role=volume-initializer',
                '--network=none', '--user=0:0', '--read-only', '--cap-drop=ALL', '--cap-add=CHOWN', '--cap-add=DAC_OVERRIDE',
                '--security-opt=no-new-privileges:true', '--memory=64m', '--cpus=1', '--pids-limit=32',
                '--tmpfs', '/var/www/html:rw,noexec,nosuid,nodev,size=1m',
                '--mount', 'type=volume,src=' + names['site_volume'] + ',dst=/muse-volume',
                '--entrypoint=php', self.lock['images']['cli'], '-r',
                _VOLUME_INIT_CODE, timeout=120)
            containers = {}
            for role in ('database', 'wordpress', 'cli'):
                await self._cli(*self._run_arguments(started, role, directory))
                values = json.loads(await self._cli('inspect', names[role]))
                if not isinstance(values, list) or len(values) != 1:
                    raise ValueError()
                containers[role] = inspect_reference_container(values[0], role=role, job_id=job.id,
                    image_digest=self.lock['images'][role], image_id=images[role], port=job.port, private_root=directory,
                    loopback_proxy=self.lock.get('loopback_preview_proxy') is True)
            networks = json.loads(await self._cli('network', 'inspect', names['network']))
            if not isinstance(networks, list) or len(networks) != 1:
                raise ValueError()
            inspect_reference_resources(job.id, networks[0], volumes,
                containers={identity: role for role, identity in containers.items()})
            metadata = {'job_id': job.id, 'asset_digest': bundle.source_digest, 'containers': containers, 'images': images}
            self._write_private(directory / 'prepared.json', metadata)
            await self._ensure_preview_proxy(started, metadata)
            # Returned data is provisioning diagnostics only. READY requires
            # offline asset/bootstrap/safety readback by the next stage.
            return {'job_id': job.id, 'job_revision': started.revision, 'containers': containers,
                    'asset_digest': bundle.source_digest, 'site_ready': False}
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except (CommerceFailure, ValueError, TypeError, KeyError, OSError, TimeoutError):
            # A CLI error may have created resources. Leave UNKNOWN intact;
            # never delete or relaunch from this exception handler.
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    @staticmethod
    def _write_private(path, value):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(json.dumps(value, separators=(',', ':')).encode())
            stream.flush()
            os.fsync(stream.fileno())

    async def _read_safety(self, connection):
        async with (
            httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10,
                auth=(connection.username, connection.application_password)) as client,
            client.stream('GET', connection.base_url + '/wp-json/muse-staging/v1/safety') as response,
        ):
            if response.status_code != 200:
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 65536:
                    raise CommerceFailure('VERIFICATION_FAILED', 422)
            return json.loads(data)

    async def _wait_ready(self, job, container_id):
        # Fixed read-only probe. Container Running does not imply entrypoint
        # file-copy/ownership or MariaDB initialization has finished.
        if not isinstance(container_id, str) or not re.fullmatch(r'[a-f0-9]{64}', container_id):
            raise ValueError()
        script = """/* MUSE_REFERENCE_READINESS */
ini_set('display_errors', '0');
$root = '/var/www/html';
$ready = is_readable($root . '/wp-load.php') && is_readable($root . '/wp-config.php') &&
    is_writable($root . '/wp-content') && is_readable('/run/secrets/database_password');
if ($ready) {
    $db = mysqli_init(); mysqli_options($db, MYSQLI_OPT_CONNECT_TIMEOUT, 2);
    mysqli_report(MYSQLI_REPORT_OFF);
    $ready = @mysqli_real_connect($db, getenv('WORDPRESS_DB_HOST'), getenv('WORDPRESS_DB_USER'),
        trim(file_get_contents('/run/secrets/database_password')), getenv('WORDPRESS_DB_NAME'));
    if ($ready) { mysqli_close($db); }
}
echo json_encode((bool) $ready);
"""
        async with asyncio.timeout(60):
            for _ in range(30):
                result = await self._cli('exec', container_id, '/usr/local/bin/php', '-r', script,
                    timeout=5, limit=1024)
                ready = json.loads(result)
                if ready is True:
                    return
                if ready is not False:
                    raise ValueError()
                await asyncio.sleep(1)
        raise TimeoutError()

    async def bootstrap(self, job, bundle, *, currency, language):
        """Install once from fixed stdin/assets, then inspect actual safety state."""
        directory = self.root / job.id
        try:
            current = self.jobs.read(job.project_id, job.id)
            project = self.jobs.repo.get_project(job.project_id)
            if (platform.system() != 'Linux' or current != job or job.state != 'UNKNOWN'
                    or digest(project) != job.project_hash or project.revision != job.project_revision
                    or not isinstance(bundle, ReferenceAssetBundle) or bundle.source_digest != job.asset_digest
                    or not re.fullmatch(r'[A-Z]{3}', currency) or not re.fullmatch(r'[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{2,8})*', language)
                    or currency != project.brief.currency or language != project.brief.language
                    or directory.is_symlink() or directory.is_junction()):
                raise ValueError()
            metadata = self._read_private(job, 'prepared.json')
            if (set(metadata) != {'job_id', 'asset_digest', 'containers', 'images'}
                    or metadata['job_id'] != job.id or metadata['asset_digest'] != job.asset_digest):
                raise ValueError()
            names = job.resource_names
            for role in ('database', 'wordpress', 'cli'):
                records = json.loads(await self._cli('inspect', metadata['containers'][role]))
                if len(records) != 1:
                    raise ValueError()
                identity = inspect_reference_container(records[0], role=role, job_id=job.id,
                    image_digest=self.lock['images'][role], image_id=metadata['images'][role], port=job.port, private_root=directory,
                    loopback_proxy=self.lock.get('loopback_preview_proxy') is True)
                if identity != metadata['containers'][role]:
                    raise ValueError()
            networks = json.loads(await self._cli('network', 'inspect', names['network']))
            volumes = json.loads(await self._cli('volume', 'inspect', names['database_volume'], names['site_volume']))
            if len(networks) != 1:
                raise ValueError()
            inspect_reference_resources(job.id, networks[0], volumes,
                containers={identity: role for role, identity in metadata['containers'].items()})
            await self._wait_ready(job, metadata['containers']['cli'])
            if (self.jobs.read(job.project_id, job.id) != job
                    or digest(self.jobs.repo.get_project(job.project_id)) != job.project_hash):
                raise ValueError()
            # Exclusive durable fence before any installation command. Missing
            # reply leaves the marker; another bootstrap must not rotate users.
            self._write_private(directory / 'bootstrap-started.json', {'job_id': job.id, 'asset_digest': job.asset_digest})
            await self._cli('exec', '-i', metadata['containers']['cli'], '/bin/tar', 'xzf', '-', '-C', '/var/www/html',
                '--no-same-owner', stdin=bundle.compressed_tar, timeout=120, limit=16384)
            parameters = {'job_id': job.id, 'project_id': job.project_id, 'connection_id': 'ref-' + job.id,
                'port': job.port, 'wordpress_version': self.lock['wordpress'], 'woocommerce_version': self.lock['woocommerce'],
                'currency': currency, 'language': language, 'admin_password': secrets.token_urlsafe(48),
                'service_password': secrets.token_urlsafe(48), 'execution_secret': secrets.token_urlsafe(48)}
            script = (Path(__file__).parent / 'assets/reference/bootstrap.php').read_text(encoding='utf-8')
            if not script.startswith('<?php\n'):
                raise ValueError()
            output = await self._cli('exec', '-i', metadata['containers']['cli'], '/usr/local/bin/php', '-r', script[6:], '/var/www/html',
                stdin=json.dumps(parameters).encode(), timeout=120, limit=16384)
            value = json.loads(output)
            if (set(value) != {'service_user_id', 'username', 'application_password', 'job_id'}
                    or type(value['service_user_id']) is not int or value['service_user_id'] <= 0
                    or value['username'] != 'muse_reference_service' or value['job_id'] != job.id
                    or not isinstance(value['application_password'], str) or not 16 <= len(value['application_password']) <= 100):
                raise ValueError()
            connection = WordPressConnection(parameters['connection_id'], job.project_id, 'staging',
                'http://127.0.0.1:' + str(job.port), value['username'], value['application_password'], approved_development_http=True)
            # Private file survives safety-read failure for read-only recovery.
            self._write_private(directory / 'connection.json', {'connection_id': connection.connection_id,
                'project_id': connection.project_id, 'environment': 'staging', 'base_url': connection.base_url,
                'username': connection.username, 'application_password': connection.application_password,
                'approved_development_http': True, 'execution_secret': parameters['execution_secret']})
            return await self.verify(job, bundle)
        except (CommerceFailure, ValueError, TypeError, KeyError, OSError, TimeoutError, httpx.HTTPError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    def _read_private(self, job, filename, limit=16384):
        directory = self.root / job.id
        path = directory / filename
        if (any(part.is_symlink() or part.is_junction() for part in (path, directory, *directory.parents))
                or not path.is_file() or path.stat().st_size > limit):
            raise ValueError()
        if os.name == 'posix':
            for part, mode in ((directory, 0o700), (path, 0o600)):
                info = part.stat()
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode:
                    raise ValueError()
        return json.loads(path.read_bytes())

    def _connection(self, job):
        value = self._read_private(job, 'connection.json')
        if (set(value) != {'connection_id', 'project_id', 'environment', 'base_url', 'username',
                    'application_password', 'approved_development_http', 'execution_secret'}
                or value['connection_id'] != 'ref-' + job.id or value['project_id'] != job.project_id
                or value['environment'] != 'staging' or value['base_url'] != 'http://127.0.0.1:' + str(job.port)
                or value['username'] != 'muse_reference_service' or value['approved_development_http'] is not True
                or not isinstance(value['application_password'], str) or not 16 <= len(value['application_password']) <= 100
                or not isinstance(value['execution_secret'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{32,256}', value['execution_secret'])):
            raise ValueError()
        return WordPressConnection(**{key: item for key, item in value.items() if key != 'execution_secret'})

    async def verify(self, job, bundle, *, _code=None):
        """Explicit read-only recovery after installation, never reinstall.

        A lost installation reply without stored credentials cannot recover READY.
        Docker exec is limited to the fixed file-hash reader; no CMS writes occur.
        """
        try:
            current = self.jobs.read(job.project_id, job.id)
            project = self.jobs.repo.get_project(job.project_id)
            validate_lock(self.lock)
            if (platform.system() != 'Linux' or self.executable is None or current != job
                    or job.state not in {'UNKNOWN', 'READY'} or project.revision != job.project_revision
                    or digest(project) != job.project_hash or not isinstance(bundle, ReferenceAssetBundle)
                    or bundle.source_digest != job.asset_digest):
                raise ValueError()
            metadata = self._read_private(job, 'prepared.json')
            marker = self._read_private(job, 'bootstrap-started.json')
            connection = self._connection(job)
            if (marker != {'job_id': job.id, 'asset_digest': job.asset_digest}
                    or set(metadata) != {'job_id', 'asset_digest', 'containers', 'images'}
                    or metadata['job_id'] != job.id or metadata['asset_digest'] != job.asset_digest
                    or set(metadata['containers']) != {'database', 'wordpress', 'cli'}
                    or set(metadata['images']) != {'database', 'wordpress', 'cli'}):
                raise ValueError()
            _prepare_cli_config(self.root)
            if json.loads(await self._cli('info', '--format', '{{json .OSType}}')) != 'linux':
                raise ValueError()
            names = job.resource_names
            for role in ('database', 'wordpress', 'cli'):
                records = json.loads(await self._cli('inspect', metadata['containers'][role]))
                if len(records) != 1:
                    raise ValueError()
                identity = inspect_reference_container(records[0], role=role, job_id=job.id,
                    image_digest=self.lock['images'][role], image_id=metadata['images'][role],
                    port=job.port, private_root=self.root / job.id,
                    loopback_proxy=self.lock.get('loopback_preview_proxy') is True)
                if identity != metadata['containers'][role]:
                    raise ValueError()
            networks = json.loads(await self._cli('network', 'inspect', names['network']))
            volumes = json.loads(await self._cli('volume', 'inspect', names['database_volume'], names['site_volume']))
            if len(networks) != 1:
                raise ValueError()
            inspect_reference_resources(job.id, networks[0], volumes,
                containers={identity: role for role, identity in metadata['containers'].items()})
            await self._ensure_preview_proxy(job, metadata)
            safety = await self._read_safety(connection)
            if (safety.get('wordpress_version') != self.lock['wordpress']
                    or safety.get('woocommerce_version') != self.lock['woocommerce']):
                raise ValueError()
            script = (Path(__file__).parent / 'assets/reference/verify-assets.php').read_text(encoding='utf-8')
            if not script.startswith('<?php\n'):
                raise ValueError()
            if _code is not None and _code.project_id != job.project_id:
                raise ValueError()
            manifest = reference_readback_manifest(bundle, _code)
            output = await self._cli('exec', '-i', metadata['containers']['cli'], '/usr/local/bin/php', '-r', script[6:], '/var/www/html',
                stdin=json.dumps(manifest).encode(), timeout=120, limit=2 * 1024 * 1024)
            if json.loads(output) != manifest:
                raise ValueError()
            evidence = {'job_id': job.id, 'asset_digest': job.asset_digest, 'containers': metadata['containers'],
                'volumes': [names['database_volume'], names['site_volume']], 'network': names['network'], 'safety': safety}
            if job.state == 'READY':
                if job.evidence != evidence or self.jobs.read(job.project_id, job.id) != job:
                    raise ValueError()
                ready = job
            else:
                ready = self.jobs.ready(job.id, job.revision, evidence)
            return {'job_id': job.id, 'job_revision': ready.revision, 'site_ready': True,
                    'safety': safety, 'assets_verified': True}
        except (CommerceFailure, ValueError, TypeError, KeyError, AttributeError, OSError, TimeoutError, httpx.HTTPError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    async def _validate_initializer(self, record, job):
        """Recognize only the exact fixed helper; never resume its command."""
        image = self.lock['images']['cli']
        images = json.loads(await self._cli('image', 'inspect', image))
        if len(images) != 1 or image not in images[0].get('RepoDigests', []):
            raise ValueError()
        config, host = record['Config'], record['HostConfig']
        expected_mounts = [('volume', job.resource_names['site_volume'], '/muse-volume', True)]
        mounts = [(value['Type'], value.get('Name'), value['Destination'], value['RW']) for value in record['Mounts']]
        host_mounts = host.get('Mounts', [])
        if (record['Image'] != images[0]['Id'] or config['Image'] != image or config['User'] != '0:0'
                or config['Entrypoint'] != ['php'] or config['Cmd'] != ['-r', _VOLUME_INIT_CODE]
                or config.get('Env') != images[0]['Config'].get('Env')
                or config.get('WorkingDir') != images[0]['Config'].get('WorkingDir')
                or host['NetworkMode'] != 'none' or host['Privileged'] is not False
                or host['ReadonlyRootfs'] is not True or set(host['CapDrop']) != {'ALL'}
                or {cap.removeprefix('CAP_') for cap in host['CapAdd']} != {'CHOWN', 'DAC_OVERRIDE'}
                or 'no-new-privileges:true' not in host['SecurityOpt']
                or host['Memory'] != 67108864 or host['NanoCpus'] != 1000000000 or host['PidsLimit'] != 32
                or host.get('Tmpfs') != {'/var/www/html': 'rw,noexec,nosuid,nodev,size=1m'}
                or any(host.get(key) for key in ('PortBindings', 'Devices', 'VolumesFrom', 'Links', 'ExtraHosts'))
                or any(host.get(key, '') not in {'', 'private'} for key in ('PidMode', 'IpcMode', 'UTSMode', 'UsernsMode'))
                or mounts != expected_mounts or len(host_mounts) != 1
                or host_mounts[0]['Type'] != 'volume' or host_mounts[0]['Source'] != job.resource_names['site_volume']
                or host_mounts[0]['Target'] != '/muse-volume' or host_mounts[0].get('ReadOnly', False)
                or host_mounts[0].get('VolumeOptions', {}).get('Subpath')):
            raise ValueError()

    async def recover(self, job):
        current = self.jobs.read(job.project_id, job.id)
        if current != job or job.state not in {'UNKNOWN', 'BLOCKED', 'CLEANUP_UNKNOWN', 'READY'}:
            raise CommerceFailure('RESOURCE_CONFLICT')
        try:
            validate_lock(self.lock)
            if platform.system() != 'Linux' or self.executable is None:
                raise ValueError()
            _prepare_cli_config(self.root)
            if json.loads(await self._cli('info', '--format', '{{json .OSType}}')) != 'linux':
                raise ValueError()
            absent, present = [], []
            absent_resources, present_resources = [], []
            names = job.resource_names
            for key, name in names.items():
                kind = 'network' if key == 'network' else 'volume' if key.endswith('_volume') else 'container'
                args = ['--all'] if kind == 'container' else []
                output = await self._cli(kind, 'ls', *args, '--filter', 'name=' + name,
                    '--format', '{{.Names}}' if kind == 'container' else '{{.Name}}')
                found = output.decode('utf-8').splitlines()
                if not found:
                    absent.append(name)
                    absent_resources.append(key)
                    continue
                if found != [name]:
                    raise ValueError()
                records = json.loads(await self._cli(kind, 'inspect', name))
                if not isinstance(records, list) or len(records) != 1:
                    raise ValueError()
                record = records[0]
                labels = record['Config']['Labels'] if kind == 'container' else record['Labels']
                if labels.get('muse.reference_job') != job.id:
                    raise ValueError()
                if kind == 'container':
                    if key == 'cli' and labels.get('muse.reference_role') == 'volume-initializer':
                        await self._validate_initializer(record, job)
                    elif labels.get('muse.reference_role') != key:
                        raise ValueError()
                present.append(name)
                present_resources.append(key)
            # Inventory is not an isolation or CMS readiness attestation.
            # The caller cannot use these strings to authorize publication.
            return {'job_id': job.id, 'job_revision': job.revision, 'site_ready': False,
                    'absent_names': absent, 'present_names': present,
                    'absent_resources': absent_resources, 'present_resources': present_resources}
        except (ValueError, TypeError, KeyError, OSError, TimeoutError, UnicodeError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    async def _cleanup_inventory(self, job):
        """Inspect every fixed resource before deletion; stopped containers count."""
        records = {}
        for key, name in job.resource_names.items():
            kind = 'network' if key == 'network' else 'volume' if key.endswith('_volume') else 'container'
            args = ['--all'] if kind == 'container' else []
            found = (await self._cli(kind, 'ls', *args, '--filter', 'name=' + name,
                '--format', '{{.Names}}' if kind == 'container' else '{{.Name}}')).decode().splitlines()
            if not found:
                continue
            if found != [name]:
                raise ValueError()
            values = json.loads(await self._cli(kind, 'inspect', name))
            if not isinstance(values, list) or len(values) != 1:
                raise ValueError()
            record = values[0]
            labels = record['Config']['Labels'] if kind == 'container' else record['Labels']
            if labels.get('muse.reference_job') != job.id:
                raise ValueError()
            if kind == 'container':
                initializer = key == 'cli' and labels.get('muse.reference_role') == 'volume-initializer'
                if initializer:
                    await self._validate_initializer(record, job)
                if ((not initializer and labels.get('muse.reference_role') != key) or record['Name'] != '/' + name
                        or not re.fullmatch(r'[a-f0-9]{64}', record['Id'])):
                    raise ValueError()
                for mount in record['Mounts']:
                    if mount['Type'] == 'volume':
                        if mount['Name'] != job.resource_names['database_volume' if key == 'database' else 'site_volume']:
                            raise ValueError()
                    elif mount['Type'] == 'bind':
                        allowed = {str(self.root / job.id / 'database-password')}
                        if key == 'database': allowed.add(str(self.root / job.id / 'database-root-password'))
                        if mount['Source'] not in allowed or mount['RW'] is not False:
                            raise ValueError()
                    else:
                        raise ValueError()
            elif kind == 'volume':
                if (record['Name'] != name or record['Driver'] != 'local' or record['Scope'] != 'local'
                        or record.get('Options') not in ({}, None)):
                    raise ValueError()
            else:
                if (record['Name'] != name or not re.fullmatch(r'[a-f0-9]{64}', record['Id'])
                        or record['Driver'] != 'bridge' or record['Scope'] != 'local'
                        or record['Internal'] is not True or record['Attachable'] is not False
                        or record['Ingress'] is not False or record.get('Options') not in ({}, None)):
                    raise ValueError()
            records[key] = record
        containers = {value['Id']: job.resource_names[key] for key, value in records.items()
            if key in {'cli', 'wordpress', 'database'}}
        network = records.get('network')
        if network:
            for identity, endpoint in (network.get('Containers') or {}).items():
                if identity not in containers or endpoint['Name'] != containers[identity]:
                    raise ValueError()
        for key in ('database_volume', 'site_volume'):
            if key in records:
                users = (await self._cli('container', 'ls', '--all', '--filter',
                    'volume=' + job.resource_names[key], '--format', '{{.ID}}', '--no-trunc')).decode().splitlines()
                if not set(users).issubset(containers):
                    raise ValueError()
        return records

    async def cleanup(self, job):
        """Explicit owned-resource deletion; failures retain the durable fence.

        Private credentials are retained for diagnosis, never recursively deleted.
        Resumption always inventories remaining resources before another removal.
        """
        current = self.jobs.read(job.project_id, job.id)
        if current != job:
            raise CommerceFailure('RESOURCE_CONFLICT')
        if job.state == 'CLEANED':
            return job
        try:
            validate_lock(self.lock)
            if platform.system() != 'Linux' or self.executable is None:
                raise ValueError()
            _prepare_cli_config(self.root)
            if json.loads(await self._cli('info', '--format', '{{json .OSType}}')) != 'linux':
                raise ValueError()
            if job.state != 'CLEANUP_UNKNOWN':
                job = self.jobs.begin_cleanup(job.id, job.revision)
            initial = await self._cleanup_inventory(job)
            proxy = self.preview_proxies.pop(job.id, None)
            if proxy is not None:
                await proxy.close()
            for key in ('cli', 'wordpress', 'database', 'network', 'site_volume', 'database_volume'):
                # Recheck all ownership and foreign consumers after every effect.
                remaining = await self._cleanup_inventory(job)
                if key not in remaining:
                    continue
                # Docker updates health/log counters and endpoint statistics while
                # containers run. Compare identity and configuration, not telemetry.
                def stable(record):
                    fields = {field: value for field, value in record.items()
                              if field not in {'State', 'NetworkSettings'}}
                    if 'Mounts' in fields:
                        fields['Mounts'] = sorted(fields['Mounts'], key=lambda mount: json.dumps(mount, sort_keys=True))
                    return fields
                if key not in initial or stable(remaining[key]) != stable(initial[key]) and key != 'network':
                    raise ValueError()
                if key == 'network' and remaining[key]['Id'] != initial[key]['Id']:
                    raise ValueError()
                kind = 'network' if key == 'network' else 'volume' if key.endswith('_volume') else 'container'
                target = remaining[key]['Id'] if kind != 'volume' else job.resource_names[key]
                args = ['--force'] if kind == 'container' else []
                await self._cli(kind, 'rm', *args, target)
            if await self._cleanup_inventory(job):
                raise ValueError()
            return self.jobs.cleaned(job.id, job.revision, absent_names=set(job.resource_names.values()))
        except (CommerceFailure, ValueError, TypeError, KeyError, AttributeError, OSError, TimeoutError, UnicodeError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
