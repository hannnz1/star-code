"""Internal HMAC execution permits; never an Agent-visible signing endpoint.

The trusted backend must supply CURRENT persisted approval at verification time.
This does not implement merchant approval storage, remote WP verification, or OS
isolation. No API/CLI write route is enabled by creating this authority.
"""
import base64
import hmac
import json
import math
import re
import time

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ApprovalGrant, ChangeOperation
from muse.commerce_connector.operations import operation_digest, validate_operation
from muse.commerce_connector.wordpress import WordPressConnection


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


class ExecutionAuthority:
    def __init__(self, secret: bytes, *, clock=time.time):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError('A separate execution signing secret is required')
        self._secret, self._clock = secret, clock

    def _claims(self, approval: ApprovalGrant, connection: WordPressConnection, operation: ChangeOperation, issued: float):
        validate_operation(operation)
        if operation.kind in {'set_owned_shipping', 'set_owned_store_navigation'}:
            raise CommerceFailure('PERMISSION_DENIED', 403)
        if operation.kind == 'create_product_draft' and 'crew_preview_seed' in operation.payload['product']['source_facts']:
            raise CommerceFailure('PERMISSION_DENIED',403)
        if (approval.project_id != connection.project_id or approval.environment != connection.environment):
            raise CommerceFailure('PERMISSION_DENIED', 403)
        now = self._clock()
        if approval.status != 'approved':
            raise CommerceFailure('APPROVAL_REQUIRED', 403)
        if (not math.isfinite(approval.expires_at) or not math.isfinite(issued)
                or not math.isfinite(now) or issued > now or approval.expires_at <= now
                or not 0 < approval.expires_at - issued <= 1800):
            raise CommerceFailure('APPROVAL_EXPIRED', 403)
        for value in (approval.id, approval.project_id, connection.connection_id):
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value):
                raise CommerceFailure('INPUT_INVALID', 422)
        for value in (approval.changeset_digest, approval.verification_hash):
            if not re.fullmatch(r'[a-f0-9]{64}', value):
                raise CommerceFailure('INPUT_INVALID', 422)
        if approval.resource_preconditions.get(operation.resource_key) != operation.expected_fingerprint:
            raise CommerceFailure('REVIEW_STALE')
        return {'v': 1, 'grant_id': approval.id, 'project_id': approval.project_id,
                'connection_id': connection.connection_id, 'target_url': connection.base_url,
                'environment': approval.environment, 'audience': 'muse-wp-operation-v1',
                'changeset_digest': approval.changeset_digest, 'verification_hash': approval.verification_hash,
                'preconditions': approval.resource_preconditions, 'operation_digest': operation_digest(operation),
                'issued_at': issued, 'expires_at': approval.expires_at}

    def issue(self, approval: ApprovalGrant, connection: WordPressConnection, operation: ChangeOperation) -> str:
        """Trusted backend only, after independently validating verification/approval."""
        claims = self._claims(approval, connection, operation, self._clock())
        raw = json.dumps(claims, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        token = _encode(raw) + '.' + _encode(hmac.digest(self._secret, raw, 'sha256'))
        if len(token) > 8192:
            raise CommerceFailure('INPUT_INVALID', 422)
        return token

    def verify(self, token: str, approval: ApprovalGrant, connection: WordPressConnection, operation: ChangeOperation) -> ChangeOperation:
        try:
            if not isinstance(token, str) or len(token) > 8192:
                raise ValueError()
            body, signature = token.split('.')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', body) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', signature):
                raise ValueError()
            raw = base64.urlsafe_b64decode(body + '=' * (-len(body) % 4))
            expected_signature = _encode(hmac.digest(self._secret, raw, 'sha256'))
            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError()
            claims = json.loads(raw)
            issued = claims['issued_at']
            if type(issued) not in (int, float):
                raise ValueError()
            expected = self._claims(approval, connection, operation, issued)
            if claims != expected:
                raise ValueError()
            return validate_operation(operation)
        except CommerceFailure:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
            raise CommerceFailure('PERMISSION_DENIED', 403) from None
