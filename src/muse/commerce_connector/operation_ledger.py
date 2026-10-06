"""Durable local send fencing; not an authorization or remote execution boundary.

The future publisher must commit begin() BEFORE sending HTTP. Once marked, even
remote 404 cannot authorize resend. Only a verified terminal remote receipt can
confirm(). This module is deliberately not registered as a public write API.
"""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ChangeOperation, Environment

_ID = re.compile(r'[a-zA-Z0-9_-]{1,100}\Z')
_HASH = re.compile(r'[a-f0-9]{64}\Z')


class OperationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    project_id: str
    connection_id: str
    environment: Environment
    operation_id: str
    operation_digest: str
    resource_key: str
    state: Literal['PREPARED', 'NEEDS_RECONCILIATION', 'SUCCEEDED', 'FAILED']
    fingerprint: str | None = None


class OperationLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        with self._transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS operations (
                project_id TEXT NOT NULL, connection_id TEXT NOT NULL,
                environment TEXT NOT NULL, operation_id TEXT NOT NULL,
                operation_digest TEXT NOT NULL, resource_key TEXT NOT NULL,
                state TEXT NOT NULL, fingerprint TEXT,
                PRIMARY KEY(connection_id, environment, operation_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS target_bindings (
                connection_id TEXT NOT NULL, environment TEXT NOT NULL,
                project_id TEXT NOT NULL, target_hash TEXT NOT NULL,
                PRIMARY KEY(connection_id, environment))''')
            db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS active_resource
                ON operations(connection_id, environment, resource_key)
                WHERE state IN ('PREPARED', 'NEEDS_RECONCILIATION')''')

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _scope(project_id, connection_id, environment, operation_id):
        if (not all(isinstance(value, str) and _ID.fullmatch(value)
                    for value in (project_id, connection_id, operation_id))
                or environment not in ('staging', 'live', 'live-test')):
            raise CommerceFailure('INPUT_INVALID', 422)
        return connection_id, environment, operation_id

    @staticmethod
    def _find(db, project_id, scope):
        row = db.execute('SELECT * FROM operations WHERE connection_id=? AND environment=? AND operation_id=?',
                         scope).fetchone()
        if row is None or row['project_id'] != project_id:
            raise CommerceFailure('NOT_FOUND', 404)
        return OperationRecord(**dict(row))

    def bind_target(self, project_id: str, connection_id: str, environment: Environment, target_url: str) -> None:
        """Immutable target fence. Legacy unbound operations cannot establish origin."""
        self._scope(project_id, connection_id, environment, 'target')
        if not isinstance(target_url, str) or not 1 <= len(target_url) <= 2048:
            raise CommerceFailure('INPUT_INVALID', 422)
        fingerprint = hashlib.sha256(target_url.rstrip('/').encode('utf-8')).hexdigest()
        with self._transaction() as db:
            row = db.execute('SELECT * FROM target_bindings WHERE connection_id=? AND environment=?',
                             (connection_id, environment)).fetchone()
            if row:
                if row['project_id'] != project_id or row['target_hash'] != fingerprint:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return
            existing = db.execute('SELECT 1 FROM operations WHERE connection_id=? AND environment=? LIMIT 1',
                                  (connection_id, environment)).fetchone()
            if existing:
                raise CommerceFailure('RESOURCE_CONFLICT')
            db.execute('INSERT INTO target_bindings VALUES (?,?,?,?)',
                       (connection_id, environment, project_id, fingerprint))

    def get(self, project_id: str, connection_id: str, environment: Environment, operation_id: str) -> OperationRecord:
        scope = self._scope(project_id, connection_id, environment, operation_id)
        with self._transaction() as db:
            return self._find(db, project_id, scope)

    def prepare(self, project_id: str, connection_id: str, environment: Environment,
                operation: ChangeOperation) -> OperationRecord:
        scope = self._scope(project_id, connection_id, environment, operation.operation_id)
        if (not re.fullmatch(r'[a-zA-Z0-9:_-]{1,200}', operation.resource_key)
                or (operation.expected_fingerprint is not None
                    and not _HASH.fullmatch(operation.expected_fingerprint))):
            raise CommerceFailure('INPUT_INVALID', 422)
        try:
            raw = json.dumps(operation.model_dump(mode='json'), ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
        except (ValueError, TypeError, UnicodeError):
            raise CommerceFailure('INPUT_INVALID', 422) from None
        if len(raw) > 6 * 1024 * 1024:
            raise CommerceFailure('INPUT_INVALID', 422)
        digest = hashlib.sha256(raw).hexdigest()
        with self._transaction() as db:
            row = db.execute('SELECT * FROM operations WHERE connection_id=? AND environment=? AND operation_id=?',
                             scope).fetchone()
            if row:
                if row['project_id'] != project_id or row['operation_digest'] != digest:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return OperationRecord(**dict(row))
            try:
                db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?)',
                           (project_id, connection_id, environment, operation.operation_id, digest,
                            operation.resource_key, 'PREPARED', None))
            except sqlite3.IntegrityError:
                raise CommerceFailure('RESOURCE_CONFLICT') from None
            return self._find(db, project_id, scope)

    def begin(self, project_id: str, connection_id: str, environment: Environment,
              operation_id: str) -> OperationRecord:
        scope = self._scope(project_id, connection_id, environment, operation_id)
        with self._transaction() as db:
            record = self._find(db, project_id, scope)
            if record.state != 'PREPARED':
                raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
            db.execute("UPDATE operations SET state='NEEDS_RECONCILIATION' WHERE connection_id=? AND environment=? AND operation_id=?",
                       scope)
            return self._find(db, project_id, scope)

    def confirm(self, project_id: str, connection_id: str, environment: Environment, operation_id: str,
                *, operation_digest: str, succeeded: bool, fingerprint: str | None = None) -> OperationRecord:
        """Trusted publisher only, after validating remote scope/digest/terminal state.

        A transport error, timeout, HTTP status alone, or missing receipt MUST NOT
        be passed as a terminal failure. Remote plugin receipt verification is
        still required before this ledger can be connected to store writes.
        """
        scope = self._scope(project_id, connection_id, environment, operation_id)
        if type(succeeded) is not bool or (fingerprint is not None and not _HASH.fullmatch(fingerprint)):
            raise CommerceFailure('INPUT_INVALID', 422)
        if succeeded and fingerprint is None:
            raise CommerceFailure('INPUT_INVALID', 422)
        state = 'SUCCEEDED' if succeeded else 'FAILED'
        with self._transaction() as db:
            record = self._find(db, project_id, scope)
            if record.operation_digest != operation_digest:
                raise CommerceFailure('RESOURCE_CONFLICT')
            if record.state in ('SUCCEEDED', 'FAILED'):
                if record.state != state or record.fingerprint != fingerprint:
                    raise CommerceFailure('RESOURCE_CONFLICT')
                return record
            if record.state != 'NEEDS_RECONCILIATION':
                raise CommerceFailure('RESOURCE_CONFLICT')
            db.execute('UPDATE operations SET state=?, fingerprint=? WHERE connection_id=? AND environment=? AND operation_id=?',
                       (state, fingerprint, *scope))
            return self._find(db, project_id, scope)
