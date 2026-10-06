"""Separate product-step permits. No public signing or approval endpoint.

The broker must load a CURRENT persisted root grant and trusted verification;
constructing a grant here is not merchant approval. Projection is recomputed
from authenticated outcomes; caller-supplied operations are never signed.
"""
import base64
import hmac
import json
import math
import re
import time
from dataclasses import dataclass

from muse.commerce.errors import CommerceFailure
from muse.commerce.release_steps import project_product_step
from muse.commerce_connector.authorization import _encode
from muse.commerce_connector.operations import operation_digest


@dataclass(frozen=True)
class ProductReleaseGrant:
    id: str
    intent_digest: str
    project_id: str
    connection_id: str
    environment: str
    target_url: str
    verification_hash: str
    approved_at: float
    expires_at: float
    status: str


class ProductReleaseAuthority:
    def __init__(self, secret: bytes, *, clock=time.time):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError('A separate execution signing secret is required')
        self._secret, self._clock = secret, clock

    def _claims(self, grant, intent, connection, index, history, snapshot, proofs):
        if not isinstance(grant, ProductReleaseGrant) or grant.status != 'approved':
            raise CommerceFailure('APPROVAL_REQUIRED', 403)
        now = self._clock()
        if (any(type(value) not in (int, float) or not math.isfinite(value)
                for value in (grant.approved_at, grant.expires_at, now))
                or grant.approved_at > now or grant.expires_at <= now
                or not 0 < grant.expires_at - grant.approved_at <= 1800):
            raise CommerceFailure('APPROVAL_EXPIRED', 403)
        step = project_product_step(intent, connection, index, history, snapshot, proofs)
        if (grant.intent_digest != step.root_digest or grant.project_id != connection.project_id
                or grant.connection_id != connection.connection_id or grant.environment != connection.environment
                or grant.target_url != connection.base_url):
            raise CommerceFailure('REVIEW_STALE')
        if (any(not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value)
                for value in (grant.id, grant.project_id, grant.connection_id))
                or any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value)
                       for value in (grant.intent_digest, grant.verification_hash))):
            raise CommerceFailure('INPUT_INVALID', 422)
        claims = {'v': 2, 'grant_id': grant.id, 'project_id': grant.project_id,
            'connection_id': grant.connection_id, 'target_url': grant.target_url, 'environment': grant.environment,
            'audience': 'muse-wp-product-step-v2', 'changeset_digest': grant.intent_digest,
            'verification_hash': grant.verification_hash, 'preconditions': step.preconditions,
            'operation_digest': operation_digest(step.operation), 'issued_at': grant.approved_at,
            'expires_at': grant.expires_at, 'step_index': step.index, 'step_key': step.key,
            'sku_identities': step.sku_identities}
        return claims, step

    def issue(self, grant, intent, connection, index, history, snapshot, proofs):
        claims, _ = self._claims(grant, intent, connection, index, history, snapshot, proofs)
        raw = json.dumps(claims, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=False).encode('utf-8')
        token = _encode(raw) + '.' + _encode(hmac.digest(self._secret, raw, 'sha256'))
        if len(token) > 32768:
            raise CommerceFailure('INPUT_INVALID', 422)
        return token

    def verify(self, token, grant, intent, connection, index, history, snapshot, proofs):
        try:
            if not isinstance(token, str) or len(token) > 32768:
                raise ValueError()
            body, signature = token.split('.')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', body) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', signature):
                raise ValueError()
            raw = base64.urlsafe_b64decode(body + '=' * (-len(body) % 4))
            if not hmac.compare_digest(signature, _encode(hmac.digest(self._secret, raw, 'sha256'))):
                raise ValueError()
            claims = json.loads(raw)
            expected, step = self._claims(grant, intent, connection, index, history, snapshot, proofs)
            if (claims != expected or type(claims.get('v')) is not int
                    or type(claims.get('step_index')) is not int
                    or any(type(claims.get(key)) not in (int, float) for key in ('issued_at', 'expires_at'))):
                raise ValueError()
            return step
        except CommerceFailure:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
            raise CommerceFailure('PERMISSION_DENIED', 403) from None
