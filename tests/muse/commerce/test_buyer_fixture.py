"""Disposable probe identities remain separate from approved merchant facts."""
import json
import subprocess
from pathlib import Path

import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_php_protocol import php  # noqa: F401


def proof():
    return {'job_id': 'a' * 32, 'project_id': 'project', 'connection_id': 'ref-' + 'a' * 32,
        'product_id': 12, 'sku': 'MUSE-PROBE-' + 'a' * 32, 'title': 'MUSE disposable purchase probe',
        'price': '12.50', 'currency': 'USD', 'stock_quantity': 3, 'status': 'publish',
        'catalog_visibility': 'hidden', 'fixture_only': True}


def test_fixture_is_exact_owned_job_product_and_never_merchant_draft():
    from muse.commerce.buyer_fixture import read_disposable_product
    value = read_disposable_product(proof(), project_id='project', job_id='a' * 32, currency='USD')
    assert value.product_id == 12 and value.draft.stock == 3
    assert value.draft.sku == 'MUSE-PROBE-' + 'a' * 32
    assert value.fixture_only is True


@pytest.mark.parametrize('change', [{'job_id': 'b' * 32}, {'project_id': 'other'}, {'product_id': True},
    {'stock_quantity': 0}, {'stock_quantity': '3'}, {'price': '0'}, {'currency': 'EUR'},
    {'sku': 'MERCHANT'}, {'catalog_visibility': 'visible'}, {'fixture_only': False},
    {'status': 'draft'}, {'passed': True}])
def test_fixture_readback_rejects_retargeting_or_invented_facts(change):
    from muse.commerce.buyer_fixture import read_disposable_product
    with pytest.raises(CommerceFailure):
        read_disposable_product({**proof(), **change}, project_id='project', job_id='a' * 32, currency='USD')


@pytest.mark.parametrize('change', [None, {'duplicate': True}, {'change': 'stock_quantity', 'value': 0},
    {'change': 'catalog_visibility', 'value': 'visible'}, {'change': 'sku', 'value': 'MERCHANT'},
    {'change': 'regular_price', 'value': '0'}, {'change': 'status', 'value': 'draft'}])
def test_actual_php_bootstrap_product_and_read_only_proof(php, change):  # noqa: F811
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([php, '-n', str(root / 'tests/fixtures/commerce/php-disposable-product.php'),
        str(root / 'src/muse/commerce/assets/reference/staging-safety.php')], input=json.dumps(change or {}),
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    if change is None:
        from muse.commerce.buyer_fixture import read_disposable_product
        assert read_disposable_product(value, project_id='project', job_id='a' * 32, currency='USD').product_id == 12
    else:
        assert 'error' in value
