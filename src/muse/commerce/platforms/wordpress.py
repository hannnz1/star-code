"""Main backend reads only the fixed connector service, never WordPress credentials."""
import asyncio
import json
import re
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from muse.commerce.context import normalize_snapshot, require_capabilities
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import EnvironmentRef


class WordPressPlatform:
    def __init__(self, config, *, lock=None, transport=None):
        self.config, self.transport = config, transport
        if lock is None:
            try:
                lock = json.loads(config.versions_lock_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise ValueError('Cannot read the configured commerce versions lock') from None
        self.lock = json.loads(json.dumps(lock))

    async def _get(self, project_id, connection_id, resource=''):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', connection_id):
            raise CommerceFailure('INPUT_INVALID', 422, project_id=project_id)
        if resource not in {'', '/snapshot', '/capabilities'}:
            raise CommerceFailure('PERMISSION_DENIED', 403, project_id=project_id)
        target = self.config.service_url + '/v1/connections/' + connection_id + resource
        try:
            async with (
                asyncio.timeout(25),
                httpx.AsyncClient(transport=self.transport, follow_redirects=False, trust_env=False,
                    headers={'Authorization': 'Bearer ' + self.config.token.get_secret_value()}, timeout=20) as client,
                client.stream('GET', target, params={'project_id': project_id}) as response,
            ):
                if response.status_code != 200:
                    codes = {401: ('AUTH_REQUIRED', 502), 403: ('PERMISSION_DENIED', 502),
                             404: ('NOT_FOUND', 404), 422: ('UNSUPPORTED_CAPABILITY', 422),
                             502: ('READ_TEMPORARY_FAILURE', 502)}
                    code, status = codes.get(response.status_code, ('READ_TEMPORARY_FAILURE', 503))
                    if 300 <= response.status_code < 400:
                        code, status = 'PERMISSION_DENIED', 502
                    elif response.status_code in {422, 502, 503}:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 16384:
                                break
                        if len(body) <= 16384:
                            try:
                                envelope = json.loads(body)
                                public_code = envelope.get('error', {}).get('code') if isinstance(envelope, dict) else None
                                allowed = {'AUTH_REQUIRED', 'PERMISSION_DENIED', 'UNSUPPORTED_CAPABILITY',
                                           'READ_TEMPORARY_FAILURE', 'VERIFICATION_UNAVAILABLE'}
                                if isinstance(public_code, str) and public_code in allowed:
                                    code = public_code
                            except (ValueError, TypeError, AttributeError):
                                pass  # Only known codes survive; remote messages are discarded.
                    # Never echo remote error bodies or transparently retry the service.
                    raise CommerceFailure(code, status, project_id=project_id)
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise CommerceFailure('READ_TEMPORARY_FAILURE', 502, project_id=project_id)
                    chunks.append(chunk)
                data = json.loads(b''.join(chunks))
                if not isinstance(data, dict):
                    raise TypeError('Invalid connector response')
                return data
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, UnicodeError):
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 503, project_id=project_id) from None

    async def describe(self, project_id, connection_id):
        raw = await self._get(project_id, connection_id)
        try:
            reference = EnvironmentRef.model_validate(raw)
            url = urlsplit(reference.public_url)
            if (reference.project_id != project_id or reference.id != connection_id or reference.connector_ref != connection_id
                    or not url.hostname or url.username or url.password or url.query or url.fragment
                    or (url.scheme != 'https' and not (url.scheme == 'http' and reference.environment == 'staging'
                        and url.hostname in {'localhost', '127.0.0.1', '::1'}))):
                raise ValueError('Connector identity mismatch')
            _ = url.port
            return reference
        except (ValidationError, ValueError):
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 502, project_id=project_id) from None

    async def capabilities(self, project_id, connection_id):
        return require_capabilities(await self._get(project_id, connection_id, '/capabilities'), self.lock)

    async def snapshot(self, project_id, connection_id, environment):
        raw = await self._get(project_id, connection_id, '/snapshot')
        if raw.get('project_id') != project_id or raw.get('environment') != environment:
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 502, project_id=project_id)
        return normalize_snapshot(raw, project_id, environment)
