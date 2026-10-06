import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope='module')
def php():
    executable = os.environ.get('MUSE_TEST_PHP') or shutil.which('php')
    portable = ROOT / 'work/tools/php-8.4.26/php.exe'
    if executable is None and portable.exists():
        executable = str(portable)
    if executable is None:
        pytest.skip('PHP CLI required')
    return executable


def run_setup(php, **changes):
    value = {'mode': 'state', 'admin': True, 'nonce': True, 'shipping': True, 'payment': True, 'options': {}, 'post': {}}
    value.update(changes)
    result = subprocess.run([php, '-n', str(ROOT / 'tests/fixtures/commerce/php-store-setup.php'),
                             str(ROOT / 'wordpress/muse-connector/includes/store-setup.php')],
                            input=json.dumps(value), text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('shipping,payment,confirmed', [(True, True, True), (False, True, True),
                         (True, False, True), (True, True, False), (False, False, False)])
def test_setup_requires_human_confirmation_and_current_configuration(php, shipping, payment, confirmed):
    options = {'muse_shipping_confirmed': 'yes', 'muse_payment_confirmed': 'yes'} if confirmed else {}
    assert run_setup(php, shipping=shipping, payment=payment, options=options) == {
        'shipping_confirmed': shipping and confirmed, 'payment_confirmed': payment and confirmed}


@pytest.mark.parametrize('admin,nonce,error', [(False, True, 'denied'), (True, False, 'nonce')])
def test_service_account_or_invalid_nonce_cannot_confirm_setup(php, admin, nonce, error):
    assert run_setup(php, mode='save', admin=admin, nonce=nonce,
                     post={'shipping_confirmed': 'yes', 'payment_confirmed': 'yes'}) == {'error': error, 'saved': []}


def test_human_confirmation_only_writes_two_fixed_options(php):
    assert run_setup(php, mode='save', post={'shipping_confirmed': 'yes', 'payment_confirmed': ['yes'],
                                            'blog_public': '1', 'arbitrary': 'value'}) == {
        'saved': {'muse_shipping_confirmed': 'yes', 'muse_payment_confirmed': 'no'}}
