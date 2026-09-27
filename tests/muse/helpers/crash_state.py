import sys
import time
from pathlib import Path

from muse.tasks.repository import TaskRepository

repo=TaskRepository(Path(sys.argv[1]))
task=repo.claim_next("crash-child",ttl=60)
risk=sys.argv[3]
repo.checkpoint(task.id,"crash-child",task.lease_epoch,{"model_requests":3,"active_seconds":7,"pending_calls":[{"id":"fault","name":"read_file" if risk=="read" else "write_file","arguments":{"path":"x"}}]})
repo.prepare_call(task.id,"crash-child",task.lease_epoch,"confirmed","read_file",{"path":"confirmed"},"read")
repo.begin_call(task.id,"crash-child",task.lease_epoch,"confirmed")
repo.complete_call(task.id,"crash-child",task.lease_epoch,"confirmed",{"status":"success","content":"confirmed result"})
repo.prepare_call(task.id,"crash-child",task.lease_epoch,"fault","read_file" if risk=="read" else "write_file",{"path":"x"},risk)
repo.begin_call(task.id,"crash-child",task.lease_epoch,"fault")
if risk=="write": Path(sys.argv[2]+".counter").write_text("1")
Path(sys.argv[2]).write_text("ready")
time.sleep(120)
