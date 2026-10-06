"""Opt-in actual Store API against a disposable Windows CMS, not Docker evidence."""
import re
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ProductDraft
from muse.commerce_connector.wordpress import WordPressReader
from tests.muse.commerce.test_buyer_sender import setup
from tests.muse.commerce.test_wordpress_live_fixture import (  # noqa: F401
    fixture_action,
    local_store,
)


async def test_real_store_api_signed_checkout_and_independent_readback(workflow, tmp_path, monkeypatch, local_store):  # noqa: F811
    connection, private = local_store
    fixture_action({'action': 'offline_checkout'})
    sku = 'BUYER-API-' + uuid.uuid4().hex
    created = fixture_action({'action': 'buyer_probe_fixture', 'sku': sku})
    root = Path(__file__).resolve().parents[3]
    mu = root / 'work/tools/wordpress/wordpress/wp-content/mu-plugins'
    guard = mu / 'muse-staging-safety.php'
    constants = mu / '000-muse-buyer-fixture.php'
    if guard.exists() or constants.exists():
        raise RuntimeError('Refuse replacing existing disposable guard configuration')
    sender, probes, plan, job, _, _ = setup(workflow, tmp_path, monkeypatch)
    sender.transport = None
    monkeypatch.setattr(sender, '_target', lambda project_id, job_id: (job, connection))
    monkeypatch.setattr(sender.runner, '_read_private', lambda *args: {'execution_secret': private['signing_secret']})
    intent = SimpleNamespace(project_id=plan.project_id, plan_id=plan.id, source_digest='b' * 64, digest='c' * 64,
        target=SimpleNamespace(connector_ref=connection.connection_id),
        products=[ProductDraft(sku=sku, title='Disposable buyer probe', price='12.50', currency='USD', stock=3)])
    # Actual CMS/Store API, but host/source attestation remains an explicit fake.
    monkeypatch.setattr(sender.sources, '_verification_source', lambda *args, **kwargs:
        (intent, [SimpleNamespace(snapshot=SimpleNamespace(products=[{'id': created['id'], 'sku': sku}]))]))
    diagnostics = []
    original_client = httpx.AsyncClient
    async def inspect_response(response):
        await response.aread()
        code = ''
        try:
            value = response.json()
            candidate = value.get('code', '') if isinstance(value, dict) else ''
            if isinstance(candidate, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', candidate): code = candidate
        except ValueError: pass
        diagnostics.append((response.request.method, response.request.url.path, response.status_code, code))
    monkeypatch.setattr('muse.commerce.buyer_sender.httpx.AsyncClient', lambda *args, **kwargs:
        original_client(*args, **kwargs, event_hooks={'response': [inspect_response]}))
    try:
        constants.write_text("<?php\ndefine('MUSE_REFERENCE_JOB', '" + job.id + "');\n", encoding='utf-8')
        shutil.copyfile(root / 'src/muse/commerce/assets/reference/staging-safety.php', guard)
        try:
            saved = await sender.send(plan.project_id, plan.id, job.id, 'unit-grant-not-real-linux', sku)
        except CommerceFailure as error:
            diagnostics.append(('fixed-error', error.public.code))
            raise AssertionError('Actual CMS HTTP status/code diagnostics: ' + repr(diagnostics)) from None
        assert saved.source.product_id == created['id'] and saved.receipt.status == 'on-hold'
        snapshot = await WordPressReader(connection).read('snapshot', remaining_seconds=20)
        products = [item for item in snapshot['products'] if item.get('sku') == sku]
        assert len(products) == 1 and products[0]['stock_quantity'] == 3
        assert probes.read(plan.project_id, plan.id, saved.probe_id).buyer_flow_verified is False
        assert await sender.reconcile(plan.project_id, plan.id, saved.probe_id) == saved
        assert not any(key in saved.model_dump_json() for key in ('email', 'address', 'order_key', 'cookie'))
    finally:
        if guard.exists(): guard.unlink()
        if constants.exists(): constants.unlink()
        fixture_action({'action': 'buyer_probe_fixture', 'restore': created['old']})
