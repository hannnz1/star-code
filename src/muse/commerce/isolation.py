"""Host-controlled Docker execution for static storefront code only.

Container inspection is necessary but insufficient: each new session also runs
real UID/capability/filesystem/network probes. No successful mock is recorded as
an isolation attestation. Missing Linux or a verified coding image fails closed.
"""
import asyncio
import base64
import json
import os
import platform
import re
import shutil
import stat
import uuid
from pathlib import Path

from muse.commerce.errors import CommerceFailure
from muse.commerce.theme import ALLOWED_FILES, MAX_PACKAGE, validate_theme_files

TMPFS = {path: 'rw,noexec,nosuid,nodev,size=8m,uid=65532,gid=65532,mode=700' for path in ('/workspace', '/tmp')}
ENV_KEYS = {'PATH', 'HOME', 'LANG', 'PYTHON_VERSION', 'PYTHON_SHA256', 'GPG_KEY'}
LIFETIME = 'import time; time.sleep(900)'
PROBE = '''import json, os, socket
status = open('/proc/self/status').read().splitlines()
caps = next(x.split(':', 1)[1].strip() for x in status if x.startswith('CapEff:'))
network_blocked = True
s = socket.socket(); s.settimeout(1)
try:
    s.connect(('198.18.0.1', 443)); network_blocked = False
except OSError:
    pass
finally:
    s.close()
root_blocked = False
try:
    open('/muse-write-probe', 'w').close()
except OSError:
    root_blocked = True
with open('/workspace/.muse-write-probe', 'w') as f: f.write('probe')
os.unlink('/workspace/.muse-write-probe')
print(json.dumps({'uid': os.getuid(), 'capabilities': int(caps, 16),
    'network_blocked': network_blocked, 'root_blocked': root_blocked,
    'docker_socket_absent': not os.path.exists('/var/run/docker.sock'),
    'secrets_absent': not os.path.exists('/run/secrets')}))
'''
UPLOAD = '''import base64, json, os, sys
for name, data in json.load(sys.stdin).items():
    path = '/workspace/' + name
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'xb') as f: f.write(base64.b64decode(data, validate=True))
'''
CAPTURE = '''import io, os, stat, sys, tarfile
allowed = set(sys.argv[1:]); found = set()
for parent, dirs, files in os.walk('/workspace', followlinks=False):
    for name in dirs + files:
        p = os.path.join(parent, name)
        if os.path.islink(p): raise ValueError('Code links forbidden')
    for name in files: found.add(os.path.relpath(os.path.join(parent, name), '/workspace'))
if found != allowed: raise ValueError('Code manifest differs')
out = io.BytesIO()
with tarfile.open(fileobj=out, mode='w') as archive:
    for name in sorted(allowed):
        path = '/workspace/' + name
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as f:
            before = os.fstat(f.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 524288: raise ValueError('Invalid code file')
            data = f.read(524289)
            if len(data) != before.st_size: raise ValueError('Changed capture')
        info = tarfile.TarInfo(name); info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
sys.stdout.buffer.write(out.getvalue())
'''


def inspect_boundary(record, *, job_id, image_id):
    """Validate actual daemon inspection, never a model-supplied checkpoint flag."""
    try:
        config, host = record['Config'], record['HostConfig']
        identity = record['Id']
        if (not re.fullmatch(r'[a-f0-9]{64}', identity) or record['Image'] != image_id
                or record['State']['Running'] is not True or config['User'] != '65532:65532'
                or config['Labels'].get('muse.coding_job') != job_id
                or config['Entrypoint'] != ['/usr/local/bin/python']
                or any(item.split('=', 1)[0] not in ENV_KEYS for item in config.get('Env', []))
                or host['ReadonlyRootfs'] is not True or host['Privileged'] is not False
                or host['NetworkMode'] != 'none' or set(host['CapDrop']) != {'ALL'} or host.get('CapAdd')
                or host.get('PidMode', '') not in {'', 'private'}
                or host.get('IpcMode', '') not in {'', 'private'}
                or host.get('UTSMode', '') not in {'', 'private'}
                or host.get('UsernsMode', '') not in {'', 'private'}
                or 'no-new-privileges:true' not in host['SecurityOpt']
                or any(host.get(key) for key in ('Binds', 'Devices', 'Mounts', 'PortBindings', 'VolumesFrom'))
                or record.get('Mounts') or record['NetworkSettings'].get('Ports')
                or host['PidsLimit'] != 32 or host['Memory'] != 134217728 or host['NanoCpus'] != 1000000000
                or host['Tmpfs'] != TMPFS):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
    return identity


def _prepare_cli_config(root):
    """Never truncate a linked credential file while preparing isolated CLI state."""
    directory_fd = file_fd = None
    try:
        if root == Path(root.anchor) or '..' in root.parts:
            raise ValueError('Private job directory required')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        owner = os.geteuid() if hasattr(os, 'geteuid') else root.lstat().st_uid
        for path in (root, root / 'docker-config'):
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError('Linked config directory')
            path.mkdir(exist_ok=True, mode=0o700)
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner:
                raise ValueError('Private config ownership required')
            path.chmod(0o700)
        directory = root / 'docker-config'
        if hasattr(os, 'O_DIRECTORY') and os.open in os.supports_dir_fd:
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0))
            if os.fstat(directory_fd).st_uid != owner:
                raise ValueError('Directory changed')
        config = directory / 'config.json'
        if config.is_symlink():
            raise ValueError('Linked config file')
        # Deliberately no O_TRUNC: verify the opened inode BEFORE truncation.
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        file_fd = os.open('config.json', flags, 0o600, dir_fd=directory_fd) if directory_fd is not None else os.open(config, flags, 0o600)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != owner:
            raise ValueError('Private unlinked config file required')
        if hasattr(os, 'fchmod'): os.fchmod(file_fd, 0o600)
        os.ftruncate(file_fd, 0)
        os.write(file_fd, b'{}')
        os.fsync(file_fd)
    except (OSError, ValueError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
    finally:
        if file_fd is not None: os.close(file_fd)
        if directory_fd is not None: os.close(directory_fd)


class DockerCodingSession:
    def __init__(self, private_root: Path, versions_lock: dict):
        self.root, self.lock = Path(private_root).absolute(), dict(versions_lock)
        self.job_id, self.container, self.image_id = uuid.uuid4().hex, None, None
        self.attestation = None
        self.executable = shutil.which('docker')

    async def _cli(self, *args, stdin=None, limit=16384, timeout=30):
        if self.executable is None:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        # WSL inherits Windows PATH entries. Docker scans PATH for credential
        # helpers/plugins, which can stall on Windows mounts even with {} config.
        # The trusted executable is already resolved; child lookup needs only
        # standard host utilities, never user/provider/plugin search paths.
        env = {'PATH': os.defpath, **{name: os.environ[name] for name in ('LANG', 'LC_ALL') if name in os.environ}}
        process = await asyncio.create_subprocess_exec(self.executable, '--config', str(self.root / 'docker-config'), *args,
            env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        async def read(stream):
            data = bytearray()
            while chunk := await stream.read(4096):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError('Coding output limit exceeded')
            return bytes(data)
        async def write():
            if stdin:
                process.stdin.write(stdin)
                await process.stdin.drain()
            process.stdin.close()
        try:
            async with asyncio.timeout(timeout):
                await write()
                stdout, _stderr = await asyncio.gather(read(process.stdout), read(process.stderr))
                code = await process.wait()
                if code:
                    raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
                return stdout
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise

    async def _inspection(self):
        record = json.loads(await self._cli('inspect', self.container))
        if not isinstance(record, list) or len(record) != 1:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        return inspect_boundary(record[0], job_id=self.job_id, image_id=self.image_id)

    async def start(self, files):
        image = self.lock.get('images', {}).get('coding', '')
        if (platform.system() != 'Linux' or self.lock.get('verified') is not True
                or not re.fullmatch(r'[a-zA-Z0-9._/:-]+@sha256:[a-f0-9]{64}', image) or self.container):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        validate_theme_files(files)
        if self.root.is_symlink() or any(p.is_symlink() for p in self.root.parents):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        _prepare_cli_config(self.root)
        try:
            info = json.loads(await self._cli('info', '--format', '{{json .OSType}}'))
            if info != 'linux':
                raise ValueError('Linux daemon required')
            images = json.loads(await self._cli('image', 'inspect', image))
            if len(images) != 1 or images[0]['Os'] != 'linux' or image not in images[0].get('RepoDigests', []):
                raise ValueError('Pinned image unavailable')
            self.image_id = images[0]['Id']
            name = 'muse-code-' + self.job_id
            # The name is reserved before launching so any cancellation can remove it.
            self.container = name
            await self._cli('run', '--detach', '--name', name, '--label', 'muse.coding_job=' + self.job_id,
                '--pull=never', '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
                '--user=65532:65532', '--pids-limit=32', '--memory=128m', '--cpus=1', '--workdir=/workspace',
                '--tmpfs=/workspace:' + TMPFS['/workspace'], '--tmpfs=/tmp:' + TMPFS['/tmp'],
                '--env=HOME=/tmp', '--entrypoint=/usr/local/bin/python', image, '-I', '-c', LIFETIME)
            identity = await self._inspection()
            proof = json.loads(await self._cli('exec', self.container, '/usr/local/bin/python', '-I', '-c', PROBE))
            expected = {'uid': 65532, 'capabilities': 0, 'network_blocked': True, 'root_blocked': True,
                        'docker_socket_absent': True, 'secrets_absent': True}
            if proof != expected:
                raise ValueError('Execution probes failed')
            payload = json.dumps({name: base64.b64encode(value).decode('ascii') for name, value in files.items()}).encode()
            await self._cli('exec', '-i', self.container, '/usr/local/bin/python', '-I', '-c', UPLOAD, stdin=payload)
            self.attestation = {'container_id': identity, 'image_id': self.image_id, 'image_digest': image, 'probes': proof}
            return self.attestation
        except BaseException as error:
            await self.close()
            if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    async def run(self, command: str):
        if not isinstance(command, str) or not 1 <= len(command) <= 4096 or '\0' in command or self.attestation is None:
            raise CommerceFailure('INPUT_INVALID', 422)
        await self._inspection()
        try:
            return (await self._cli('exec', self.container, '/bin/sh', '-c', command)).decode('utf-8', errors='replace')
        except BaseException:
            await self.close()  # Killing only Docker's client can leave the remote process running.
            raise

    async def capture(self):
        if self.attestation is None:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        await self._inspection()
        return await self._cli('exec', self.container, '/usr/local/bin/python', '-I', '-c', CAPTURE,
                               *sorted(ALLOWED_FILES), limit=MAX_PACKAGE + 1024 * 1024)

    async def close(self):
        if self.container:
            try:
                await self._cli('rm', '--force', self.container, timeout=10)
            except (CommerceFailure, TimeoutError, OSError):
                pass  # Session is never reused; the fixed process lifetime is the crash backstop.
            finally:
                self.container, self.attestation = None, None
