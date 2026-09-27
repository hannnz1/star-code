import importlib.util
from io import BytesIO

import pytest
from reportlab.pdfgen import canvas

from test_workspace_tools import context
from muse.contracts import ToolCall


async def test_save_artifact_is_versioned_and_download_is_hash_checked(tmp_path):
    repo, ctx, tools = context(tmp_path)
    assert importlib.util.find_spec("muse.artifacts") is not None, "Artifact service missing"
    from muse.artifacts.service import ArtifactService
    service = ArtifactService(ctx)
    first = service.save("report.md", b"# first", "text/markdown")
    second = service.save("report.md", b"# second", "text/markdown")
    assert first["version"] == 1 and second["version"] == 2
    assert service.read(first["id"])[1] == b"# first"
    with pytest.raises(ValueError):
        service.save("../escape.md", b"no", "text/markdown")
    from pathlib import Path
    Path(first["storage_path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        service.read(first["id"])


async def test_text_pdf_extraction_and_scanned_pdf_are_distinguished(tmp_path):
    repo, ctx, tools = context(tmp_path)
    normal = BytesIO()
    writer = canvas.Canvas(normal)
    writer.drawString(30, 700, "Project Atlas budget 1200")
    writer.save()
    (ctx.workspace / "normal.pdf").write_bytes(normal.getvalue())
    empty = BytesIO()
    writer = canvas.Canvas(empty)
    writer.showPage()
    writer.save()
    (ctx.workspace / "scan.pdf").write_bytes(empty.getvalue())
    found = await tools.execute(ToolCall(id="pdf", name="read_document", arguments={"path": "normal.pdf"}))
    missing = await tools.execute(ToolCall(id="scan", name="read_document", arguments={"path": "scan.pdf"}))
    assert found.status == "success" and "budget 1200" in found.content
    assert missing.status == "error" and "OCR" in missing.content


async def test_organize_copies_preserve_sources_and_same_names(tmp_path):
    repo, ctx, tools = context(tmp_path)
    for folder, content in [("甲 文件", "one"), ("乙 文件", "two")]:
        (ctx.workspace / folder).mkdir()
        (ctx.workspace / folder / "资料.txt").write_text(content, encoding="utf-8")
    first = await tools.execute(ToolCall(id="o1", name="organize_document", arguments={"path": "甲 文件/资料.txt", "category": "学习"}))
    second = await tools.execute(ToolCall(id="o2", name="organize_document", arguments={"path": "乙 文件/资料.txt", "category": "学习"}))
    assert first.status == second.status == "success"
    assert (ctx.workspace / "甲 文件/资料.txt").read_text(encoding="utf-8") == "one"
    assert (ctx.workspace / "乙 文件/资料.txt").read_text(encoding="utf-8") == "two"
    copies = list((ctx.workspace / "muse-output/学习").rglob("*.txt"))
    assert sorted(p.read_text(encoding="utf-8") for p in copies) == ["one", "two"]


def test_memory_scope_delete_and_secret_rejection(tmp_path):
    repo, ctx, tools = context(tmp_path)
    assert importlib.util.find_spec("muse.memory") is not None, "Memory service missing"
    from muse.memory.service import MemoryService
    memory = MemoryService(repo, ctx.settings)
    other = tmp_path / "other"
    other.mkdir()
    ws_other = repo.register_workspace(str(other))["id"]
    global_note = memory.upsert(scope="user", content="Use Chinese", title="Language")
    local_note = memory.upsert(scope="project", workspace_id=ctx.task.workspace_id, content="Project uses pytest", title="Testing")
    memory.upsert(scope="project", workspace_id=ws_other, content="Unrelated project uses Maven", title="Other")
    selected = memory.for_task(ctx.task.workspace_id)
    assert {m["id"] for m in selected} == {global_note["id"], local_note["id"]}
    memory.delete(local_note["id"])
    assert "pytest" not in str(memory.for_task(ctx.task.workspace_id))
    with pytest.raises(ValueError, match="secret"):
        memory.upsert(scope="user", content="api_key: sk-fixture-secret-value", title="Forbidden")
