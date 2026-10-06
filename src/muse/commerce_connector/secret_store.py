"""Service configuration loaded only under the independent Linux connector UID."""
import json
import os
import stat
from pathlib import Path

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.wordpress import WordPressConnection


def load_connector_config(path: Path) -> tuple[dict[str, WordPressConnection], str]:
    if os.name != 'posix':
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
    try:
        path = Path(path).absolute()
        # No agent workspace, group-readable file, symlink, or different UID is acceptable.
        for candidate in (path, path.parent):
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError()
        with path.open('rb') as source:
            data = source.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        value = json.loads(data)
        token = value['token']
        if not isinstance(token, str) or len(token) < 16:
            raise ValueError()
        rows = [WordPressConnection(**item) for item in value['connections']]
        connections = {item.connection_id: item for item in rows}
        if len(rows) != len(connections):
            raise ValueError()
        return connections, token
    except (OSError, ValueError, TypeError, KeyError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None


def load_execution_secrets(path: Path) -> dict[str, bytes]:
    # Reuse the connector's owner-only Linux gate. No main-backend module
    # calls this loader, and its errors never include secret values or paths.
    connections, _token = load_connector_config(path)
    try:
        with Path(path).open('rb') as source:
            content = source.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError()
        values = json.loads(content)['execution_secrets']
        if not isinstance(values, dict) or set(values) != set(connections):
            raise ValueError()
        secrets = {}
        for identity, value in values.items():
            if not isinstance(value, str) or not 32 <= len(value.encode('utf-8')) <= 1024:
                raise ValueError()
            secrets[identity] = value.encode('utf-8')
        return secrets
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
