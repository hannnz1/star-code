"""Fixed-target, read-only WordPress client; no arbitrary URLs or write retry."""
import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import Environment
from muse.commerce.repository import digest


@dataclass(frozen=True)
class WordPressConnection:
    connection_id: str
    project_id: str
    environment: Environment
    base_url: str
    username: str = field(repr=False)
    application_password: str = field(repr=False)
    approved_development_http: bool = False

    def __post_init__(self):
        url = urlsplit(self.base_url)
        if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', self.connection_id)
                or self.environment not in {'staging', 'live', 'live-test'}
                or not self.project_id or not self.username or not self.application_password
                or not url.hostname or url.username or url.password or url.query or url.fragment
                or not re.fullmatch(r'(?:/[a-zA-Z0-9_-]+)*/?', url.path)):
            raise ValueError('Invalid connector configuration')
        if url.scheme != 'https' and not (url.scheme == 'http' and self.environment == 'staging'
                and self.approved_development_http and url.hostname in {'127.0.0.1', 'localhost', '::1'}):
            raise ValueError('HTTPS required outside explicitly approved loopback staging')
        # Force port validation; reject malformed URLs before any request.
        _ = url.port


class WordPressReader:
    def __init__(self, connection: WordPressConnection, *, transport=None, sleep=asyncio.sleep):
        self.connection, self.transport, self.sleep = connection, transport, sleep

    async def read(self, resource: str, *, remaining_seconds: float):
        if resource not in {'snapshot', 'capabilities'}:
            raise CommerceFailure('PERMISSION_DENIED', 403)
        if remaining_seconds <= 0:
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 503)
        try:
            async with asyncio.timeout(min(remaining_seconds, 120)):
                return await self._read(resource, min(remaining_seconds, 120))
        except TimeoutError:
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 503) from None

    async def read_sku(self, sku: str, *, remaining_seconds: float):
        """An explicit SKU query proves absence; bounded product snapshots cannot."""
        if (not isinstance(sku, str) or not 1 <= len(sku.strip()) <= 100
                or any(char in sku for char in '<>\x00') or remaining_seconds <= 0):
            raise CommerceFailure('INPUT_INVALID', 422)
        canonical = sku.strip().casefold()
        return await self._resource_state('sku', sku, canonical, 'sku', 'product_id', remaining_seconds)

    async def read_page_slug(self, slug: str, *, remaining_seconds: float):
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', slug) or remaining_seconds <= 0:
            raise CommerceFailure('INPUT_INVALID', 422)
        return await self._resource_state('page_slug', slug, slug, 'slug', 'page_id', remaining_seconds)

    async def read_media_sha256(self, sha256: str, *, remaining_seconds: float):
        from muse.commerce_connector.media import RemoteAttachment
        if not isinstance(sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', sha256) or remaining_seconds <= 0:
            raise CommerceFailure('INPUT_INVALID', 422)
        try:
            async with asyncio.timeout(min(remaining_seconds, 120)):
                proof = await self._read('resources', min(remaining_seconds, 120), params={'media_sha256': sha256})
            state = proof['state']
            if (set(proof) != {'resource_key', 'fingerprint', 'state'} or not isinstance(state, dict)
                    or type(state.get('exists')) is not bool or state.get('sha256') != sha256
                    or set(state) != ({'sha256', 'exists', 'attachment'} if state['exists'] else {'sha256', 'exists'})
                    or proof['resource_key'] != 'media-sha256:' + sha256 or proof['fingerprint'] != digest(state)):
                raise ValueError('Invalid image proof')
            if state['exists']:
                attachment = RemoteAttachment.model_validate(state['attachment'])
                if (attachment.model_dump(mode='json') != state['attachment'] or attachment.sha256 != sha256
                        or attachment.muse_project_id != self.connection.project_id
                        or attachment.media_ref != digest([self.connection.project_id, 'image', sha256])
                        or attachment.width * attachment.height > 20_000_000):
                    raise ValueError('Image scope differs')
            return proof
        except (TimeoutError, ValueError, TypeError, KeyError, AttributeError):
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 502) from None

    async def _resource_state(self, parameter, value, canonical, identity_field, id_field, remaining_seconds):
        try:
            async with asyncio.timeout(min(remaining_seconds, 120)):
                result = await self._read('resources', min(remaining_seconds, 120), params={parameter: value})
            state = result['state']
            expected_keys = {identity_field, 'exists', id_field, 'entity_fingerprint'} if state.get('exists') is True else {identity_field, 'exists'}
            prefix = 'sku:' if parameter == 'sku' else 'page-slug:'
            if (set(result) != {'resource_key', 'fingerprint', 'state'} or set(state) != expected_keys
                    or state[identity_field] != canonical or type(state['exists']) is not bool
                    or (state['exists'] and (type(state[id_field]) is not int or state[id_field] <= 0
                        or not isinstance(state['entity_fingerprint'], str)
                        or not re.fullmatch(r'[a-f0-9]{64}', state['entity_fingerprint'])))
                    or result['resource_key'] != prefix + hashlib.sha256(canonical.encode()).hexdigest()
                    or result['fingerprint'] != digest(state)):
                raise ValueError()
            return result
        except (TimeoutError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 502) from None

    async def _read(self, resource, remaining_seconds, *, params=None):
        deadline = time.monotonic() + remaining_seconds
        url = self.connection.base_url.rstrip('/') + '/wp-json/muse/v1/' + resource
        # Default HTTPTransport has zero retries. Redirects and environment proxies are disabled.
        async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, trust_env=False,
                                    auth=(self.connection.username, self.connection.application_password), timeout=10) as client:
            for attempt in range(3):
                retry_after = None
                try:
                    async with client.stream('GET', url, params=params) as response:
                        status = response.status_code
                        if status == 200:
                            chunks, size = [], 0
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > 4 * 1024 * 1024:
                                    raise CommerceFailure('READ_TEMPORARY_FAILURE', 502)
                                chunks.append(chunk)
                            import json
                            try:
                                data = json.loads(b''.join(chunks))
                                if not isinstance(data, dict):
                                    raise TypeError()
                                return data
                            except (ValueError, UnicodeError, TypeError):
                                raise CommerceFailure('READ_TEMPORARY_FAILURE', 502) from None
                        if status == 401:
                            raise CommerceFailure('AUTH_REQUIRED', 502)
                        if status == 403 or 300 <= status < 400:
                            raise CommerceFailure('PERMISSION_DENIED', 502)
                        if status != 429 and status < 500:
                            raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
                        retry_after = response.headers.get('Retry-After')
                except (httpx.TimeoutException, httpx.NetworkError):
                    pass
                delay = float(attempt + 1)
                if retry_after:
                    try:
                        if retry_after.isdigit():
                            delay = float(retry_after)
                        else:
                            date = parsedate_to_datetime(retry_after)
                            delay = max(0, (date - datetime.now(UTC)).total_seconds())
                    except (ValueError, TypeError, OverflowError):
                        pass
                if attempt == 2 or delay > 60 or delay >= deadline - time.monotonic():
                    raise CommerceFailure('READ_TEMPORARY_FAILURE', 503)
                await self.sleep(delay)
        raise CommerceFailure('READ_TEMPORARY_FAILURE', 503)
