"""Offline package integrity; does not stand in for WordPress rendering."""
import hashlib
import io
import json
import stat
import zipfile

import pytest

from muse.commerce.models import SiteBrief, StoreSnapshot
from muse.commerce.site import build_site_blueprint


def blueprint():
    return build_site_blueprint(SiteBrief(brand_name='My Shop', language='zh-CN', currency='USD'),
                                StoreSnapshot(project_id='p', environment='staging'))


def package():
    from muse.commerce.theme import build_site_archive
    return build_site_archive(blueprint(), [], code_revision='a' * 40)


def test_native_theme_manifest_is_complete_and_archive_deterministic():
    metadata, data = package()
    assert (metadata, data) == package()
    assert metadata.code_revision == 'a' * 40
    assert metadata.package_sha256 == hashlib.sha256(data).hexdigest()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        assert 'muse-storefront/templates/index.html' in names
        assert 'muse-storefront/templates/archive-product.html' in names
        assert 'muse-storefront/templates/single-product.html' in names
        assert all('..' not in name and name.startswith('muse-storefront/') for name in names)
        assert len(names) == len(metadata.files_manifest)
        for entry in metadata.files_manifest:
            content = archive.read('muse-storefront/' + entry['path'])
            assert len(content) == entry['bytes']
            assert hashlib.sha256(content).hexdigest() == entry['sha256']
        assert b'woocommerce/cart' in archive.read('muse-storefront/templates/page-cart.html')
        assert b'woocommerce/checkout' in archive.read('muse-storefront/templates/page-checkout.html')
        assert b'woocommerce/product-price' in archive.read('muse-storefront/templates/single-product.html')
        assert b'wp:post-title' in archive.read('muse-storefront/templates/single-product.html')
        assert b'wp:post-title' in archive.read('muse-storefront/templates/archive-product.html')
        assert b'woocommerce/add-to-cart-form' in archive.read('muse-storefront/templates/single-product.html')
        assert b'"inherit":false' in archive.read('muse-storefront/templates/front-page.html')
        assert json.loads(archive.read('muse-storefront/theme.json'))['version'] == 3
    from muse.commerce.theme import validate_site_archive
    assert validate_site_archive(data, metadata) == metadata


def test_markup_inputs_are_escaped_and_theme_palette_is_validated():
    from muse.commerce.theme import build_site_archive
    value = blueprint()
    value.pages[0].title = '<script>alert(1)</script>-->'
    value.navigation[0].label = '<img src=x onerror=alert(1)>-->'
    _, data = build_site_archive(value, [], code_revision='a' * 40)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert b'<script>' not in archive.read('muse-storefront/templates/front-page.html')
        assert b'<img' not in archive.read('muse-storefront/parts/header.html')
        assert b'&lt;script&gt;' in archive.read('muse-storefront/templates/front-page.html')
    value.design_tokens['accent'] = 'red; background:url(https://evil.test)'
    with pytest.raises(ValueError):
        build_site_archive(value, [], code_revision='a' * 40)


def test_bad_navigation_and_missing_commit_revision_fail_before_packaging():
    from muse.commerce.theme import build_site_archive
    value = blueprint()
    value.navigation[0].slug = 'missing'
    with pytest.raises(ValueError):
        build_site_archive(value, [], code_revision='a' * 40)
    with pytest.raises(ValueError):
        build_site_archive(blueprint(), [], code_revision='unknown')


def repack(transform):
    metadata, data = package()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, 'w') as target:
        for info in source.infolist():
            target.writestr(info, source.read(info.filename))
        transform(target)
    return metadata, output.getvalue()


@pytest.mark.parametrize('name', ['../escape.html', '/absolute.html', 'muse-storefront/../escape.html',
                                 'muse-storefront/assets/agent.js', 'muse-storefront/agent.php',
                                 'muse-storefront/templates/INDEX.html', 'muse-storefront/templates\\escape.html'])
def test_zip_path_or_executable_additions_are_rejected(name):
    from muse.commerce.theme import validate_site_archive
    metadata, data = repack(lambda archive: archive.writestr(name, 'unexpected'))
    # Updating the overall digest cannot turn a forbidden path into a valid package.
    metadata = metadata.model_copy(update={'package_sha256': hashlib.sha256(data).hexdigest()})
    with pytest.raises(ValueError):
        validate_site_archive(data, metadata)


def test_duplicate_paths_and_symlinks_are_rejected():
    from muse.commerce.theme import validate_site_archive
    with pytest.warns(UserWarning, match='Duplicate name'):
        metadata, data = repack(lambda archive: archive.writestr('muse-storefront/functions.php', 'changed'))
    with pytest.raises(ValueError):
        validate_site_archive(data, metadata)
    info = zipfile.ZipInfo('muse-storefront/assets/link.css')
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    metadata, data = repack(lambda archive: archive.writestr(info, '../../secret'))
    with pytest.raises(ValueError):
        validate_site_archive(data, metadata)


def test_immutable_php_and_manifest_tampering_are_rejected_even_with_new_zip_hash():
    from muse.commerce.theme import validate_site_archive
    metadata, data = package()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, 'w') as target:
        for info in source.infolist():
            content = b'<?php system($_GET["cmd"]);' if info.filename.endswith('functions.php') else source.read(info.filename)
            target.writestr(info, content)
    data = output.getvalue()
    metadata = metadata.model_copy(update={'package_sha256': hashlib.sha256(data).hexdigest()})
    with pytest.raises(ValueError):
        validate_site_archive(data, metadata)
    metadata, data = package()
    metadata.files_manifest[0]['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        validate_site_archive(data, metadata)


def test_edit_changes_content_hash_and_cannot_reuse_old_package_metadata():
    from muse.commerce.theme import build_site_archive, validate_site_archive
    metadata, _ = package()
    value = blueprint()
    value.pages[0].title = 'New title'
    changed, data = build_site_archive(value, [], code_revision='b' * 40)
    assert changed.content_sha256 != metadata.content_sha256
    assert changed.package_sha256 != metadata.package_sha256
    assert changed.immutable_code_sha256 == metadata.immutable_code_sha256
    with pytest.raises(ValueError):
        validate_site_archive(data, metadata)


@pytest.mark.parametrize('path,value', [
    ('templates/front-page.html', b'<!-- wp:html --><script>alert(1)</script><!-- /wp:html -->'),
    ('templates/page.html', b'<p onclick="alert(1)">Text</p>'),
    ('templates/page.html', b'<a href="https://evil.test/">Text</a>'),
    ('assets/storefront.css', b'body { background:url(https://evil.test/); }'),
    ('assets/storefront.css', b'@import "https://evil.test/";'),
    ('assets/storefront.css', b'body { background:u\\72l(https://evil.test/); }'),
    ('theme.json', b'{"version":3,"styles":{"css":"@import https://evil.test;"}}'),
])
def test_active_or_external_content_is_rejected_before_archive(path, value):
    from muse.commerce.theme import render_site_files, validate_theme_files
    files = render_site_files(blueprint(), [])
    files[path] = value
    with pytest.raises(ValueError):
        validate_theme_files(files)
