import hashlib
import json

import httpx
import pytest

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    ApprovalGrant,
    ChangeOperation,
    ChangeSet,
    VerificationReport,
)
from muse.commerce.repository import digest
from muse.commerce_connector.authorization import ExecutionAuthority
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.commerce_connector.operations import operation_digest
from muse.commerce_connector.publisher import ApprovedExecution, WordPressPublisher
from muse.commerce_connector.wordpress import WordPressConnection


@pytest.mark.asyncio
@pytest.mark.parametrize('exists', [False, True])
async def test_product_publisher_checks_explicit_sku_state_before_sending(setup, exists):
    connection, snapshot, _, context, authority, _, lock, ledger = setup
    sku = 'Fixture-cup'
    absent = {'sku': sku.casefold(), 'exists': False}
    resource = 'sku:' + hashlib.sha256(sku.casefold().encode()).hexdigest()
    operation = ChangeOperation(operation_id='new-product', kind='create_product_draft', resource_key=resource,
        expected_fingerprint=digest(absent), payload={'product': {'sku': sku, 'title': 'Cup', 'price': '19.99',
            'currency': 'USD', 'stock': 2, 'description': '', 'category': '', 'source_facts': {}, 'media_refs': []}})
    context.changeset.operations = [operation]
    context.changeset.resource_preconditions = {resource: digest(absent)}
    context.changeset.digest = digest(context.changeset.model_dump(mode='json', exclude={'digest'}))
    context.verification.changeset_digest = context.changeset.digest
    context.approval.changeset_digest = context.changeset.digest
    context.approval.resource_preconditions = context.changeset.resource_preconditions
    context.approval.verification_hash = digest(context.verification)
    token = authority.issue(context.approval, connection, operation)
    calls = []
    async def lookup(identifier):
        return context
    def remote(request):
        calls.append(request)
        if request.url.path.endswith('capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': ['create_product_draft']})
        if request.url.path.endswith('snapshot'):
            return httpx.Response(200, json=snapshot)
        if request.url.path.endswith('resources'):
            state = dict(absent, exists=True, product_id=99, entity_fingerprint='f' * 64) if exists else absent
            return httpx.Response(200, json={'resource_key': resource, 'fingerprint': digest(state), 'state': state})
        return httpx.Response(200, json={'project_id': 'project', 'connection_id': 'connection', 'environment': 'staging',
            'operation_id': operation.operation_id, 'operation_digest': operation_digest(operation), 'resource_key': resource,
            'state': 'SUCCEEDED', 'fingerprint': 'f' * 64})
    publisher = WordPressPublisher(connection, ledger, authority, approval_lookup=lookup, versions_lock=lock,
                                    execution_enabled=True, transport=httpx.MockTransport(remote))
    if exists:
        with pytest.raises(CommerceFailure) as error:
            await publisher.publish('grant', token, operation)
        assert error.value.public.code == 'REVIEW_STALE'
    else:
        assert (await publisher.publish('grant', token, operation)).state == 'SUCCEEDED'
    assert len([call for call in calls if call.url.path.endswith('resources')]) == 1
    assert len([call for call in calls if call.method == 'POST']) == (0 if exists else 1)


@pytest.fixture
def setup(tmp_path):
    connection = WordPressConnection('connection', 'project', 'staging', 'https://store.example', 'service', 'private-password')
    snapshot = {'pages': [{'id': 12, 'slug': 'about', 'title': 'About', 'content': 'Old', 'status': 'draft'}],
                'products': [], 'settings': {'currency': 'USD', 'language': 'en'},
                'theme_identity': {'stylesheet': 'muse-storefront', 'effective_templates': [], 'global_styles': {'styles': {}}}}
    fingerprint = normalize_snapshot(snapshot, 'project', 'staging').resource_fingerprints['page:12']
    operation = ChangeOperation(operation_id='op-1', kind='update_owned_page', resource_key='page:12', expected_fingerprint=fingerprint,
                                payload={'page_id': 12, 'title': 'About', 'content': 'New'})
    changeset = ChangeSet(id='set-1', plan_id='plan', project_id='project', environment='staging', operations=[operation],
                         resource_preconditions={'page:12': fingerprint}, content_hash='d' * 64, digest='')
    changeset.digest = digest(changeset.model_dump(mode='json', exclude={'digest'}))
    report = VerificationReport(id='report', changeset_digest=changeset.digest, code_revision=None, snapshot_hash='a'*64, passed=True, checks=[])
    approval = ApprovalGrant(id='grant', changeset_digest=changeset.digest, project_id='project', environment='staging',
                             resource_preconditions=changeset.resource_preconditions, verification_hash=digest(report), expires_at=1900)
    context = ApprovedExecution(approval=approval, changeset=changeset, verification=report)
    authority = ExecutionAuthority(b'k' * 32, clock=lambda: 1000)
    token = authority.issue(approval, connection, operation)
    lock = {'verified': True, 'wordpress': '7.1.2', 'woocommerce': '11.1.2',
            'images': {key: 'example/image@sha256:' + 'a'*64 for key in ('wordpress', 'database', 'cli')}}
    ledger = OperationLedger(tmp_path / 'ledger.sqlite')
    return connection, snapshot, operation, context, authority, token, lock, ledger


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'timeout', '404', 'malformed', 'wrong-receipt', 'compressed', 'oversize'])
async def test_publisher_posts_once_and_never_resends_after_response_loss(setup, outcome):
    connection, snapshot, operation, context, authority, token, lock, ledger = setup
    calls = []
    receipt = {'project_id': 'project', 'connection_id': 'connection', 'environment': 'staging', 'operation_id': 'op-1',
               'operation_digest': operation_digest(operation), 'resource_key': 'page:12', 'state': 'SUCCEEDED', 'fingerprint': 'b'*64}
    async def lookup(identifier):
        assert identifier == 'grant'
        return context
    def remote(request):
        calls.append(request.method)
        if request.url.path.endswith('capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': ['update_owned_page']})
        if request.url.path.endswith('snapshot'):
            return httpx.Response(200, json=snapshot)
        if request.method == 'POST':
            assert request.url.path == '/wp-json/muse/v1/operations'
            assert json.loads(request.content)['operation'] == operation.model_dump(mode='json')
            assert ledger.get('project', 'connection', 'staging', 'op-1').state == 'NEEDS_RECONCILIATION'
            if outcome == 'timeout':
                raise httpx.ReadTimeout('private-password', request=request)
            if outcome == '404':
                return httpx.Response(404)
            if outcome == 'malformed':
                return httpx.Response(200, text='private-password')
            if outcome == 'wrong-receipt':
                return httpx.Response(200, json=dict(receipt, operation_digest='e'*64))
            if outcome == 'compressed':
                return httpx.Response(200, headers={'Content-Encoding': 'gzip'}, content=b'')
            if outcome == 'oversize':
                return httpx.Response(200, content=b'x'*16385)
        return httpx.Response(200, json=receipt)
    publisher = WordPressPublisher(connection, ledger, authority, approval_lookup=lookup, versions_lock=lock,
                                    execution_enabled=True, transport=httpx.MockTransport(remote))
    if outcome == 'success':
        assert (await publisher.publish('grant', token, operation)).state == 'SUCCEEDED'
    else:
        with pytest.raises(CommerceFailure) as error:
            await publisher.publish('grant', token, operation)
        assert error.value.public.code == 'WRITE_OUTCOME_UNKNOWN'
        assert 'private-password' not in str(error.value)
        assert ledger.get('project', 'connection', 'staging', 'op-1').state == 'NEEDS_RECONCILIATION'
    # Repeated publish may retrieve a terminal receipt; it MUST never POST again.
    assert (await publisher.publish('grant', token, operation)).state == 'SUCCEEDED'
    assert calls.count('POST') == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('block', ['disabled', 'lock', 'revoked', 'changed-resource', 'membership', 'report', 'revoked-during-read'])
async def test_preflight_failure_never_sends_post(setup, block):
    connection, snapshot, operation, context, authority, token, lock, ledger = setup
    calls, reads = [], 0
    if block == 'lock':
        lock['verified'] = False
    if block == 'changed-resource':
        snapshot['pages'][0]['content'] = 'Merchant changed it'
    if block == 'membership':
        context.changeset.operations = []
    if block == 'report':
        context.verification.passed = False
    async def lookup(identifier):
        nonlocal reads
        reads += 1
        if block == 'revoked' or (block == 'revoked-during-read' and reads > 1):
            context.approval.status = 'revoked'
        return context
    def remote(request):
        calls.append(request.method)
        if request.url.path.endswith('capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': ['update_owned_page']})
        return httpx.Response(200, json=snapshot)
    publisher = WordPressPublisher(connection, ledger, authority, approval_lookup=lookup, versions_lock=lock,
                                    execution_enabled=block != 'disabled', transport=httpx.MockTransport(remote))
    with pytest.raises(CommerceFailure):
        await publisher.publish('grant', token, operation)
    assert 'POST' not in calls

@pytest.mark.asyncio
async def test_rebound_connection_cannot_reconcile_old_operation_on_new_host(setup):
    connection, snapshot, operation, context, authority, token, lock, ledger = setup
    async def lookup(identifier):
        return context
    calls = []
    def remote(request):
        calls.append(str(request.url))
        if request.url.path.endswith('capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': ['update_owned_page']})
        if request.url.path.endswith('snapshot'):
            return httpx.Response(200, json=snapshot)
        raise httpx.ReadTimeout('private-password', request=request)
    publisher = WordPressPublisher(connection, ledger, authority, approval_lookup=lookup, versions_lock=lock,
                                    execution_enabled=True, transport=httpx.MockTransport(remote))
    with pytest.raises(CommerceFailure):
        await publisher.publish('grant', token, operation)
    calls.clear()
    rebound = WordPressConnection('connection', 'project', 'staging', 'https://another.example', 'service', 'private-password')
    publisher = WordPressPublisher(rebound, ledger, authority, approval_lookup=lookup, versions_lock=lock,
                                    execution_enabled=True, transport=httpx.MockTransport(remote))
    with pytest.raises(CommerceFailure) as error:
        await publisher.publish('grant', token, operation)
    assert error.value.public.code == 'RESOURCE_CONFLICT'
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_at', [1, 2, 3])
async def test_approval_lookup_failure_is_sanitized_before_any_http(setup, failure_at):
    connection, snapshot, operation, context, authority, token, lock, ledger = setup
    count = 0
    async def lookup(identifier):
        nonlocal count
        count += 1
        if count == failure_at:
            raise RuntimeError('private-password internal storage path')
        return context
    calls = []
    def remote(request):
        calls.append(request.method)
        if request.url.path.endswith('capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': ['update_owned_page']})
        return httpx.Response(200, json=snapshot)
    publisher = WordPressPublisher(connection, ledger, authority, approval_lookup=lookup, versions_lock=lock,
                                    execution_enabled=True, transport=httpx.MockTransport(remote))
    with pytest.raises(CommerceFailure) as error:
        await publisher.publish('grant', token, operation)
    assert 'private-password' not in str(error.value)
    assert 'POST' not in calls
    if failure_at == 3:
        assert ledger.get('project', 'connection', 'staging', 'op-1').state == 'NEEDS_RECONCILIATION'

@pytest.mark.asyncio
async def test_changed_approved_dependency_prevents_page_write(setup):
    connection, snapshot, operation, context, authority, token, lock, ledger = setup
    old_settings = normalize_snapshot(snapshot, 'project', 'staging').resource_fingerprints['settings']
    context.changeset.resource_preconditions['settings'] = old_settings
    context.approval.resource_preconditions = dict(context.changeset.resource_preconditions)
    context.changeset.digest = digest(context.changeset.model_dump(mode='json', exclude={'digest'}))
    context.verification.changeset_digest = context.changeset.digest
    context.approval.changeset_digest = context.changeset.digest
    context.approval.verification_hash = digest(context.verification)
    token = authority.issue(context.approval, connection, operation)
    snapshot['settings']['currency'] = 'EUR'
    async def lookup(identifier):
        return context
    calls = []
    def remote(request):
        calls.append(request.method)
        if request.url.path.endswith('capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': ['update_owned_page']})
        return httpx.Response(200, json=snapshot)
    publisher = WordPressPublisher(connection, ledger, authority, approval_lookup=lookup, versions_lock=lock,
                                    execution_enabled=True, transport=httpx.MockTransport(remote))
    with pytest.raises(CommerceFailure):
        await publisher.publish('grant', token, operation)
    assert 'POST' not in calls
