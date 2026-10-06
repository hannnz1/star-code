"""Read-only connector ASGI factory. Run under a separate Linux service identity."""
import asyncio
import secrets
from contextlib import asynccontextmanager, suppress
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import Field

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_review import MerchantReleaseReview
from muse.commerce.models import (
    Contract,
    EnvironmentRef,
    PlatformCapabilities,
    StoreSnapshot,
)
from muse.commerce_connector.wordpress import WordPressConnection, WordPressReader


class PublicationCommand(Contract):
    project_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,200}$')
    expected_revision: int = Field(ge=1, strict=True)
    action: Literal['publish', 'reconcile']


class ReferenceReservation(Contract):
    project_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,200}$')
    expected_revision: int = Field(ge=1, strict=True)
    client_request_id: str = Field(min_length=1, max_length=200)


class ReferenceCommand(Contract):
    project_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,200}$')
    expected_revision: int = Field(ge=1, strict=True)
    action: Literal['provision', 'verify', 'recover', 'cleanup']


class VerificationReservation(ReferenceReservation):
    plan_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,200}$')


class VerificationCommand(Contract):
    project_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,200}$')
    expected_revision: int = Field(ge=1, strict=True)
    action: Literal['cancel', 'reconcile', 'resume_staging']


def create_connector_app(connections: dict[str, WordPressConnection], *, token: str, transport=None, publication=None, reference=None, verification=None) -> FastAPI:
    if not token or len(token) < 16:
        raise ValueError('A separate connector token is required')
    if any(key != value.connection_id for key, value in connections.items()):
        raise ValueError('Connection registry mismatch')
    registry = dict(connections)
    @asynccontextmanager
    async def lifespan(_app):
        worker = None
        stop = asyncio.Event()
        lease = getattr(verification, 'host_lease', None)
        try:
            if verification is not None:
                if lease is None or lease.fd is None:
                    raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
                await asyncio.to_thread(verification.recover_owned)
                worker = asyncio.create_task(verification.run(stop))
                _app.state.verification_worker = worker
            yield
        finally:
            stop.set()
            try:
                if worker is not None:
                    worker.cancel()
                    with suppress(asyncio.CancelledError):
                        await worker
            finally:
                if lease is not None:
                    lease.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def authenticate(authorization: str = Header(default='')):
        if not secrets.compare_digest(authorization.encode(), ('Bearer ' + token).encode()):
            raise CommerceFailure('AUTH_REQUIRED', 401)

    @app.exception_handler(CommerceFailure)
    async def public_failure(request, error):
        return JSONResponse(status_code=error.status, content={'error': error.public.model_dump()})

    def resolve(connection_id, project_id):
        value = registry.get(connection_id)
        if value is None and reference is not None:
            value = reference.resolve_connection(connection_id, project_id)
        if value is None or value.project_id != project_id:
            raise CommerceFailure('NOT_FOUND', 404)
        return value

    def reference_service():
        if reference is None:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        return reference

    @app.post('/v1/reference-jobs', dependencies=[Depends(authenticate)])
    async def reserve_reference(body: ReferenceReservation):
        return await asyncio.to_thread(reference_service().reserve, body.project_id,
            body.expected_revision, body.client_request_id)

    @app.get('/v1/reference-jobs/{job_id}', dependencies=[Depends(authenticate)])
    async def read_reference(job_id: str, project_id: str):
        return await asyncio.to_thread(reference_service().read, project_id, job_id)

    @app.post('/v1/reference-jobs/{job_id}', dependencies=[Depends(authenticate)])
    async def execute_reference(job_id: str, body: ReferenceCommand):
        return await reference_service().execute(body.project_id, job_id, body.expected_revision, body.action)

    def verification_service():
        worker = getattr(app.state, 'verification_worker', None)
        if verification is None or worker is not None and worker.done():
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        return verification

    @app.post('/v1/verification-jobs', dependencies=[Depends(authenticate)])
    async def reserve_verification(body: VerificationReservation):
        return await asyncio.to_thread(verification_service().reserve, body.project_id,
            body.plan_id, body.expected_revision, body.client_request_id)

    @app.get('/v1/verification-jobs', dependencies=[Depends(authenticate)])
    async def list_verifications(project_id: str, plan_id: str):
        return await asyncio.to_thread(verification_service().list, project_id, plan_id)

    @app.get('/v1/verification-jobs/{job_id}', dependencies=[Depends(authenticate)])
    async def read_verification(job_id: str, project_id: str):
        return await asyncio.to_thread(verification_service().read, project_id, job_id)

    @app.post('/v1/verification-jobs/{job_id}', dependencies=[Depends(authenticate)])
    async def cancel_verification(job_id: str, body: VerificationCommand):
        if body.action == 'resume_staging':
            return await verification_service().resume_staging(body.project_id, job_id, body.expected_revision)
        if body.action == 'reconcile':
            return await verification_service().reconcile(body.project_id, job_id, body.expected_revision)
        return await asyncio.to_thread(verification_service().cancel, body.project_id,
            job_id, body.expected_revision)

    async def publication_scope(connection_id, project_id, plan_id, intent_digest, revision):
        connection = resolve(connection_id, project_id)
        if publication is None:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        view = await asyncio.to_thread(publication.review, project_id, plan_id, intent_digest, revision)
        if (view.target.connector_ref != connection.connection_id or view.target.environment != connection.environment
                or view.target.public_url != connection.base_url):
            raise CommerceFailure('PERMISSION_DENIED', 403)
        return view

    @app.get('/v1/connections/{connection_id}/publication/{plan_id}/{intent_digest}',
        dependencies=[Depends(authenticate)], response_model=MerchantReleaseReview)
    async def publication_review(connection_id: str, plan_id: str, intent_digest: str, project_id: str,
                                 revision: int = Query(ge=1)):
        return await publication_scope(connection_id, project_id, plan_id, intent_digest, revision)

    @app.post('/v1/connections/{connection_id}/publication/{plan_id}/{intent_digest}',
        dependencies=[Depends(authenticate)], response_model=MerchantReleaseReview)
    async def publication_command(connection_id: str, plan_id: str, intent_digest: str, body: PublicationCommand):
        await publication_scope(connection_id, body.project_id, plan_id, intent_digest, body.expected_revision)
        return await publication.execute(body.project_id, plan_id, intent_digest, body.expected_revision,
            reconcile_only=body.action == 'reconcile')

    @app.get('/v1/connections/{connection_id}', dependencies=[Depends(authenticate)], response_model=EnvironmentRef)
    async def describe(connection_id: str, project_id: str):
        connection = resolve(connection_id, project_id)
        return EnvironmentRef(id=connection.connection_id, project_id=connection.project_id,
            environment=connection.environment, public_url=connection.base_url, connector_ref=connection.connection_id)

    @app.get('/v1/connections/{connection_id}/snapshot', dependencies=[Depends(authenticate)], response_model=StoreSnapshot)
    async def snapshot(connection_id: str, project_id: str, remaining_seconds: float = Query(default=20, gt=0, le=120)):
        connection = resolve(connection_id, project_id)
        reader = WordPressReader(connection, transport=transport)
        value = await reader.read('snapshot', remaining_seconds=remaining_seconds)
        return normalize_snapshot(value, project_id, connection.environment)

    @app.get('/v1/connections/{connection_id}/capabilities', dependencies=[Depends(authenticate)], response_model=PlatformCapabilities)
    async def capabilities(connection_id: str, project_id: str):
        connection = resolve(connection_id, project_id)
        value = await WordPressReader(connection, transport=transport).read('capabilities', remaining_seconds=20)
        from pydantic import ValidationError
        try:
            return PlatformCapabilities.model_validate(value)
        except ValidationError:
            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422) from None

    return app
