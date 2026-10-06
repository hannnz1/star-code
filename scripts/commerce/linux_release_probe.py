"""Synthetic release probe for a verified, disposable Linux reference job only.

The test grant is not a merchant approval or a production verification report.
Credentials stay in the reference runner's owner-only directory.
"""
import time
import uuid

import httpx

from muse.commerce.context import normalize_snapshot
from muse.commerce.models import (
    CommercePlan,
    EnvironmentRef,
    ProductDraft,
    SiteBrief,
    StoreProject,
)
from muse.commerce.release import prepare_product_release
from muse.commerce.release_steps import CompletedProductStep
from muse.commerce.repository import digest
from muse.commerce.site import build_site_blueprint
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.commerce_connector.publisher import confirm_operation_receipt
from muse.commerce_connector.release_authorization import (
    ProductReleaseAuthority,
    ProductReleaseGrant,
)
from muse.commerce_connector.wordpress import WordPressReader


async def release_probe(runner, job, bundle, ledger_path):
    checked = await runner.verify(job, bundle)
    if not checked['assets_verified'] or checked['safety']['job_id'] != job.id:
        raise ValueError('Disposable reference evidence required')
    connection = runner._connection(job)
    project_id, connection_id = connection.project_id, connection.connection_id
    reader = WordPressReader(connection)
    snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), project_id, 'staging')
    brief = SiteBrief(brand_name='Disposable release acceptance', language='en-US', currency=snapshot.settings['currency'])
    target = EnvironmentRef(id='staging', project_id=project_id, environment='staging',
                            connector_ref=connection_id, public_url=connection.base_url)
    project = StoreProject(id=project_id, workspace_id='disposable', brief=brief, environment_refs=[target])
    suffix = uuid.uuid4().hex
    products = [ProductDraft(sku=f'acceptance-{suffix}-{index}', title=f'Acceptance product {index}',
                            price='12.30', stock=3, currency=brief.currency) for index in range(2)]
    blueprint = build_site_blueprint(brief, snapshot)
    plan = CommercePlan(id='probe-' + suffix, project_id=project_id, kind='launch_products', state='VERIFYING',
        products=products, blueprint=blueprint, snapshot_hash=digest(snapshot), code_revision='c' * 40,
        content_hash=digest({'blueprint': blueprint.model_dump(mode='json'),
                             'products': [p.model_dump(mode='json') for p in products]}))
    proofs = {}
    for product in products:
        proof = await reader.read_sku(product.sku, remaining_seconds=20)
        proofs[proof['resource_key']] = proof
    intent = prepare_product_release(project, plan, target, snapshot, proofs, connection=connection)
    now = time.time()
    grant = ProductReleaseGrant('disposable-' + suffix, intent.digest, project_id, connection_id, 'staging',
        connection.base_url, 'e' * 64, now, now + 300, 'approved')
    authority = ProductReleaseAuthority(runner._read_private(job, 'connection.json')['execution_secret'].encode())
    ledger = OperationLedger(ledger_path)
    ledger.bind_target(project_id, connection_id, 'staging', connection.base_url)
    history = []
    async with httpx.AsyncClient(trust_env=False,
            auth=(connection.username, connection.application_password), timeout=20) as client:
        for index in range(len(intent.steps)):
            token = authority.issue(grant, intent, connection, index, history, snapshot, proofs)
            operation = authority.verify(token, grant, intent, connection, index, history, snapshot, proofs).operation
            ledger.prepare(project_id, connection_id, 'staging', operation)
            local = ledger.begin(project_id, connection_id, 'staging', operation.operation_id)
            body = {'operation': operation.model_dump(mode='json'), 'execution_authorization': token}
            response = await client.post(connection.base_url + '/wp-json/muse/v1/operations', json=body)
            if response.status_code != 200:
                raise ValueError(f'Disposable operation HTTP {response.status_code}')
            receipt = confirm_operation_receipt(ledger, local, response.content)
            if receipt.state != 'SUCCEEDED':
                raise ValueError('Disposable operation rejected')
            repeated = await client.post(connection.base_url + '/wp-json/muse/v1/operations', json=body)
            if repeated.status_code != 200 or repeated.json() != response.json():
                raise ValueError('Idempotent receipt differs')
            snapshot = normalize_snapshot(await reader.read('snapshot', remaining_seconds=20), project_id, 'staging')
            for product in products:
                proof = await reader.read_sku(product.sku, remaining_seconds=20)
                proofs[proof['resource_key']] = proof
            history.append(CompletedProductStep(operation, receipt, snapshot, proofs[intent.steps[index].resource_ref]))
    actual = [p for p in snapshot.products if p['sku'] in {product.sku for product in products}]
    if len(actual) != 2 or not all(p['status'] == 'publish' and p['price'] == '12.30' and p['stock_quantity'] == 3 for p in actual):
        raise ValueError('Published facts differ')
    return {'scope': 'synthetic disposable staging only', 'products_published': 2,
            'receipts_succeeded': len(history), 'duplicate_receipts_equal': True, 'facts_readback_pass': True,
            'merchant_approval_verified': False, 'production_verified': False}
