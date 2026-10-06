"""Durable reference provisioning fences; contains no CMS credentials.

Only the trusted runner calls transitions. UNKNOWN is written before launching
Docker; reserving or restarting an unknown job cannot launch it a second time.
"""
import uuid
from typing import Literal

from pydantic import Field
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Contract
from muse.commerce.reference_environment import reference_names
from muse.commerce.repository import digest, encode


class ReferenceJob(Contract):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    project_id: str
    project_revision: int = Field(ge=1)
    project_hash: str
    revision: int = Field(ge=1)
    asset_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    port: int = Field(ge=1024, le=65535, strict=True)
    resource_names: dict[str, str]
    state: Literal['RESERVED', 'UNKNOWN', 'READY', 'BLOCKED', 'CLEANUP_UNKNOWN', 'CLEANED']
    error_code: str | None = None
    evidence: dict | None = None


class ReferenceJobRepository:
    def __init__(self, repo):
        self.repo, self.db = repo, repo.db

    @staticmethod
    def _read(conn, project_id, identity):
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='reference_job'"),
            {'id': identity, 'project': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404)
        try:
            job = ReferenceJob.model_validate_json(row['data'])
            if (job.id != identity or job.project_id != project_id or digest(job) != row['digest']
                    or job.resource_names != reference_names(identity)):
                raise ValueError()
            return job
        except (ValueError, TypeError):
            raise CommerceFailure('RESOURCE_CONFLICT') from None

    def read(self, project_id, identity):
        with self.db.engine.connect() as conn:
            self.repo._project(conn, project_id)
            return self._read(conn, project_id, identity)

    def list(self, project_id):
        with self.db.engine.connect() as conn:
            self.repo._project(conn, project_id)
            identities = conn.execute(text("SELECT id FROM commerce_artifacts WHERE project_id=:project AND kind='reference_job' ORDER BY id LIMIT 100"),
                {'project': project_id}).scalars().all()
            return [self._read(conn, project_id, identity) for identity in identities]

    @staticmethod
    def _write(conn, job):
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
            {'id': job.id, 'data': encode(job), 'digest': digest(job)})
        return job

    def reserve(self, project_id, project_revision, request_id, asset_digest, port):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
            raise CommerceFailure('INPUT_INVALID', 422)
        receipt_id = digest([project_id, 'reference_request', request_id])
        fingerprint = digest([project_revision, asset_digest, port])
        with self.db.transaction() as conn:
            project = self.repo._project(conn, project_id, project_revision)
            old = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='reference_request'"),
                {'id': receipt_id, 'project': project_id}).mappings().first()
            if old:
                if old['digest'] != fingerprint:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return self._read(conn, project_id, old['data'])
            for row in conn.execute(text("SELECT project_id,id FROM commerce_artifacts WHERE kind='reference_job'")).mappings():
                existing = self._read(conn, row['project_id'], row['id'])
                if existing.port == port and existing.state != 'CLEANED':
                    raise CommerceFailure('RESOURCE_CONFLICT')
            identity = uuid.uuid4().hex
            job = ReferenceJob(id=identity, project_id=project_id, project_revision=project_revision,
                project_hash=digest(project), revision=1, asset_digest=asset_digest, port=port,
                resource_names=reference_names(identity), state='RESERVED')
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'reference_job',:digest,:data)"),
                {'id': identity, 'project': project_id, 'digest': digest(job), 'data': encode(job)})
            conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,NULL,'reference_request',:digest,:data)"),
                {'id': receipt_id, 'project': project_id, 'digest': fingerprint, 'data': identity})
            self.repo.event(conn, project_id, 'reference_reserved', {'job_id': identity})
            return job

    def _transition(self, identity, revision, states, state, *, require_source=False, error=None, evidence=None):
        with self.db.transaction() as conn:
            project_id = conn.execute(text("SELECT project_id FROM commerce_artifacts WHERE id=:id AND kind='reference_job'"), {'id': identity}).scalar()
            job = self._read(conn, project_id, identity)
            if job.revision != revision or job.state not in states:
                raise CommerceFailure('RESOURCE_CONFLICT')
            if require_source:
                project = self.repo._project(conn, project_id, job.project_revision)
                if digest(project) != job.project_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT')
            if state == 'CLEANUP_UNKNOWN':
                project = self.repo._project(conn, project_id)
                refs = [ref for ref in project.environment_refs if ref.connector_ref != 'ref-' + identity]
                if refs != project.environment_refs:
                    updated = project.model_copy(update={'revision': project.revision + 1, 'environment_refs': refs})
                    conn.execute(text('UPDATE commerce_projects SET revision=:revision,data=:data WHERE id=:id'),
                        {'id': project_id, 'revision': updated.revision, 'data': encode(updated)})
                    self.repo._invalidate(conn, project_id)
                    self.repo.event(conn, project_id, 'reference_detached', {'job_id': identity, 'project_revision': updated.revision})
            return self._write(conn, job.model_copy(update={'state': state, 'revision': revision + 1,
                'error_code': error, 'evidence': evidence}))

    def begin(self, identity, *, expected_revision):
        return self._transition(identity, expected_revision, {'RESERVED'}, 'UNKNOWN', require_source=True)

    def ready(self, identity, revision, evidence):
        # Provisioning runner must independently inspect every resource and
        # validate the installed fixed assets and actual PHP safety response.
        with self.db.engine.connect() as conn:
            project_id = conn.execute(text("SELECT project_id FROM commerce_artifacts WHERE id=:id AND kind='reference_job'"), {'id': identity}).scalar()
            job = self._read(conn, project_id, identity)
        expected = {'job_id', 'asset_digest', 'containers', 'volumes', 'network', 'safety'}
        try:
            safety = evidence['safety']
            if (set(evidence) != expected or evidence['job_id'] != identity or evidence['asset_digest'] != job.asset_digest
                    or set(evidence['containers']) != {'wordpress', 'database', 'cli'}
                    or any(not isinstance(value, str) or len(value) != 64 for value in evidence['containers'].values())
                    or set(evidence['volumes']) != {job.resource_names['database_volume'], job.resource_names['site_volume']}
                    or evidence['network'] != job.resource_names['network'] or safety.get('job_id') != identity
                    or safety.get('environment') != 'staging'
                    or any(safety.get(key) is not True for key in ('email_disabled', 'external_requests_disabled',
                        'indexing_disabled', 'cron_disabled', 'offline_gateway_only'))):
                raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CommerceFailure('VERIFICATION_FAILED', 422) from None
        return self._transition(identity, revision, {'UNKNOWN'}, 'READY', require_source=True, evidence=evidence)

    def failed(self, identity, revision, error_code):
        if error_code not in {'EXECUTION_BOUNDARY_UNAVAILABLE', 'VERIFICATION_FAILED', 'READ_TEMPORARY_FAILURE'}:
            raise CommerceFailure('INPUT_INVALID', 422)
        return self._transition(identity, revision, {'UNKNOWN'}, 'BLOCKED', error=error_code)

    def begin_cleanup(self, identity, revision):
        return self._transition(identity, revision, {'RESERVED', 'UNKNOWN', 'READY', 'BLOCKED'}, 'CLEANUP_UNKNOWN')

    def cleaned(self, identity, revision, *, absent_names):
        with self.db.engine.connect() as conn:
            project_id = conn.execute(text("SELECT project_id FROM commerce_artifacts WHERE id=:id AND kind='reference_job'"), {'id': identity}).scalar()
            job = self._read(conn, project_id, identity)
        if not isinstance(absent_names, set) or absent_names != set(job.resource_names.values()):
            raise CommerceFailure('VERIFICATION_FAILED', 422)
        return self._transition(identity, revision, {'CLEANUP_UNKNOWN'}, 'CLEANED')
