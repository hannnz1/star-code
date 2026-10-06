import json
import sys
from types import SimpleNamespace

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector import __main__ as launcher
from muse.commerce_connector.runtime import create_reference_service
from tests.muse.commerce.test_reference_environment import archive, manifest


def test_reference_runtime_never_starts_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr('muse.commerce_connector.runtime.platform.system', lambda: 'Windows')
    with pytest.raises(CommerceFailure):
        create_reference_service(runtime_database=tmp_path / 'missing.sqlite', private_directory=tmp_path,
            versions_lock=manifest(archive()), woocommerce_archive=tmp_path / 'missing.zip', ports=(63800,))


def test_launcher_explicit_reference_settings_and_close_without_real_daemon(tmp_path, monkeypatch):
    lock = tmp_path / 'versions.json'
    lock.write_text(json.dumps(manifest(archive())), encoding='utf-8')
    calls, closed, served = [], [], []
    service = SimpleNamespace(jobs=SimpleNamespace(db=SimpleNamespace(engine=SimpleNamespace(dispose=lambda: closed.append(True)))))
    monkeypatch.setattr(launcher, 'load_connector_config', lambda path: ({}, 'unit-reference-token'))
    def factory(**kwargs):
        calls.append(kwargs)
        return service
    monkeypatch.setattr('muse.commerce_connector.runtime.create_reference_service', factory)
    monkeypatch.setattr(launcher, 'create_connector_app', lambda connections, **kwargs: served.append(kwargs) or object())
    monkeypatch.setattr(launcher.uvicorn, 'run', lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, 'argv', ['connector', '--config', str(tmp_path / 'private.json'),
        '--enable-reference-environments', '--runtime-database', str(tmp_path / 'runtime.sqlite'),
        '--versions-lock', str(lock), '--reference-private-directory', str(tmp_path),
        '--woocommerce-archive', str(tmp_path / 'woo.zip')])
    launcher.main()
    assert calls[0]['ports'] == (63800, 63801, 63802, 63803)
    assert served[0]['reference'] is service and closed == [True]


def test_launcher_missing_reference_files_refuses_before_service_factory(tmp_path, monkeypatch):
    lock = tmp_path / 'versions.json'
    lock.write_text(json.dumps(manifest(archive())), encoding='utf-8')
    monkeypatch.setattr(launcher, 'load_connector_config', lambda path: ({}, 'unit-reference-token'))
    calls = []
    monkeypatch.setattr('muse.commerce_connector.runtime.create_reference_service', lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, 'argv', ['connector', '--config', str(tmp_path / 'private.json'),
        '--enable-reference-environments', '--runtime-database', str(tmp_path / 'runtime.sqlite'), '--versions-lock', str(lock)])
    with pytest.raises(SystemExit) as error: launcher.main()
    assert error.value.code == 2 and not calls
