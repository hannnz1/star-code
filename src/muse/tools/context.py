import asyncio
import time

from muse.config import Settings
from muse.contracts import TaskRecord
from muse.permissions.secrets import redact, stream_prefix
from muse.tasks.repository import TaskRepository


class TaskControl(RuntimeError):
    def __init__(self, status: str, message: str = ""):
        self.status = status
        super().__init__(message or status)


class ApprovalRequired(TaskControl):
    def __init__(self):
        super().__init__("WAITING_APPROVAL", "Tool needs approval")


class ExecutionContext:
    def __init__(self, settings: Settings, repository: TaskRepository, task: TaskRecord, owner: str, *, enforce_budgets=False):
        from pathlib import Path
        self.settings, self.repo, self.task, self.owner = settings, repository, task, owner
        self.task_id, self.epoch = task.id, task.lease_epoch
        if enforce_budgets:
            limits = repository.bind_budgets(task.id, owner, task.lease_epoch, {
                name: getattr(settings, name) for name in ('max_turns', 'max_tool_calls', 'max_active_seconds')})
            self.settings = settings.model_copy(update=limits)
        self.workspace = Path(repository.workspace(task.workspace_id)["path"])
        self.cp = dict(task.checkpoint)
        self.started = time.monotonic()
        self.prior_active = float(self.cp.get("active_seconds", 0))
        self.extension_secrets = set()

    def safe(self, value: str) -> str:
        secrets = (self.settings.access_token.get_secret_value(),)
        if self.settings.provider:
            secrets += (self.settings.provider.api_key.get_secret_value(),)
        return redact(value, secrets + tuple(self.extension_secrets))

    def safe_value(self, value):
        if isinstance(value, str):
            return self.safe(value)
        if isinstance(value, dict):
            return {self.safe(key): self.safe_value(child) for key, child in value.items()}
        if isinstance(value, list):
            return [self.safe_value(child) for child in value]
        return value

    def stream_prefix(self, value: str):
        secrets = (self.settings.access_token.get_secret_value(),)
        if self.settings.provider:
            secrets += (self.settings.provider.api_key.get_secret_value(),)
        return stream_prefix(value, secrets + tuple(self.extension_secrets))

    def active_seconds(self) -> float:
        return self.prior_active + time.monotonic() - self.started

    def check(self, *, include_pause=True):
        task = self.repo.get(self.task_id)
        if task.status != "RUNNING" or task.lease_owner != self.owner or task.lease_epoch != self.epoch or (task.lease_until or 0) <= time.time():
            raise TaskControl("INTERRUPTED", "Worker lost its lease")
        if task.cancel_requested:
            raise TaskControl("CANCELLED")
        if include_pause and task.pause_requested:
            raise TaskControl("PAUSED")
        if self.active_seconds() + self.repo.group_active_seconds(self.task_id) >= self.settings.max_active_seconds:
            raise TaskControl("FAILED", "Activity time budget exhausted")

    def save(self):
        self.cp["active_seconds"] = self.active_seconds()
        self.repo.checkpoint(self.task_id, self.owner, self.epoch, self.cp)

    async def controlled(self, operation):
        future = asyncio.ensure_future(operation)
        try:
            while not future.done():
                self.check(include_pause=False)
                await asyncio.wait({future}, timeout=0.1)
            self.check(include_pause=False)
            return await future
        except BaseException:
            future.cancel()
            await asyncio.gather(future, return_exceptions=True)
            raise
