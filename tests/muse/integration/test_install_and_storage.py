import sqlite3
from pathlib import Path

import pytest

from muse.artifacts.service import ArtifactService
from muse.config import load_settings
from muse.main import create_app
from muse.tasks.repository import TaskRepository
from test_workspace_tools import context


@pytest.mark.parametrize("iteration", range(10))
def test_state_event_transaction_rolls_back_together(tmp_path, monkeypatch, iteration):
    repo, ctx, _ = context(tmp_path)
    previous = repo.get(ctx.task_id)
    def fail(*args, **kwargs): raise OSError("Injected storage failure")
    monkeypatch.setattr(TaskRepository, "_event", fail)
    with pytest.raises(OSError):
        repo.control(ctx.task_id, "cancel", expected_revision=previous.revision)
    assert repo.get(ctx.task_id).status == previous.status
    assert repo.get(ctx.task_id).cancel_requested is False
    assert repo.get(ctx.task_id).revision == previous.revision


def test_artifact_disk_failure_has_no_record_or_completion_event(tmp_path, monkeypatch):
    repo, ctx, _ = context(tmp_path)
    service = ArtifactService(ctx)
    before = repo.events(ctx.task_id)
    def fail(*args, **kwargs): raise OSError("Injected disk full")
    monkeypatch.setattr(Path, "write_bytes", fail)
    with pytest.raises(OSError, match="disk full"):
        service.save("report.md", b"content")
    assert service.list() == []
    assert repo.events(ctx.task_id) == before


def test_database_rejects_future_schema_without_modifying_it(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE schema_version(version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version VALUES(999)")
    with pytest.raises(ValueError, match="Unsupported"):
        TaskRepository(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchall() == [(999,)]


async def test_missing_browser_returns_actionable_failure(tmp_path, monkeypatch):
    from muse.contracts import ToolCall
    from muse.tools.registry import ToolRegistry
    repo,ctx,_=context(tmp_path)
    ctx.settings.browser_allowed_origins=['http://127.0.0.1:9']
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH',str(tmp_path/'missing-browser-install'))
    result=await ToolRegistry(ctx).execute(ToolCall(id='missing-browser',name='read_url',arguments={'url':'http://127.0.0.1:9/'}))
    assert result.status=='error'
    assert 'playwright install' in result.content
    assert not repo.db.rows('SELECT id FROM sources')
