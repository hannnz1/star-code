import asyncio
import importlib.util

from muse.config import load_settings
from muse.contracts import ModelEvent, TaskRequest, ToolCall
from muse.tasks.repository import TaskRepository


class ScriptedProvider:
    def __init__(self, turns):
        self.turns = iter(turns)
        self.requests = []

    async def stream(self, messages, tools):
        self.requests.append(messages)
        turn = next(self.turns)
        for event in turn:
            yield event
        yield ModelEvent(type="done")


def runtime(tmp_path, provider, **limits):
    assert importlib.util.find_spec("muse.agent") is not None, "Agent runner is missing"
    from muse.agent.loop import AgentRunner
    from muse.tasks.worker import Worker
    settings = load_settings(data_dir=tmp_path / "data", require_provider=False).model_copy(update=limits)
    repo = TaskRepository(settings.data_dir / "state.sqlite3")
    root = tmp_path / "project"
    root.mkdir()
    (root / "hello.txt").write_text("local content", encoding="utf-8")
    ws = repo.register_workspace(str(root))
    task = repo.create(TaskRequest(prompt="Read hello.txt", workspace_id=ws["id"], scenario="coding", client_request_id="task"))
    return repo, task, Worker(settings, repo, AgentRunner(provider), worker_id="test-worker")


async def test_agent_uses_real_file_tool_and_passes_result_back(tmp_path):
    scripted = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="read", name="read_file", arguments={"path": "hello.txt"}))],
        [ModelEvent(type="text", text="The file contains local content.")],
    ])
    repo, task, worker = runtime(tmp_path, scripted)
    assert await worker.run_once()
    assert repo.get(task.id).status == "SUCCEEDED"
    assert "local content" in scripted.requests[1][-1]["content"]
    assert len(repo.calls(task.id)) == 1


async def test_model_budget_stops_before_third_request(tmp_path):
    scripted = ScriptedProvider([[ModelEvent(type="call", call=ToolCall(id=f"r{i}", name="read_file", arguments={"path": "hello.txt"}))] for i in range(3)])
    repo, task, worker = runtime(tmp_path, scripted, max_turns=2)
    await worker.run_once()
    assert len(scripted.requests) == 2
    assert repo.get(task.id).status == "FAILED"
    assert repo.get(task.id).checkpoint["model_requests"] == 2


async def test_tool_budget_stops_before_second_dispatch(tmp_path):
    scripted = ScriptedProvider([[ModelEvent(type="call", call=ToolCall(id=f"r{i}", name="read_file", arguments={"path": "hello.txt"})) for i in range(2)]])
    repo, task, worker = runtime(tmp_path, scripted, max_tool_calls=1)
    await worker.run_once()
    assert repo.tool_attempts(task.id) == 1
    assert repo.get(task.id).status == "FAILED"


async def test_code_changes_without_verification_are_not_success(tmp_path):
    scripted = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="w", name="write_file", arguments={"path": "hello.txt", "content": "changed"}))],
        [ModelEvent(type="text", text="Everything passed!")],
    ])
    repo, task, worker = runtime(tmp_path, scripted, max_turns=2)
    await worker.run_once()
    assert repo.get(task.id).status == "FAILED"
    assert "verification" in repo.get(task.id).error.lower()


async def test_coding_agent_gets_one_repair_turn_after_unverified_final(tmp_path):
    scripted = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="w", name="write_file", arguments={"path": "hello.txt", "content": "changed"}))],
        [ModelEvent(type="text", text="Done")],
        [ModelEvent(type="call", call=ToolCall(id="v", name="verify_command", arguments={"command": "echo verified"}))],
        [ModelEvent(type="text", text="Verified after writing")],
    ])
    repo, task, worker = runtime(tmp_path, scripted)
    await worker.run_once()
    assert repo.get(task.id).status == "WAITING_APPROVAL"
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval["id"], True, approval["action_digest"])
    await worker.run_once()
    assert repo.get(task.id).status == "SUCCEEDED"
    assert len(scripted.requests) == 4
    assert "verify_command" in scripted.requests[2][-1]["content"]


async def test_approval_resume_uses_saved_call_not_a_second_model_decision(tmp_path):
    scripted = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="cmd", name="verify_command", arguments={"command": "echo verified"}))],
        [ModelEvent(type="text", text="Verified.")],
    ])
    repo, task, worker = runtime(tmp_path, scripted)
    await worker.run_once()
    assert repo.get(task.id).status == "WAITING_APPROVAL"
    assert len(scripted.requests) == 1
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval["id"], True, approval["action_digest"])
    await worker.run_once()
    assert repo.get(task.id).status == "SUCCEEDED"
    assert len(scripted.requests) == 2
    assert repo.tool_attempts(task.id) == 1


async def test_cancel_interrupts_a_waiting_model_and_preserves_task(tmp_path):
    started = asyncio.Event()
    class Slow:
        async def stream(self, messages, tools):
            started.set()
            await asyncio.sleep(100)
            yield ModelEvent(type="done")
    repo, task, worker = runtime(tmp_path, Slow())
    running = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), 2)
    latest = repo.get(task.id)
    repo.control(task.id, "cancel", expected_revision=latest.revision)
    await asyncio.wait_for(running, 3)
    assert repo.get(task.id).status == "CANCELLED"
    assert repo.get(task.id).checkpoint["model_requests"] == 1


def test_runtime_progress_prefers_successful_delegation_over_earlier_error():
    from types import SimpleNamespace

    from muse.agent.loop import runtime_progress

    calls = [
        {'name': 'spawn_worktree', 'status': 'FAILED', 'result': {'status': 'error',
            'content': 'Unknown role; private child prompt must not be copied'}},
        {'name': 'spawn_worktree', 'status': 'DONE', 'result': {'status': 'success',
            'metadata': {'child_id': 'child-1'}, 'content': 'private workspace path'}},
    ]
    repo = SimpleNamespace(children=lambda _: [SimpleNamespace(id='child-1', status='RUNNING')],
                           calls=lambda _: calls)
    progress = runtime_progress(SimpleNamespace(repo=repo, task_id='parent'))
    assert progress['children'] == [{'id': 'child-1', 'status': 'RUNNING'}]
    assert progress['successful_worktree_spawns'] == ['child-1']
    assert progress['recent_worktree_actions'][-1]['status'] == 'success'
    assert 'private child prompt' not in str(progress)
    assert 'private workspace path' not in str(progress)
