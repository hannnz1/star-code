import json
import pytest


def test_snapshot_copies_runtime_and_web_without_private_state(tmp_path):
    from scripts.commerce.snapshot_linux_runtime import snapshot_runtime
    source=tmp_path/'source'
    for directory in ('src','scripts','wordpress','frontend/dist'):
        (source/directory).mkdir(parents=True)
    (source/'src/app.py').write_text('print("runtime")')
    (source/'src/agent.md').write_text('public role prompt')
    (source/'src/.env').write_text('PRIVATE=value')
    (source/'src/__pycache__').mkdir()
    (source/'src/__pycache__/app.pyc').write_bytes(b'cache')
    (source/'frontend/dist/index.html').write_text('<html>public</html>')
    (source/'config.yaml').write_text('secret configuration')
    (source/'pyproject.toml').write_text('[project]\nname="test"')
    destination=tmp_path/'runtime'
    manifest=snapshot_runtime(source,destination)
    assert (destination/'src/app.py').read_text()=='print("runtime")'
    assert (destination/'src/agent.md').read_text()=='public role prompt'
    assert (destination/'frontend/dist/index.html').is_file()
    assert not (destination/'src/.env').exists()
    assert not (destination/'src/__pycache__').exists()
    assert not (destination/'config.yaml').exists()
    assert manifest['files']['src/app.py']['sha256']
    assert json.loads((destination/'runtime-manifest.json').read_text())==manifest
    with pytest.raises(FileExistsError):
        snapshot_runtime(source,destination)


def test_snapshot_rejects_linked_runtime_source(tmp_path):
    from scripts.commerce.snapshot_linux_runtime import snapshot_runtime
    source=tmp_path/'source';source.mkdir()
    (source/'src').mkdir()
    outside=tmp_path/'external.py';outside.write_text('external')
    try:
        (source/'src/link.py').symlink_to(outside)
    except OSError:
        pytest.skip('Host cannot create symbolic links')
    with pytest.raises(ValueError,match='link'):
        snapshot_runtime(source,tmp_path/'runtime')


def test_runtime_destination_rejects_parent_escape(tmp_path):
    from scripts.commerce.snapshot_linux_runtime import validate_native_destination
    boundary=tmp_path/'acceptance';boundary.mkdir()
    with pytest.raises(ValueError):
        validate_native_destination(boundary/'..'/'outside',boundary)
    assert validate_native_destination(boundary/'fresh',boundary)==boundary/'fresh'


def test_runtime_destination_rejects_parent_link(tmp_path):
    from scripts.commerce.snapshot_linux_runtime import validate_native_destination
    boundary=tmp_path/'acceptance';boundary.mkdir()
    outside=tmp_path/'outside';outside.mkdir()
    try:
        (boundary/'link').symlink_to(outside,target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create symbolic links')
    with pytest.raises(ValueError):
        validate_native_destination(boundary/'link'/'fresh',boundary)
