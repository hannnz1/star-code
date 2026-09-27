from importlib.metadata import version

from fastapi.testclient import TestClient

from muse.config import load_settings
from muse.main import create_app


def test_health_distinguishes_api_contract_from_installed_release(tmp_path):
    settings = load_settings(data_dir=tmp_path, require_provider=False)
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8765') as client:
        response = client.get('/health')
        assert response.status_code == 200
        result = response.json()
    assert result['release_version'] == version('muse-personal-agent')
    assert result['version'] == '0.1.0'
