import importlib.util


def test_distribution_contains_durable_muse_runtime():
    assert importlib.util.find_spec('muse') is not None
    from muse.config import load_settings
    from muse.tasks.worker import Worker
    from muse.main import create_app
    assert callable(load_settings) and callable(create_app) and Worker


def test_installed_distribution_serves_packaged_frontend(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import muse.main
    from muse.config import load_settings
    package = tmp_path / 'site-packages/muse'
    assets = package / '_web/assets'
    assets.mkdir(parents=True)
    (package / '_web/index.html').write_text('<html>MUSE wheel fixture</html>')
    (assets / 'app.js').write_text('console.log("fixture")')
    monkeypatch.setattr(muse.main, '__file__', str(package / 'main.py'))
    settings = load_settings(data_dir=tmp_path / 'data', require_provider=False)
    with TestClient(muse.main.create_app(settings), base_url='http://127.0.0.1') as client:
        assert 'MUSE wheel fixture' in client.get('/').text
        assert client.get('/assets/app.js').status_code == 200
