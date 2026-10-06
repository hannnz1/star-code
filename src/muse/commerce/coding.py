"""Trusted capture of hostile static code. This module does not prove OS isolation.

The source store lives outside every agent mount. No agent Git config, hooks,
revision, symlinks or archive extraction are used. Objects are ordinary Git
objects, so the frozen revision can be inspected with existing Git tools.
"""
import hashlib
import io
import os
import re
import tarfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from muse.commerce.models import SitePackage
from muse.commerce.repository import digest, encode
from muse.commerce.theme import (
    ALLOWED_FILES,
    MAX_FILE,
    MAX_PACKAGE,
    build_file_archive,
    validate_site_archive,
    validate_theme_files,
)


@dataclass(frozen=True)
class CodingArtifact:
    project_id: str
    plan_id: str
    snapshot_hash: str
    source_digest: str
    package: SitePackage
    archive: bytes


def _git_id(kind, payload):
    return hashlib.sha1(kind.encode('ascii') + b' ' + str(len(payload)).encode('ascii') + b'\0' + payload).hexdigest()


def _git_tree(paths, write):
    children = {}
    for name, content in paths.items():
        head, separator, tail = name.partition('/')
        if separator:
            children.setdefault(head, {})[tail] = content
        else:
            children[head] = content
    payload = b''
    for name, value in sorted(children.items(), key=lambda pair: pair[0] + ('/' if isinstance(pair[1], dict) else '')):
        directory = isinstance(value, dict)
        identity = _git_tree(value, write) if directory else write('blob', value)
        payload += ('40000' if directory else '100644').encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(identity)
    return write('tree', payload)


def _source_commit(files, *, project_id, plan_id, snapshot_hash, content_hash, write=_git_id):
    tree = _git_tree(files, write)
    source_digest = digest({name: hashlib.sha256(content).hexdigest() for name, content in files.items()})
    message = encode({'project_id': project_id, 'plan_id': plan_id, 'snapshot_hash': snapshot_hash,
                      'content_hash': content_hash, 'source_digest': source_digest})
    commit = write('commit', ('tree ' + tree + '\nauthor MUSE <source@muse.invalid> 0 +0000\n'
        'committer MUSE <source@muse.invalid> 0 +0000\n\n' + message + '\n').encode('utf-8'))
    return commit, source_digest


def verify_coding_artifact(artifact: CodingArtifact):
    """Check code/source/archive binding; this is not browser or OS verification."""
    if not isinstance(artifact, CodingArtifact):
        raise TypeError('Invalid captured code artifact')
    validate_site_archive(artifact.archive, artifact.package)
    with zipfile.ZipFile(io.BytesIO(artifact.archive)) as archive:
        files = {name: archive.read('muse-storefront/' + name) for name in ALLOWED_FILES}
    commit, source_digest = _source_commit(files, project_id=artifact.project_id, plan_id=artifact.plan_id,
        snapshot_hash=artifact.snapshot_hash, content_hash=artifact.package.content_sha256)
    if commit != artifact.package.code_revision or source_digest != artifact.source_digest:
        raise ValueError('Captured source binding differs')
    return artifact


def capture_static_tar(data: bytes) -> dict[str, bytes]:
    if not isinstance(data, bytes) or len(data) > MAX_PACKAGE + 1024 * 1024:
        raise ValueError('Code capture exceeds its limit')
    files = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
            for info in archive:
                if (info.name not in ALLOWED_FILES or info.name in files or not info.isfile()
                        or info.issparse() or not 0 <= info.size <= MAX_FILE):
                    raise ValueError('Unsupported code capture entry')
                stream = archive.extractfile(info)
                if stream is None:
                    raise ValueError('Code capture unavailable')
                content = stream.read(MAX_FILE + 1)
                if len(content) != info.size:
                    raise ValueError('Code capture is incomplete')
                files[info.name] = content
                if len(files) > len(ALLOWED_FILES):
                    raise ValueError('Unexpected code capture entries')
    except (tarfile.TarError, OSError, EOFError) as error:
        raise ValueError('Invalid code capture') from error
    validate_theme_files(files)
    return files


class SourceStore:
    def __init__(self, root: Path):
        self.root = Path(root).absolute()

    def _safe_directory(self, path):
        for component in (path, *path.parents):
            if component.is_symlink() or component.is_junction():
                raise ValueError('Source store cannot contain links')
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == 'posix':
            if path.stat().st_uid != os.getuid():
                raise ValueError('Source store has a different owner')
            path.chmod(0o700)

    def _object(self, kind, payload):
        raw = kind.encode('ascii') + b' ' + str(len(payload)).encode('ascii') + b'\0' + payload
        identity = hashlib.sha1(raw).hexdigest()
        directory = self.root / 'objects' / identity[:2]
        self._safe_directory(directory)
        path = directory / identity[2:]
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.is_symlink() or path.is_junction() or zlib.decompress(path.read_bytes()) != raw:
                raise ValueError('Source object conflict') from None
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(zlib.compress(raw))
                stream.flush()
                os.fsync(stream.fileno())
        return identity

    def seal(self, capture: bytes, *, project_id: str, plan_id: str, snapshot_hash: str, content_hash: str) -> CodingArtifact:
        for identity in (project_id, plan_id):
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', identity):
                raise ValueError('Invalid code identity')
        if any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in (snapshot_hash, content_hash)):
            raise ValueError('Invalid frozen code binding')
        files = capture_static_tar(capture)  # Validate all hostile input before creating trusted files.
        self._safe_directory(self.root)
        self._safe_directory(self.root / 'refs')
        # No Git commands run during sealing, and no agent-controlled config is copied.
        for name, content in {'HEAD': b'ref: refs/heads/captured\n',
                              'config': b'[core]\n\tbare = true\n\trepositoryformatversion = 0\n'}.items():
            path = self.root / name
            if path.is_symlink() or path.is_junction():
                raise ValueError('Source store cannot contain links')
            if not path.exists():
                with path.open('xb') as stream:
                    stream.write(content)
            elif path.read_bytes() != content:
                raise ValueError('Source store metadata differs')
        commit, source_digest = _source_commit(files, project_id=project_id, plan_id=plan_id, snapshot_hash=snapshot_hash,
                                               content_hash=content_hash, write=self._object)
        package, archive = build_file_archive(files, code_revision=commit, content_hash=content_hash)
        return CodingArtifact(project_id, plan_id, snapshot_hash, source_digest, package, archive)
