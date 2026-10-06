import base64
import hashlib
import hmac
import json
import subprocess
from pathlib import Path

import pytest

from tests.muse.commerce.test_php_protocol import php  # noqa: F401


def run(executable, *, attack=None):
    source = {'job_id': 'a' * 32, 'probe_id': 'b' * 64, 'source_digest': 'c' * 64,
        'staging_intent_digest': 'd' * 64, 'product_id': 12, 'sku': 'CUP'}
    payload = base64.b64encode(json.dumps(source, separators=(',', ':')).encode()).decode()
    signature = hmac.new(b'unit-private-probe-signing-secret-0000', payload.encode(), hashlib.sha256).hexdigest()
    body = {'x-muse-probe': payload, 'x-muse-probe-signature': signature, 'probe_id': source['probe_id']}
    if attack == 'signature': body['x-muse-probe-signature'] = '0' * 64
    if attack == 'sku': body['sku'] = 'OTHER'
    if attack == 'quantity': body['quantity'] = 2
    if attack == 'fraction': body['quantity'] = 1.5
    if attack == 'lookup': body['probe_id'] = 'e' * 64
    if attack == 'unsigned': body.pop('x-muse-probe')
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([executable, '-n', str(root / 'tests/fixtures/commerce/php-buyer-probe.php'),
        str(root / 'src/muse/commerce/assets/reference/staging-safety.php')], input=json.dumps(body),
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_actual_php_order_readback_is_source_bound_and_contains_no_pii(php):  # noqa: F811
    value = run(php)
    assert value['state'] == 'found' and value['order_id'] == 25 and value['status'] == 'on-hold'
    assert value['source_digest'] == 'c' * 64 and value['product_id'] == 12 and value['sku'] == 'CUP'
    assert not any(name in json.dumps(value) for name in ('email', 'address', 'cookie', 'secret', 'order_key'))


@pytest.mark.parametrize('attack', ['signature', 'sku', 'quantity', 'fraction', 'lookup', 'unsigned'])
def test_bad_or_unsigned_probe_cannot_produce_owned_order_receipt(php, attack):  # noqa: F811
    value = run(php, attack=attack)
    assert value.get('missing') is not True
    assert value.get('state') != 'found'


def test_signed_probe_preserves_preview_inventory_but_ordinary_order_does_not(php):  # noqa: F811
    value = run(php)
    assert value['stock_reduction'] is False
    assert value['ordinary_stock_reduction'] is True
    assert value['forged_stock_reduction'] is True
