import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_task_lifecycle import create, make_repo


@pytest.mark.parametrize("iteration", range(10))
@pytest.mark.parametrize("risk", ["read", "write"])
def test_real_process_kill_preserves_checkpoint_and_fences_unknown_writes(tmp_path, risk, iteration):
    repo, ws = make_repo(tmp_path)
    task = create(repo, ws)
    barrier = tmp_path / "barrier"
    helper = Path(__file__).resolve().parents[1] / "helpers" / "crash_state.py"
    process = subprocess.Popen([sys.executable,str(helper),str(tmp_path / "state.sqlite3"),str(barrier),risk], stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    try:
        deadline=time.monotonic()+10
        while not barrier.exists() and process.poll() is None and time.monotonic()<deadline: time.sleep(.02)
        assert barrier.exists()
        process.kill();process.wait(5)
        before = repo.get(task.id)
        repo.recover_expired_tasks(now=time.time()+100)
        saved=repo.get(task.id)
        assert saved.checkpoint["model_requests"]==3
        # Recovery conservatively charges the uncheckpointed interval, capped
        # at lease expiry; a crash must not refund the shared active budget.
        assert saved.checkpoint["active_seconds"] == pytest.approx(7 + max(0, before.lease_until - before.updated_at))
        repo.recover_expired_tasks(now=time.time()+200)
        assert repo.get(task.id).checkpoint['active_seconds'] == saved.checkpoint['active_seconds']
        assert repo.calls(task.id)[0]["result"]["content"]=="confirmed result"
        sequences=[event["sequence"] for event in repo.events(task.id)]
        assert sequences==list(range(1,len(sequences)+1))
        assert saved.status==("QUEUED" if risk=="read" else "INTERRUPTED")
        if risk=="write":
            assert Path(str(barrier)+".counter").read_text()=="1"
            assert repo.claim_next("replacement") is None
    finally:
        if process.poll() is None: process.kill();process.wait(5)
        process.stderr.close()
