import json
import subprocess
from pathlib import Path

import pytest

from tests.muse.commerce.test_php_protocol import php  # noqa: F401


@pytest.mark.parametrize('environment,job', [('live', 'a' * 32), ('live-test', 'a' * 32), ('staging', 'invalid')])
def test_guard_never_changes_a_non_job_or_merchant_environment(php, environment, job):  # noqa: F811
    assert run(php, environment, job) == {'enabled': False}


def run(executable, environment='staging', job='a' * 32, real_gateway=False):
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([executable, '-n', str(root / 'tests/fixtures/commerce/php-staging-safety.php'),
        str(root / 'src/muse/commerce/assets/reference/staging-safety.php')],
        input=json.dumps({'environment': environment, 'job': job, 'real_gateway': real_gateway}),
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_actual_php_filters_disable_side_effects_and_reject_enabled_real_gateway(php):  # noqa: F811
    value = run(php)
    assert all(value[key] is True for key in ('email_disabled', 'external_requests_disabled',
        'indexing_disabled', 'cron_disabled', 'offline_gateway_only'))
    assert value['gateways'] == ['cod']
    assert value['cod_status'] == 'on-hold'
    unsafe = run(php, real_gateway=True)
    assert unsafe['offline_gateway_only'] is False
    assert unsafe['gateways'] == ['cod']
