import importlib.util
import json

import pytest
from fastapi.testclient import TestClient
from muse.config import load_settings


@pytest.fixture
def api(tmp_path):
    assert importlib.util.find_spec("muse.main") is not None, "HTTP application is missing"
    from muse.main import create_app
    settings = load_settings(data_dir=tmp_path / "data", require_provider=False)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.headers["Authorization"] = f"Bearer {settings.access_token.get_secret_value()}"
        yield client, app


def test_health_requires_no_provider_and_config_export_has_no_token(api):
    client, app = api
    assert client.get("/health").json()["status"] == "ok"
    public = client.get("/api/settings")
    assert public.status_code == 200
    assert app.state.settings.access_token.get_secret_value() not in public.text


def test_no_token_invalid_origin_and_host_are_rejected(api):
    client, app = api
    assert client.get("/api/tasks", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.post("/api/tasks", headers={"Origin": "https://evil.example"}, json={}).status_code == 403
    assert client.get("/api/tasks", headers={"Host": "evil.example"}).status_code == 400


def test_create_dedupe_conflict_cancel_and_event_replay(api):
    client, app = api
    ws = client.get("/api/workspaces").json()[0]
    body = {"prompt": "Read the project", "workspace_id": ws["id"], "client_request_id": "same", "scenario": "coding"}
    first = client.post("/api/tasks", json=body)
    assert first.status_code == 201
    task = first.json()
    assert client.post("/api/tasks", json=body).json()["id"] == task["id"]
    assert client.post("/api/tasks", json={**body, "prompt": "changed"}).status_code == 409
    paused = client.post(f'/api/tasks/{task["id"]}/pause', json={"expected_revision": task["revision"]})
    assert paused.json()["status"] == "PAUSED"
    assert client.post(f'/api/tasks/{task["id"]}/resume', json={"expected_revision": task["revision"]}).status_code == 409
    cancelled = client.post(f'/api/tasks/{task["id"]}/cancel', json={"expected_revision": paused.json()["revision"]})
    assert cancelled.json()["status"] == "CANCELLED"
    events = client.get(f'/api/tasks/{task["id"]}/events?after=1&follow=false')
    assert "id: 2" in events.text and "id: 1\n" not in events.text


def test_memory_crud_and_missing_artifact(api):
    client, app = api
    created = client.post("/api/memories", json={"title": "Language", "content": "Prefer Chinese", "scope": "user"})
    assert created.status_code == 201
    identifier = created.json()["id"]
    assert client.patch(f"/api/memories/{identifier}", json={"content": "Prefer concise Chinese"}).status_code == 200
    assert client.delete(f"/api/memories/{identifier}").status_code == 204
    assert client.get("/api/memories").json() == []
    assert client.get("/api/artifacts/not-known").status_code == 404


def test_blank_prompt_does_not_create_task(api):
    client, app = api
    workspace = client.get("/api/workspaces").json()[0]
    result = client.post("/api/tasks", json={"prompt": "   ", "workspace_id": workspace["id"], "client_request_id": "blank"})
    assert result.status_code == 422
def test_invalid_memory_update_and_unknown_workspace_are_client_errors(api):
    client, app = api
    created = client.post("/api/memories", json={"title": "Language", "content": "Chinese", "scope": "user"}).json()
    assert client.patch('/api/memories/' + created['id'], json={"content": None}).status_code == 422
    assert client.post('/api/workspaces', json={"path": str(app.state.settings.data_dir / 'missing')}).status_code == 409
