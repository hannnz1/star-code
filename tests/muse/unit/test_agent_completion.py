import asyncio
from pathlib import Path

import pytest
from test_agent_loop import ScriptedProvider, runtime

from muse.contracts import ModelEvent, TaskRequest, ToolCall
from muse.main import create_app
from muse.memory.service import MemoryService
from muse.tools.context import ExecutionContext
from muse.tools.files import FileTools
from muse.tools.registry import ToolRegistry


async def test_pause_finishes_current_model_turn_and_resume_does_not_repeat(tmp_path):
    started, proceed = asyncio.Event(), asyncio.Event()
    class Provider:
        calls = 0
        async def stream(self, messages, tools):
            self.calls += 1
            started.set()
            await proceed.wait()
            yield ModelEvent(type="text", text="Finished")
            yield ModelEvent(type="done")
    provider = Provider()
    repo, task, worker = runtime(tmp_path, provider)
    running = asyncio.create_task(worker.run_once())
    await started.wait()
    repo.control(task.id, "pause", expected_revision=repo.get(task.id).revision)
    proceed.set()
    await running
    assert repo.get(task.id).status == "PAUSED"
    assert repo.get(task.id).checkpoint["final_text"] == "Finished"
    repo.control(task.id, "resume", expected_revision=repo.get(task.id).revision)
    await worker.run_once()
    assert repo.get(task.id).status == "SUCCEEDED"
    assert provider.calls == 1


async def test_default_workspace_is_accessible_and_state_is_not(tmp_path):
    provider = ScriptedProvider([])
    _, _, worker = runtime(tmp_path, provider)
    worker.settings = worker.settings.model_copy(update={"data_dir": tmp_path / "fresh-data"})
    app = create_app(worker.settings)
    repo = app.state.repository
    ws = repo.workspaces()[0]
    root = Path(ws["path"])
    (root / "example.txt").write_text("hello")
    task = repo.create(TaskRequest(prompt="Read", workspace_id=ws["id"], client_request_id="default"))
    task = repo.claim_next("reader")
    ctx = ExecutionContext(worker.settings, repo, task, "reader")
    files = FileTools(ctx)
    assert await files.read_file({"path": "example.txt"}, "r") == "hello"


async def test_memory_is_injected_and_deleted_memory_disappears(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type="text", text="done")]] * 2)
    repo, task, worker = runtime(tmp_path, provider)
    memory = MemoryService(repo, worker.settings)
    item = memory.upsert(scope="project", workspace_id=task.workspace_id, title="Language", content="Use Mandarin")
    await worker.run_once()
    assert "Use Mandarin" in provider.requests[0][0]["content"]
    memory.delete(item["id"])
    repo.create(TaskRequest(prompt="Again", workspace_id=task.workspace_id, client_request_id="again"))
    await worker.run_once()
    assert "Use Mandarin" not in provider.requests[1][0]["content"]


async def test_ask_user_waits_and_continues_without_repeating_question(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="question", name="ask_user", arguments={"question": "Which folder?"}))],
        [ModelEvent(type="text", text="Received")],
    ])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    assert repo.get(task.id).status == "WAITING_INPUT"
    assert repo.get(task.id).result == "Which folder?"
    repo.control(task.id, "input", expected_revision=repo.get(task.id).revision, content="reports")
    await worker.run_once()
    assert repo.get(task.id).status == "SUCCEEDED"
    assert provider.requests[-1][-1] == {"role": "user", "content": "reports"}


async def test_ask_user_progress_statement_does_not_pause_task(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="progress", name="ask_user", arguments={
            "question": "I have spawned both children and will continue once they finish."}))],
        [ModelEvent(type="text", text="Completed after checking the work")],
    ])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    assert repo.get(task.id).status == "SUCCEEDED"
    assert repo.calls(task.id) == []
    assert "direct question" in provider.requests[1][-1]["content"]


@pytest.mark.parametrize('question', [
    'Should I wait for the children to finish and then continue?',
    'Should I inspect the child worktrees directly and continue?',
    'The child commits are ready; I need approval to integrate and verify. Should I proceed?',
])
async def test_ask_user_cannot_pause_for_routine_delegation_progress(tmp_path, question):
    repo, _, worker = runtime(tmp_path, ScriptedProvider([]))
    parent = repo.claim_next('parent')
    repo.spawn_child(parent.id, 'parent', parent.lease_epoch, 'spawn', 'Inspect component')
    ctx = ExecutionContext(worker.settings, repo, parent, 'parent')
    result = await ToolRegistry(ctx).execute(ToolCall(id='question', name='ask_user', arguments={'question': question}))
    assert result.status == 'error'
    assert 'continue' in result.content.lower()
    assert not ctx.cp.get('input_question')


async def test_research_without_sources_and_artifact_is_not_success(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type="text", text="Made up research")]])
    repo, task, worker = runtime(tmp_path, provider)
    repo.control(task.id, "cancel", expected_revision=task.revision)
    task = repo.create(TaskRequest(prompt="Research", scenario="research", workspace_id=task.workspace_id, client_request_id="research"))
    await worker.run_once()
    assert repo.get(task.id).status == "FAILED"
async def test_followup_receives_parent_outcome_without_replaying_its_calls(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type="text", text="The answer was 42.")], [ModelEvent(type="text", text="More detail")]])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    child = repo.create(TaskRequest(prompt="Explain that result", workspace_id=task.workspace_id, parent_task_id=task.id, client_request_id="child"))
    await worker.run_once()
    assert "The answer was 42" in str(provider.requests[-1])
    assert repo.tool_attempts(child.id) == 0
