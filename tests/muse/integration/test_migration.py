import json

import pytest

from muse.config import load_settings
from muse.memory.service import MemoryService
from muse.tasks.repository import TaskRepository


def test_preview_memory_rejects_secret_and_apply_requires_unchanged_digest(tmp_path):
    from muse.memory.importer import MigrationImporter
    settings = load_settings(data_dir=tmp_path / "state", require_provider=False)
    repo = TaskRepository(settings.data_dir / "state.sqlite3")
    service = MemoryService(repo, settings)
    legacy = tmp_path / "legacy"; legacy.mkdir()
    note = legacy / "user_preference_language.md"
    note.write_text('---\ntype: user_preference\ntitle: "Language"\n---\nPrefer Chinese.\n')
    bad = legacy / "project_knowledge_secret.md"
    bad.write_text('---\ntitle: Unsafe\n---\napi_key=not-a-real-secret-123456')
    importer = MigrationImporter(service)
    preview = importer.preview_memory(legacy)
    assert len(preview["accepted"]) == 1
    assert len(preview["rejected"]) == 1
    assert "not-a-real-secret" not in json.dumps(preview)
    assert service.list() == []
    note.write_text('---\ntitle: Changed\n---\nPrefer French.')
    with pytest.raises(ValueError, match="changed"):
        importer.import_memory(legacy, preview["digest"], scope="user")
    latest = importer.preview_memory(legacy)
    importer.import_memory(legacy, latest["digest"], scope="user")
    importer.import_memory(legacy, latest["digest"], scope="user")
    assert len(service.list()) == 1


def test_history_preview_contains_only_readonly_text_not_protocol_or_authorization(tmp_path):
    from muse.memory.importer import preview_history
    path = tmp_path / "history.jsonl"
    path.write_text('\n'.join(json.dumps(item) for item in [
        {"role":"user","content":"Hello","tool_calls":[{"command":"dangerous"}]},
        {"role":"assistant","content":"api_key=fake-sensitive-string-12345", "protocol_state":{"authorization":"allow-all"}},
    ]))
    preview = preview_history(path)
    assert "dangerous" not in preview["markdown"]
    assert "allow-all" not in preview["markdown"]
    assert "fake-sensitive" not in preview["markdown"]
    assert preview["resumable"] is False

