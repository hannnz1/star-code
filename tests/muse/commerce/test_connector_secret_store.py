import json
import os

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.secret_store import load_connector_config


def test_secret_loader_requires_linux_owner_only_boundary(tmp_path):
    source = tmp_path / 'connections.json'
    source.write_text(json.dumps({'token': 'connector-private-test', 'connections': []}))
    if os.name == 'nt':
        with pytest.raises(CommerceFailure) as error:
            load_connector_config(source)
        assert error.value.public.code == 'EXECUTION_BOUNDARY_UNAVAILABLE'
    else:
        source.chmod(0o644)
        with pytest.raises(CommerceFailure):
            load_connector_config(source)
        tmp_path.chmod(0o700)
        source.chmod(0o600)
        connections, token = load_connector_config(source)
        assert connections == {} and token == 'connector-private-test'


def test_secret_loader_never_exposes_missing_path(tmp_path):
    with pytest.raises(CommerceFailure) as error:
        load_connector_config(tmp_path / 'private-missing.json')
    assert 'private-missing' not in error.value.public.model_dump_json()
