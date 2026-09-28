from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TaskStatus = Literal["QUEUED", "RUNNING", "WAITING_INPUT", "WAITING_APPROVAL", "PAUSED", "INTERRUPTED", "SUCCEEDED", "FAILED", "CANCELLED"]
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
PermissionMode = Literal['default', 'acceptEdits', 'plan']


class TaskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=50000)
    workspace_id: str
    scenario: Literal["general", "research", "documents", "coding"] = "general"
    client_request_id: str = Field(min_length=1, max_length=200)
    parent_task_id: str | None = None
    read_only: bool = False
    permission_mode: PermissionMode = 'default'
    coordinator_mode: bool = False
    plan_task_id: str | None = None
    plan_sha256: str | None = None
    current_directory: str = Field(default='.', min_length=1, max_length=4096)

    @model_validator(mode='after')
    def permission_compatibility(self):
        if self.read_only:
            if 'permission_mode' in self.model_fields_set and self.permission_mode != 'plan':
                raise ValueError('read_only=true requires permission_mode=plan')
            self.permission_mode = 'plan'
        if self.permission_mode == 'plan':
            self.read_only = True
        return self

    @field_validator("prompt", mode="before")
    @classmethod
    def clean_prompt(cls, value):
        return value.strip() if isinstance(value, str) else value


class TaskRecord(TaskRequest):
    policy_version: int = 1
    legacy_policy: bool = False
    id: str
    status: TaskStatus = "QUEUED"
    revision: int = 1
    created_at: float
    updated_at: float
    cancel_requested: bool = False
    pause_requested: bool = False
    lease_owner: str | None = None
    lease_epoch: int = 0
    lease_until: float | None = None
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    error: str = ""


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    call_id: str
    status: Literal["success", "error", "denied", "cancelled"] = "success"
    content: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    risk: Literal["read", "write", "execute"] = "read"


class ModelEvent(BaseModel):
    type: Literal["text", "call", "usage", "done", "summary", "protocol_state"]
    text: str = ""
    call: ToolCall | None = None
    usage: dict[str, Any] | None = None
    protocol_state: dict[str, Any] | None = Field(default=None, exclude=True, repr=False)


class AgentResult(BaseModel):
    status: TaskStatus
    text: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
