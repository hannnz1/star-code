import asyncio
import json
import time

import psutil

from muse.contracts import ModelEvent, ToolCall
from test_agent_loop import ScriptedProvider, runtime


async def test_cancel_stops_parent_child_and_records_cancelled_call(tmp_path):
    provider = ScriptedProvider([[ModelEvent(type="call", call=ToolCall(id="run", name="run_command", arguments={"command": "python parent.py"}))]])
    repo, task, worker = runtime(tmp_path, provider)
    root = tmp_path / "project"
    (root / "parent.py").write_text("import subprocess,sys,time,pathlib,os\np=subprocess.Popen([sys.executable,'child.py'])\npathlib.Path('pids.json').write_text(__import__('json').dumps([os.getpid(),p.pid]))\ntime.sleep(120)\n")
    (root / "child.py").write_text("import time,pathlib\np=pathlib.Path('ticks.txt')\nwhile True:\n with p.open('a') as f: f.write('tick\\n')\n time.sleep(.1)\n")
    await worker.run_once()
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval["id"], True, approval["action_digest"])
    running = asyncio.create_task(worker.run_once())
    try:
        for _ in range(100):
            if (root / "ticks.txt").exists():
                break
            await asyncio.sleep(.1)
        assert (root / "ticks.txt").exists()
        pids = json.loads((root / "pids.json").read_text())
        started = time.monotonic()
        repo.control(task.id, "cancel", expected_revision=repo.get(task.id).revision)
        await asyncio.wait_for(running, 10)
        assert time.monotonic() - started < 10
        assert all(not psutil.pid_exists(pid) for pid in pids)
        size = (root / "ticks.txt").stat().st_size
        await asyncio.sleep(2)
        assert (root / "ticks.txt").stat().st_size == size
        assert repo.get(task.id).status == "CANCELLED"
        assert repo.calls(task.id)[0]["result"]["status"] == "cancelled"
    finally:
        if not running.done():
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)


async def test_failed_verification_has_downloadable_log(tmp_path):
    provider = ScriptedProvider([
        [ModelEvent(type="call", call=ToolCall(id="verify", name="verify_command", arguments={"command": "Write-Output 'failure evidence'; exit 1"}))],
        [ModelEvent(type="text", text="Unable to fix the failure.")],
    ])
    repo, task, worker = runtime(tmp_path, provider)
    await worker.run_once()
    approval = repo.approvals(task.id)[0]
    repo.decide_approval(approval["id"], True, approval["action_digest"])
    await worker.run_once()
    assert repo.get(task.id).status == "FAILED"
    result = repo.calls(task.id)[0]["result"]
    assert result["metadata"]["exit_code"] == 1
    assert result["artifact_ids"]
