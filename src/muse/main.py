from __future__ import annotations

import asyncio
import json
import secrets
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from muse.artifacts.service import ArtifactService
from muse.config import Settings, load_settings
from muse.contracts import TERMINAL, TaskRequest
from muse.memory.service import MemoryService
from muse.permissions.secrets import redact
from muse.public_contracts import (
    ApprovalView,
    ArtifactView,
    EventView,
    FileChangeView,
    MemoryView,
    SourceView,
    TaskView,
    UncertainActionView,
    WorkspaceView,
)
from muse.tasks.repository import TaskRepository
from muse.tools.context import ExecutionContext
from muse.tools.files import FileTools


class WorkspaceInput(BaseModel):
    path: str
    name: str = Field(default="Workspace", max_length=160)


class ControlInput(BaseModel):
    expected_revision: int
    content: str = Field(default="", max_length=50000)


class DecisionInput(BaseModel):
    allow: bool
    action_digest: str


class RenewalInput(BaseModel):
    action_digest: str


class FileActionInput(BaseModel):
    call_id: str
    expected_revision: int


class ExternalActionInput(FileActionInput):
    action_digest: str
    successful: bool
    explanation: str = Field(min_length=1, max_length=4000)


class ConversationForkInput(BaseModel):
    sequence: int = Field(ge=0)
    expected_revision: int
    prompt: str = Field(min_length=1, max_length=50000)
    client_request_id: str = Field(min_length=1, max_length=160)


class MemoryInput(BaseModel):
    scope: Literal["user", "project"]
    title: str
    content: str
    workspace_id: str | None = None


def public_task(task):
    output = task.model_dump(exclude={"checkpoint", "lease_owner", "lease_epoch", "lease_until"})
    cp = task.checkpoint
    usage = cp.get("usage")
    output["metrics"] = {"model_requests": cp.get("model_requests", 0), "tool_calls": cp.get("tool_calls", 0),
                         "active_seconds": cp.get("active_seconds", 0), "usage": usage,
                         "estimated_cost": None}
    return output


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings(require_provider=False)
    repo = TaskRepository(settings.data_dir / "state.sqlite3")
    if not repo.workspaces():
        default = settings.data_dir.parent / (settings.data_dir.name + "-workspaces") / "default"
        default.mkdir(parents=True, exist_ok=True)
        repo.register_workspace(str(default), "我的工作区")
    service_context = SimpleNamespace(settings=settings, repo=repo, task_id="", safe=redact)
    artifacts = ArtifactService(service_context)
    memory = MemoryService(repo, settings)
    app = FastAPI(title="MUSE", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.settings, app.state.repository = settings, repo
    app.state.artifacts, app.state.memory = artifacts, memory
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "Last-Event-ID"])

    @app.middleware("http")
    async def access_boundary(request: Request, call_next):
        if request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return JSONResponse({"detail": "Untrusted host"}, status_code=400)
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            return JSONResponse({"detail": "Untrusted origin"}, status_code=403)
        if request.url.path.startswith("/api/") and request.method != "OPTIONS":
            provided = request.headers.get("authorization", "")
            expected = "Bearer " + settings.access_token.get_secret_value()
            if not secrets.compare_digest(provided.encode(), expected.encode()):
                return JSONResponse({"detail": "Local access token required"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; object-src 'none'"
        return response

    @app.exception_handler(ValueError)
    async def invalid_state(request, error):
        detail = str(error)
        return JSONResponse({"detail": detail}, status_code=404 if detail.startswith("Unknown") else 409)

    @app.get("/health")
    def health():
        return {"status": "ok", "application": "MUSE", "version": "0.1.0", "release_version": version('muse-personal-agent')}

    @app.get("/api/settings")
    def public_settings():
        return settings.public()

    @app.get("/api/workspaces", response_model=list[WorkspaceView])
    def workspaces():
        return repo.workspaces()

    @app.post("/api/workspaces", response_model=WorkspaceView, status_code=201)
    def add_workspace(body: WorkspaceInput):
        return repo.register_workspace(body.path, body.name)

    @app.get("/api/tasks", response_model=list[TaskView])
    def tasks():
        return [public_task(task) for task in repo.list()]

    @app.post("/api/tasks", response_model=TaskView, status_code=201)
    def create_task(body: TaskRequest):
        return public_task(repo.create(body))

    @app.get("/api/tasks/{task_id}", response_model=TaskView)
    def task_detail(task_id: str):
        return public_task(repo.get(task_id))

    @app.get('/api/tasks/{task_id}/children', response_model=list[TaskView])
    def task_children(task_id: str):
        repo.get(task_id)
        return [public_task(child) for child in repo.children(task_id)]

    @app.get('/api/tasks/{task_id}/team')
    def task_team(task_id: str):
        repo.get(task_id)
        return {'members': [public_task(repo.get(row['id'])) for row in repo.team_members(task_id)],
                'work_items': repo.team_board(task_id)}

    @app.get('/api/tasks/{task_id}/catalog')
    async def task_catalog(task_id: str):
        from muse.tools.registry import ToolRegistry
        registry = ToolRegistry(ExecutionContext(settings, repo, repo.get(task_id), 'read-only-catalog'))
        return {'skills': json.loads(await registry.skills.list({}, 'catalog')),
                'agents': json.loads(await registry.roles.list({}, 'catalog')),
                'hooks': [{'id': hook.id, 'event': hook.event, 'type': hook.action.type, 'async': hook.async_exec, 'once': hook.once} for hook in registry.hooks.hooks],
                'active-skills': [{'call_id': call['id'], 'name': call['arguments'].get('name'), 'tool': call['name']}
                                  for call in repo.calls(task_id) if call['status'] == 'DONE' and call['name'] in {'load_skill', 'spawn_skill'}],
                'mcp': {'configured_servers': list(registry.mcp.configs), 'discovered': registry.context.cp.get('mcp_catalogs', {})}}

    @app.get('/api/tasks/{task_id}/conversation-checkpoints')
    def conversation_checkpoints(task_id: str):
        return repo.conversation_checkpoints(task_id)

    @app.post('/api/conversations/{task_id}/fork', response_model=TaskView)
    def fork_conversation(task_id: str, body: ConversationForkInput):
        return public_task(repo.fork_checkpoint(task_id, body.sequence, body.expected_revision, body.prompt, body.client_request_id))

    @app.get('/api/tasks/{task_id}/uncertain-actions', response_model=list[UncertainActionView])
    def uncertain_actions(task_id: str):
        repo.get(task_id)
        return [call for call in repo.calls(task_id) if call['status'] == 'UNKNOWN' and call['risk'] == 'execute']

    @app.post('/api/external-actions/{task_id}/reconcile')
    def reconcile_external(task_id: str, body: ExternalActionInput):
        ctx = ExecutionContext(settings, repo, repo.get(task_id), 'user-reconciliation')
        return repo.reconcile_external(task_id, body.call_id, body.action_digest, body.expected_revision,
                                       body.successful, ctx.safe(body.explanation))

    @app.post("/api/tasks/{task_id}/{action}", response_model=TaskView)
    def control(task_id: str, action: Literal["pause", "resume", "cancel", "input", "compact", "reload"], body: ControlInput):
        return public_task(repo.control(task_id, action, expected_revision=body.expected_revision, content=body.content))

    @app.get("/api/tasks/{task_id}/events", response_class=StreamingResponse, responses={200: {"description": "SSE id/data frames contain EventView JSON; comments are heartbeats", "content": {"text/event-stream": {"schema": {"type": "string"}, "x-event-payload-schema": {"$ref": "#/components/schemas/EventView"}}}}})
    async def events(task_id: str, request: Request, after: int = 0, follow: bool = True):
        repo.get(task_id)
        try:
            after = max(after, int(request.headers.get("Last-Event-ID", "0")))
        except ValueError:
            raise HTTPException(400, "Invalid event cursor")

        async def stream():
            cursor = after
            while True:
                batch = repo.events(task_id, cursor)
                for event in batch:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if not follow or (repo.get(task_id).status in TERMINAL and not batch):
                    break
                if await request.is_disconnected():
                    break
                if not batch:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/tasks/{task_id}/artifacts", response_model=list[ArtifactView])
    def task_artifacts(task_id: str):
        repo.get(task_id)
        return [{k: v for k, v in item.items() if k != "storage_path"} for item in artifacts.list(task_id)]

    @app.get("/api/tasks/{task_id}/file-history", response_model=list[FileChangeView])
    def file_history(task_id: str):
        task = repo.get(task_id)
        FileTools(ExecutionContext(settings, repo, task, "user"))
        rows = repo.db.rows("SELECT call_id,path,before_hash,after_hash,restored FROM file_history WHERE task_id=:task", {"task": task_id})
        for row in rows:
            row["path"] = str(Path(row["path"]).relative_to(repo.workspace(task.workspace_id)["path"]))
        return rows

    @app.post("/api/file-actions/{task_id}/reconcile")
    def reconcile(task_id: str, body: FileActionInput):
        task = repo.get(task_id)
        return FileTools(ExecutionContext(settings, repo, task, "user")).reconcile(body.call_id, expected_revision=body.expected_revision)

    @app.post("/api/file-actions/{task_id}/rewind")
    def rewind(task_id: str, body: FileActionInput):
        task = repo.get(task_id)
        if task.status not in TERMINAL or task.revision != body.expected_revision:
            raise ValueError("Rewind requires a terminal task and current revision")
        files = FileTools(ExecutionContext(settings, repo, task, "user"))
        files.rewind(task_id, body.call_id)
        repo.add_event(task_id, "file_rewound", {"call_id": body.call_id})
        return {"restored": True, "scope": "tracked file only; shell side effects are unchanged"}

    @app.get("/api/tasks/{task_id}/sources", response_model=list[SourceView])
    def task_sources(task_id: str):
        repo.get(task_id)
        return repo.db.rows("SELECT id,url,title,sha256,retrieved_at FROM sources WHERE task_id=:task", {"task": task_id})

    @app.get("/api/artifacts/{artifact_id}")
    def download(artifact_id: str):
        record, data = artifacts.read(artifact_id)
        return Response(data, media_type=record["media_type"], headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(record['name'])}"})

    @app.get("/api/approvals", response_model=list[ApprovalView])
    def approvals(task_id: str | None = None):
        return repo.approvals(task_id)

    @app.post("/api/approvals/{approval_id}/decision")
    def decision(approval_id: str, body: DecisionInput):
        return repo.decide_approval(approval_id, body.allow, body.action_digest)

    @app.post("/api/approvals/{approval_id}/renew")
    def renew_approval(approval_id: str, body: RenewalInput):
        return repo.renew_approval(approval_id, body.action_digest)

    @app.get("/api/memories", response_model=list[MemoryView])
    def memories():
        return memory.list()

    @app.post("/api/memories", response_model=MemoryView, status_code=201)
    def remember(body: MemoryInput):
        return memory.upsert(**body.model_dump())

    @app.patch("/api/memories/{memory_id}", response_model=MemoryView)
    def edit_memory(memory_id: str, body: dict):
        current = next((item for item in memory.list() if item["id"] == memory_id), None)
        if current is None:
            raise ValueError("Unknown memory")
        if set(body) - {"title", "content", "scope", "workspace_id"}:
            raise HTTPException(422, "Unsupported memory fields")
        values = {key: current[key] for key in ("title", "content", "scope", "workspace_id")}
        try:
            validated = MemoryInput(**(values | body))
        except ValidationError:
            raise HTTPException(422, "Invalid memory fields") from None
        return memory.upsert(**validated.model_dump(), memory_id=memory_id)

    @app.delete("/api/memories/{memory_id}", status_code=204)
    def forget(memory_id: str):
        memory.delete(memory_id)
        return Response(status_code=204)

    frontend = Path(__file__).resolve().parent / '_web'
    if not (frontend / 'index.html').is_file():
        frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/")
    def index():
        if (frontend / "index.html").is_file():
            return FileResponse(frontend / "index.html")
        return {"application": "MUSE", "message": "Build frontend with npm run build, then restart API"}

    def openapi_schema():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            schema["components"]["schemas"]["EventView"] = EventView.model_json_schema()
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi_schema
    return app
