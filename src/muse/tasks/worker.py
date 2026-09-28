import asyncio
import uuid

from muse.tools.context import ApprovalRequired, ExecutionContext, TaskControl


class Worker:
    def __init__(self, settings, repository, runner, *, worker_id=None):
        self.settings, self.repo, self.runner = settings, repository, runner
        from muse.agent.instructions import resource_snapshot
        repository.snapshot_factory = lambda request, workspace: resource_snapshot(settings, request, workspace)
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"

    async def run_once(self) -> bool:
        self.repo.recover_expired_tasks()
        self.repo.wake_completed_parents()
        task = self.repo.claim_next(self.worker_id, ttl=self.settings.lease_seconds)
        if task is None:
            from muse.memory.maintenance import MemoryMaintenance
            maintenance = MemoryMaintenance(self.repo, self.settings)
            if self.settings.memory_auto_extract or self.settings.memory_auto_consolidate:
                return await maintenance.run_once(getattr(self.runner, 'provider', None))
            return False
        context = ExecutionContext(self.settings, self.repo, task, self.worker_id, enforce_budgets=True)
        stop = asyncio.Event()

        async def heartbeat():
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.settings.heartbeat_seconds)
                except TimeoutError:
                    try:
                        self.repo.heartbeat(task.id, self.worker_id, task.lease_epoch, ttl=self.settings.lease_seconds)
                        context.save()
                    except ValueError:
                        break

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            result = await self.runner.run(task, context)
            context.save()
            self.repo.finish(task.id, self.worker_id, task.lease_epoch, result.status, result.text)
            if result.status == 'SUCCEEDED':
                from muse.memory.maintenance import MemoryMaintenance
                maintenance = MemoryMaintenance(self.repo, self.settings)
                maintenance.enqueue(task.id)
                for snapshot in context.cp.get('memory_snapshots', []):
                    maintenance.enqueue(task.id, snapshot)
                maintenance.enqueue_consolidation(task.workspace_id)
        except ApprovalRequired:
            pass  # Approval transition and checkpoint were committed atomically before yielding.
        except TaskControl as control:
            current = self.repo.get(task.id)
            if current.status == "RUNNING" and current.lease_owner == self.worker_id:
                try:
                    context.save()
                    self.repo.finish(task.id, self.worker_id, task.lease_epoch, control.status,
                                     context.cp.get("final_text", ""), context.safe(str(control)))
                except ValueError:
                    pass  # An expired owner must never overwrite a newer lease.
        except asyncio.CancelledError:
            self.repo.abandon(task.id, self.worker_id, task.lease_epoch)
            raise
        except Exception as error:  # noqa: BLE001 -- worker boundary records unexpected failures instead of losing the task.
            current = self.repo.get(task.id)
            if current.status == "RUNNING" and current.lease_owner == self.worker_id:
                try:
                    context.save()
                    uncertain = any(call['status'] == 'EXECUTING' and call['risk'] != 'read'
                                    for call in self.repo.calls(task.id))
                    if uncertain:
                        self.repo.add_event(task.id, 'worker_error', {'message': context.safe(str(error))[:2000]})
                        self.repo.abandon(task.id, self.worker_id, task.lease_epoch)
                    else:
                        self.repo.finish(task.id, self.worker_id, task.lease_epoch, "FAILED", error=context.safe(str(error))[:2000])
                except ValueError:
                    pass
        finally:
            stop.set()
            await heartbeat_task
        return True

    async def run_forever(self):
        while True:
            if not await self.run_once():
                await asyncio.sleep(0.5)
