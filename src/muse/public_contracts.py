"""Public response contracts; no worker checkpoint or credentials."""
from typing import Any, Literal

from pydantic import BaseModel

from muse.contracts import TaskStatus


class UsageView(BaseModel):
    input_tokens: int
    output_tokens: int
    complete: bool

class MetricsView(BaseModel):
    model_requests: int
    tool_calls: int
    active_seconds: float
    usage: UsageView | None
    estimated_cost: float | None

class TaskView(BaseModel):
    id: str
    prompt: str
    workspace_id: str
    scenario: Literal['general', 'research', 'documents', 'coding']
    client_request_id: str
    parent_task_id: str | None
    read_only: bool
    status: TaskStatus
    revision: int
    created_at: float
    updated_at: float
    cancel_requested: bool
    pause_requested: bool
    result: str
    error: str
    metrics: MetricsView

class WorkspaceView(BaseModel):
    id: str
    name: str
    path: str
    created_at: float

class ArtifactView(BaseModel):
    id: str
    task_id: str
    name: str
    media_type: str
    sha256: str
    version: int
    created_at: float

class SourceView(BaseModel):
    id: str
    url: str
    title: str
    sha256: str
    retrieved_at: float

class ApprovalView(BaseModel):
    id: str
    task_id: str
    tool_call_id: str
    action_digest: str
    status: Literal['PENDING', 'APPROVED', 'DENIED']
    expires_at: float
    created_at: float
    name: str
    arguments: dict[str, Any]

class MemoryView(BaseModel):
    id: str
    scope: Literal['user', 'project']
    workspace_id: str | None
    title: str
    content: str
    source_task_id: str | None
    updated_at: float


class UncertainActionView(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]
    digest: str
    attempts: int

class FileChangeView(BaseModel):
    call_id: str
    path: str
    before_hash: str | None
    after_hash: str
    restored: int

class EventView(BaseModel):
    task_id: str
    sequence: int
    type: str
    payload: dict[str, Any]
    created_at: float
