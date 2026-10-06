"""Captured code is hostile; revisions are made by the trusted host, never the agent."""
import io
import tarfile

import pytest

from muse.commerce.models import SiteBrief, StoreSnapshot
from muse.commerce.repository import digest
from muse.commerce.site import build_site_blueprint
from muse.commerce.theme import render_site_files, validate_site_archive


def blueprint():
    return build_site_blueprint(SiteBrief(brand_name='Shop', language='en-US', currency='USD'),
                                StoreSnapshot(project_id='project', environment='staging'))


def archive(files, *, extra=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as stream:
        for path, data in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(data)
            stream.addfile(info, io.BytesIO(data))
        if extra is not None:
            stream.addfile(extra)
    return output.getvalue()


def seal(tmp_path, data, **bindings):
    from muse.commerce.coding import SourceStore
    return SourceStore(tmp_path / 'trusted-source').seal(data, project_id='project', plan_id='plan',
        snapshot_hash='b' * 64, content_hash=digest({'blueprint': blueprint().model_dump(mode='json'), 'products': []}),
        **bindings)


def test_capture_seals_real_static_change_in_git_and_exact_deployable_archive(tmp_path):
    import subprocess
    files = render_site_files(blueprint(), [])
    files['assets/storefront.css'] += b'\n.merchant-banner { padding: 24px; }\n'
    artifact = seal(tmp_path, archive(files))
    assert validate_site_archive(artifact.archive, artifact.package) == artifact.package
    result = subprocess.run(['git', '--git-dir', str(tmp_path / 'trusted-source'), 'show',
                             artifact.package.code_revision + ':assets/storefront.css'],
                            capture_output=True, check=True)
    assert result.stdout == files['assets/storefront.css']
    assert artifact.package.code_revision != 'a' * 40
    assert seal(tmp_path, archive(files)) == artifact
    assert artifact.source_digest == digest({path: __import__('hashlib').sha256(data).hexdigest() for path, data in files.items()})


@pytest.mark.parametrize('path', ['../secret', '/etc/passwd', '.git/config', 'agent.php', 'assets/agent.js',
                                  'muse-storefront/templates/page.html'])
def test_capture_rejects_extra_or_outside_paths_before_creating_source(tmp_path, path):
    files = render_site_files(blueprint(), [])
    files[path] = b''
    with pytest.raises(ValueError):
        seal(tmp_path, archive(files))
    assert not (tmp_path / 'trusted-source').exists()


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_capture_rejects_links_and_nonregular_entries(tmp_path, kind):
    info = tarfile.TarInfo('assets/escape.css')
    info.type, info.linkname = kind, '/private/credentials'
    with pytest.raises(ValueError):
        seal(tmp_path, archive(render_site_files(blueprint(), []), extra=info))


def test_duplicate_php_change_and_agent_commit_are_not_accepted(tmp_path):
    files = render_site_files(blueprint(), [])
    duplicate = tarfile.TarInfo('functions.php')
    with pytest.raises(ValueError):
        seal(tmp_path, archive(files, extra=duplicate))
    files['functions.php'] += b'<?php system("id");'
    with pytest.raises(ValueError):
        seal(tmp_path, archive(files))


def test_same_code_different_frozen_business_input_cannot_share_source_commit(tmp_path):
    from muse.commerce.coding import SourceStore
    data = archive(render_site_files(blueprint(), []))
    first = seal(tmp_path, data)
    other = SourceStore(tmp_path / 'trusted-source').seal(data, project_id='project', plan_id='other-plan',
        snapshot_hash='b' * 64, content_hash='c' * 64)
    assert first.package.code_revision != other.package.code_revision
    with pytest.raises(ValueError):
        SourceStore(tmp_path / 'invalid').seal(data, project_id='../escape', plan_id='plan',
            snapshot_hash='b' * 64, content_hash='c' * 64)
