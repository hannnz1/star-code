import json
import subprocess
from pathlib import Path

import pytest

from tests.muse.commerce.test_php_protocol import php  # noqa: F401


def parameters():
    return {'job_id': 'a' * 32, 'project_id': 'project', 'connection_id': 'stage', 'port': 63660,
        'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2', 'currency': 'USD', 'language': 'en-US',
        'admin_password': 'admin-private-' + 'x' * 48, 'service_password': 'service-private-' + 'x' * 48,
        'execution_secret': 'signing-private-' + 'x' * 48}


@pytest.mark.parametrize('change', [{'port': True}, {'port': 80}, {'currency': 'invalid'}, {'job_id': 'invalid'},
    {'project_id': "evil';"}, {'passed': True}, {'execution_secret': 'short'}])
def test_bootstrap_rejects_bad_input_before_loading_cms_and_never_echoes_secrets(php, tmp_path, change):  # noqa: F811
    script = Path(__file__).resolve().parents[3] / 'src/muse/commerce/assets/reference/bootstrap.php'
    original_entries = set(tmp_path.iterdir())
    result = subprocess.run([php, '-n', str(script), str(tmp_path)], input=json.dumps({**parameters(), **change}),
        capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 2
    assert result.stdout == ''
    assert result.stderr.strip() == 'REFERENCE_BOOTSTRAP_REJECTED'
    assert set(tmp_path.iterdir()) == original_entries


def test_existing_store_is_never_reinstalled_or_credential_rotated(php, tmp_path):  # noqa: F811
    script = Path(__file__).resolve().parents[3] / 'src/muse/commerce/assets/reference/bootstrap.php'
    (tmp_path / 'wp-load.php').write_text('<?php function is_blog_installed() { return true; }', encoding='utf-8')
    before = (tmp_path / 'wp-load.php').read_bytes()
    original_entries = set(tmp_path.iterdir())
    result = subprocess.run([php, '-n', str(script), str(tmp_path)], input=json.dumps(parameters()),
        capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 2
    assert result.stderr.strip() == 'REFERENCE_BOOTSTRAP_REJECTED'
    assert result.stdout == ''
    assert (tmp_path / 'wp-load.php').read_bytes() == before
    assert set(tmp_path.iterdir()) == original_entries
