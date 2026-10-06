import hashlib
from dataclasses import asdict

import pytest
from sqlalchemy import text

from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest, encode
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_code_bridge import developer


@pytest.fixture
def product_review(workflow):
    from muse.commerce.code_bridge import ThemeCodeBridge, load_captured_code
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.models import VerificationReport
    from muse.commerce.release import prepare_product_release
    service, runtime, old, worker = workflow
    root = runtime.get(old.steps[0].task_id)
    runtime.control(root.id, 'cancel', expected_revision=root.revision)
    project = service.repo.get_project(old.project_id)
    context = service.repo.get_context(project.id, 'staging')
    wire = context.snapshot.model_dump(mode='json')
    wire['theme_identity'].update({'effective_templates': [], 'global_styles': {'styles': {}}})
    snapshot = normalize_snapshot(wire, project.id, 'staging')
    service.repo.save_context(project.id, 'stage', snapshot, context.capabilities, project.revision)
    project = service.repo.get_project(project.id)
    imported = service.repo.import_products(project.id,
        'sku,name,price,currency,stock,category,description,image_names\nCUP,Cup,10.00,USD,3,,,\n', 'products', project.revision)
    plan = service.create_workflow(project.id, 'launch_products', 'Prepare Cup', 'products-workflow', project.revision,
                                    import_id=imported.id, max_requests=8)
    bridge = ThemeCodeBridge(developer((service, runtime, plan, worker)))
    bridge.seal(bridge.read('style.css')['draft_hash'])
    plan = service.repo.get_plan(plan.id, project_id=project.id)
    for step in plan.steps:
        step.status = 'SUCCEEDED'
        step.output_hash = digest(['fixture-output', step.id])
    plan = service.repo.save_plan(plan.model_copy(update={'state': 'REVIEW_REQUIRED'}), plan.revision)
    artifact = load_captured_code(service.repo, plan)
    target = project.environment_refs[0]
    key = 'sku:' + hashlib.sha256(b'cup').hexdigest()
    state = {'sku': 'cup', 'exists': False}
    intent = prepare_product_release(project, plan, target, snapshot,
        {key: {'resource_key': key, 'state': state, 'fingerprint': digest(state)}})
    report = VerificationReport(id='fixture-verification', changeset_digest=intent.digest,
        code_revision=plan.code_revision, snapshot_hash=plan.snapshot_hash, passed=True,
        checks=[{'name': name, 'passed': True} for name in ['os_boundary', 'pages', 'layout_desktop', 'layout_mobile',
                'links', 'product_facts', 'buyer_flow', 'media']], evidence_refs=['fixture-evidence'])
    proof = {'report': report.model_dump(mode='json'), 'target': target.model_dump(mode='json'),
             'source_digest': artifact.source_digest, 'package_sha256': artifact.package.package_sha256}
    # Explicit unit fixture for the private trusted-verifier producer contract,
    # not a real OS/browser verification and never a public artifact upload.
    with service.repo.db.transaction() as conn:
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'trusted_product_verification',:digest,:data)"),
            {'id': report.id, 'project': project.id, 'plan': plan.id, 'digest': digest(proof), 'data': encode(proof)})
    connection = WordPressConnection('stage', project.id, 'staging', target.public_url, 'service', 'fixture')
    clock = [1000.0]
    return service.repo, project, plan, intent, report.id, connection, clock


def store(fixture):
    from muse.commerce.release_approval import ProductReleaseApprovalRepository
    repo, _, _, _, _, _, clock = fixture
    return ProductReleaseApprovalRepository(repo, clock=lambda: clock[0])


def approve(fixture):
    _, _, plan, intent, verification_id, connection, _ = fixture
    authority = store(fixture)
    authority.stage_review(intent, verification_id, connection=connection, expected_plan_revision=plan.revision)
    return authority.approve(intent.digest, expected_plan_revision=plan.revision)


def test_v2_root_approval_restart_duplicate_and_phase_advance_preserve_frozen_source(product_review):
    from muse.commerce.release_approval import ProductReleaseApprovalRepository
    from muse.commerce.repository import CommerceRepository
    from muse.tasks.repository import TaskRepository
    repo, project, plan, intent, _, connection, clock = product_review
    grant = approve(product_review)
    assert grant.approved_at == 1000 and grant.expires_at == 2800
    approved = repo.get_plan(plan.id, project_id=project.id)
    assert approved.state == 'APPROVED'
    clock[0] = 1100
    restarted = ProductReleaseApprovalRepository(CommerceRepository(TaskRepository(repo.db.engine.url.database)), clock=lambda: clock[0])
    assert asdict(restarted.approve(intent.digest, expected_plan_revision=plan.revision)) == asdict(grant)
    execution = restarted.load(grant.id, connection)
    assert execution.intent == intent and execution.grant == grant
    publishing = restarted.start(grant.id, connection)
    assert publishing.grant == grant
    assert repo.get_plan(plan.id, project_id=project.id).state == 'PUBLISHING'
    assert restarted.start(grant.id, connection).grant == grant


@pytest.mark.parametrize('change', ['expired', 'revoke', 'cancel', 'source', 'phase', 'revision', 'target', 'report', 'code'])
def test_v2_current_record_rejects_stale_source_cancel_and_replayed_approval(product_review, change):
    repo, project, plan, _, report_id, connection, clock = product_review
    authority = store(product_review)
    grant = approve(product_review)
    current = repo.get_plan(plan.id, project_id=project.id)
    if change == 'expired': clock[0] = grant.expires_at
    elif change == 'revoke': authority.revoke(grant.id, project_id=project.id)
    elif change in {'cancel', 'phase', 'revision', 'source'}:
        newer = current.model_copy(deep=True)
        if change == 'cancel': newer.state = 'CANCELLED'
        elif change == 'phase': newer.state = 'BUILDING'
        elif change == 'source': newer.products[0].title = 'Changed'
        repo.save_plan(newer, current.revision)
    elif change == 'target':
        connection = WordPressConnection('stage', project.id, 'staging', 'https://other.test', 'service', 'fixture')
    elif change == 'report':
        with repo.db.transaction() as conn:
            conn.execute(text('UPDATE commerce_artifacts SET digest=:digest WHERE id=:id'), {'id': report_id, 'digest': 'f' * 64})
    else:
        with repo.db.transaction() as conn:
            conn.execute(text("DELETE FROM commerce_artifacts WHERE plan_id=:plan AND kind='theme_code_draft'"), {'plan': plan.id})
    with pytest.raises(CommerceFailure):
        authority.load(grant.id, connection)


def test_v2_review_requires_private_verifier_and_actual_code_not_report_shape(product_review):
    repo, _, plan, intent, report_id, connection, _ = product_review
    authority = store(product_review)
    with repo.db.transaction() as conn:
        conn.execute(text('DELETE FROM commerce_artifacts WHERE id=:id'), {'id': report_id})
    with pytest.raises(CommerceFailure):
        authority.stage_review(intent, report_id, connection=connection, expected_plan_revision=plan.revision)
    assert not repo.db.rows("SELECT 1 FROM commerce_artifacts WHERE kind='product_release_review'")


def test_concurrent_v2_duplicate_approvals_commit_one_fixed_grant(product_review):
    from concurrent.futures import ThreadPoolExecutor
    repo, _, plan, intent, proof_id, connection, clock = product_review
    authority = store(product_review)
    authority.stage_review(intent, proof_id, connection=connection, expected_plan_revision=plan.revision)
    with ThreadPoolExecutor(max_workers=2) as executor:
        grants = list(executor.map(lambda _: authority.approve(intent.digest, expected_plan_revision=plan.revision), range(2)))
    assert grants[0] == grants[1]
    clock[0] += 100
    assert authority.approve(intent.digest, expected_plan_revision=plan.revision) == grants[0]
    assert len(repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='product_release_grant'")) == 1


@pytest.mark.parametrize('change', ['passed', 'checks', 'target', 'package', 'source', 'snapshot', 'revision'])
def test_corrupt_private_verification_cannot_stage_v2_review(product_review, change):
    import json
    repo, _, plan, intent, proof_id, connection, _ = product_review
    with repo.db.transaction() as conn:
        proof = json.loads(conn.execute(text('SELECT data FROM commerce_artifacts WHERE id=:id'), {'id': proof_id}).scalar())
        if change == 'passed': proof['report']['passed'] = False
        elif change == 'checks': proof['report']['checks'].pop()
        elif change == 'target': proof['target']['public_url'] = 'https://other.test'
        elif change == 'package': proof['package_sha256'] = 'f' * 64
        elif change == 'source': proof['source_digest'] = 'f' * 64
        elif change == 'snapshot': proof['report']['snapshot_hash'] = 'f' * 64
        else: proof['report']['code_revision'] = 'f' * 40
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                     {'id': proof_id, 'data': encode(proof), 'digest': digest(proof)})
    with pytest.raises(CommerceFailure):
        store(product_review).stage_review(intent, proof_id, connection=connection, expected_plan_revision=plan.revision)
    assert not repo.db.rows("SELECT 1 FROM commerce_artifacts WHERE kind='product_release_review'")


def test_root_journal_cannot_extend_independent_grant_lifetime(product_review):
    import json
    repo, _, _, _, _, connection, _ = product_review
    grant = approve(product_review)
    with repo.db.transaction() as conn:
        row = conn.execute(text("SELECT id,data FROM commerce_artifacts WHERE kind='product_release_review'")).mappings().one()
        value = json.loads(row['data'])
        value['grant']['expires_at'] = 2900
        conn.execute(text('UPDATE commerce_artifacts SET data=:data,digest=:digest WHERE id=:id'),
                     {'id': row['id'], 'data': encode(value), 'digest': digest(value)})
    with pytest.raises(CommerceFailure):
        store(product_review).load(grant.id, connection)


@pytest.mark.parametrize('mode', ['approved', 'publishing', 'newer'])
def test_expiry_and_revocation_preserve_inflight_uncertainty_and_newer_plan(product_review, mode):
    repo, project, plan, intent, _, connection, clock = product_review
    authority = store(product_review)
    grant = approve(product_review)
    if mode == 'publishing': authority.start(grant.id, connection)
    if mode == 'newer':
        current = repo.get_plan(plan.id, project_id=project.id)
        newer = repo.save_plan(current.model_copy(update={'state': 'BUILDING'}), current.revision)
    clock[0] = grant.expires_at
    authority.expire_due()
    current = repo.get_plan(plan.id, project_id=project.id)
    if mode == 'newer': assert current == newer
    else: assert current.state == ('REVIEW_REQUIRED' if mode == 'approved' else 'NEEDS_RECONCILIATION')
    with pytest.raises(CommerceFailure): authority.load(grant.id, connection)
    with pytest.raises(CommerceFailure): authority.approve(intent.digest, expected_plan_revision=plan.revision)
    revision = current.revision
    authority.expire_due()
    authority.revoke(grant.id, project_id=project.id)
    assert repo.get_plan(plan.id, project_id=project.id).revision == revision


@pytest.fixture
def journal(product_review, tmp_path):
    from muse.commerce.release_journal import ProductReleaseJournal
    from muse.commerce_connector.operation_ledger import OperationLedger
    repo, _, _, _, _, connection, _ = product_review
    authority = store(product_review)
    grant = approve(product_review)
    ledger = OperationLedger(tmp_path / 'operation-ledger.sqlite')
    ledger.bind_target(connection.project_id, connection.connection_id, connection.environment, connection.base_url)
    return ProductReleaseJournal(authority, ledger), grant, connection, repo.get_context(connection.project_id, 'staging').snapshot


def send_fence(journal, attempt, connection):
    operation = attempt.operation
    journal.ledger.prepare(connection.project_id, connection.connection_id, connection.environment, operation)
    journal.ledger.begin(connection.project_id, connection.connection_id, connection.environment, operation.operation_id)
    journal.mark_sent(attempt.id, connection)


def successful_create(journal, attempt, connection, snapshot):
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.release_steps import CompletedProductStep
    from muse.commerce_connector.operations import operation_digest
    wire = snapshot.model_dump(mode='json')
    wire['products'] = [{'id': 21, 'sku': 'CUP', 'name': 'Cup', 'price': '10.00', 'stock_quantity': 3,
                         'status': 'draft', 'muse_project_id': connection.project_id}]
    after = normalize_snapshot(wire, connection.project_id, 'staging')
    state = {'sku': 'cup', 'exists': True, 'product_id': 21, 'entity_fingerprint': after.resource_fingerprints['product:21']}
    proof = {'resource_key': attempt.operation.resource_key, 'state': state, 'fingerprint': digest(state)}
    receipt = journal.ledger.confirm(connection.project_id, connection.connection_id, connection.environment,
        attempt.operation.operation_id, operation_digest=operation_digest(attempt.operation), succeeded=True, fingerprint=proof['fingerprint'])
    return CompletedProductStep(attempt.operation, receipt, after, proof), {proof['resource_key']: proof}


def absence(intent):
    key = intent.steps[0].resource_ref
    state = {'sku': 'cup', 'exists': False}
    return {key: {'resource_key': key, 'state': state, 'fingerprint': digest(state)}}


def test_release_journal_unknown_restart_returns_same_attempt_without_resending(journal, product_review):
    from muse.commerce.release_journal import ProductReleaseJournal
    service, grant, connection, snapshot = journal
    intent = product_review[3]
    attempt = service.prepare(grant.id, connection, snapshot, absence(intent))
    send_fence(service, attempt, connection)
    restarted = ProductReleaseJournal(store(product_review), service.ledger)
    current = restarted.prepare(grant.id, connection, snapshot, absence(intent))
    assert current.id == attempt.id and current.state == 'NEEDS_RECONCILIATION'
    assert current.operation == attempt.operation
    with pytest.raises(CommerceFailure): restarted.mark_sent(current.id, connection)
    assert len(product_review[0].db.rows("SELECT 1 FROM commerce_artifacts WHERE kind='product_release_attempt'")) == 1


def test_release_journal_records_terminal_result_and_derives_next_id_after_restart(journal, product_review):
    from muse.commerce.release_journal import ProductReleaseJournal
    service, grant, connection, snapshot = journal
    first = service.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    send_fence(service, first, connection)
    outcome, proofs = successful_create(service, first, connection, snapshot)
    recorded = service.record_success(first.id, connection, outcome, proofs)
    assert recorded.state == 'SUCCEEDED'
    assert service.record_success(first.id, connection, outcome, proofs) == recorded
    restarted = ProductReleaseJournal(store(product_review), service.ledger)
    next_step = restarted.prepare(grant.id, connection, outcome.snapshot, proofs)
    assert next_step.index == 1 and next_step.operation.payload == {'product_id': 21}
    assert len(restarted.history(grant.id, connection)) == 1


def test_release_journal_fences_send_and_records_late_success_after_revoke(journal, product_review):
    service, grant, connection, snapshot = journal
    first = service.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    with pytest.raises(CommerceFailure): service.mark_sent(first.id, connection)
    send_fence(service, first, connection)
    outcome, proofs = successful_create(service, first, connection, snapshot)
    service.approvals.revoke(grant.id, project_id=connection.project_id)
    result = service.record_success(first.id, connection, outcome, proofs)
    assert result.state == 'SUCCEEDED'
    assert service.get_attempt(first.id, connection).state == 'SUCCEEDED'
    with pytest.raises(CommerceFailure): service.prepare(grant.id, connection, outcome.snapshot, proofs)
    assert product_review[0].get_plan(product_review[2].id, project_id=connection.project_id).state == 'NEEDS_RECONCILIATION'


def test_release_journal_does_not_accept_forged_terminal_receipt(journal, product_review):
    service, grant, connection, snapshot = journal
    first = service.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    send_fence(service, first, connection)
    outcome, proofs = successful_create(service, first, connection, snapshot)
    outcome.receipt = outcome.receipt.model_copy(update={'fingerprint': 'a' * 64})
    with pytest.raises(CommerceFailure): service.record_success(first.id, connection, outcome, proofs)
    assert service.get_attempt(first.id, connection).state == 'NEEDS_RECONCILIATION'


def test_release_journal_completes_exact_readback_and_consumes_grant(journal, product_review):
    from muse.commerce.context import normalize_snapshot
    from muse.commerce.release_steps import CompletedProductStep
    from muse.commerce_connector.operations import operation_digest
    service, grant, connection, snapshot = journal
    first = service.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    send_fence(service, first, connection)
    created, proofs = successful_create(service, first, connection, snapshot)
    service.record_success(first.id, connection, created, proofs)
    publish = service.prepare(grant.id, connection, created.snapshot, proofs)
    send_fence(service, publish, connection)
    wire = created.snapshot.model_dump(mode='json'); wire['products'][0]['status'] = 'publish'
    after = normalize_snapshot(wire, connection.project_id, 'staging')
    proof = {'resource_key': first.operation.resource_key,
        'state': {**created.proof['state'], 'entity_fingerprint': after.resource_fingerprints['product:21']}}
    proof['fingerprint'] = digest(proof['state'])
    terminal = service.ledger.confirm(connection.project_id, connection.connection_id, connection.environment,
        publish.operation.operation_id, operation_digest=operation_digest(publish.operation), succeeded=True,
        fingerprint=after.resource_fingerprints['product:21'])
    result = service.record_success(publish.id, connection, CompletedProductStep(publish.operation, terminal, after, proof),
                                    {first.operation.resource_key: proof})
    assert result.state == 'SUCCEEDED' and result.effect_verified is True
    assert len(service.history(grant.id, connection)) == 2
    assert product_review[0].get_plan(product_review[2].id, project_id=connection.project_id).state == 'SUCCEEDED'
    with pytest.raises(CommerceFailure): service.approvals.load(grant.id, connection)
    with pytest.raises(CommerceFailure): service.prepare(grant.id, connection, after, {first.operation.resource_key: proof})


@pytest.mark.parametrize('partial', [False, True])
def test_release_journal_records_known_failure_and_stops_pending_steps(journal, product_review, partial):
    from muse.commerce_connector.operations import operation_digest
    service, grant, connection, snapshot = journal
    attempt = service.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    send_fence(service, attempt, connection)
    if partial:
        created, proofs = successful_create(service, attempt, connection, snapshot)
        service.record_success(attempt.id, connection, created, proofs)
        attempt = service.prepare(grant.id, connection, created.snapshot, proofs)
        send_fence(service, attempt, connection)
    service.ledger.confirm(connection.project_id, connection.connection_id, connection.environment,
        attempt.operation.operation_id, operation_digest=operation_digest(attempt.operation), succeeded=False)
    result = service.record_failure(attempt.id, connection)
    assert result.state == 'FAILED'
    assert service.record_failure(attempt.id, connection) == result
    assert product_review[0].get_plan(product_review[2].id, project_id=connection.project_id).state == ('PARTIAL' if partial else 'FAILED')
    with pytest.raises(CommerceFailure): service.approvals.load(grant.id, connection)


def test_unknown_send_cannot_be_marked_as_terminal_failure(journal, product_review):
    service, grant, connection, snapshot = journal
    attempt = service.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    send_fence(service, attempt, connection)
    with pytest.raises(CommerceFailure): service.record_failure(attempt.id, connection)
    assert service.get_attempt(attempt.id, connection).state == 'NEEDS_RECONCILIATION'


def test_known_success_with_invalid_post_effect_is_preserved_but_blocks_release(journal, product_review):
    service, grant, connection, snapshot = journal
    attempt = service.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    send_fence(service, attempt, connection)
    outcome, proofs = successful_create(service, attempt, connection, snapshot)
    outcome.snapshot.products[0]['name'] = 'Merchant edited after receipt'
    outcome.snapshot.resource_fingerprints['product:21'] = digest(outcome.snapshot.products[0])
    result = service.record_success(attempt.id, connection, outcome, proofs)
    assert result.state == 'SUCCEEDED' and result.effect_verified is False
    assert service.get_attempt(attempt.id, connection) == result
    with pytest.raises(CommerceFailure): service.prepare(grant.id, connection, outcome.snapshot, proofs)


@pytest.fixture
def product_publisher(journal, product_review):
    import copy
    import json

    import httpx

    from muse.commerce.context import normalize_snapshot
    from muse.commerce_connector.release_authorization import ProductReleaseAuthority
    from muse.commerce_connector.release_publisher import ProductReleasePublisher
    service, grant, connection, snapshot = journal
    remote = {'snapshot': copy.deepcopy(snapshot.model_dump(mode='json')), 'calls': [], 'receipts': {}, 'lose_reply': False}

    def sku_state(sku):
        normalized = normalize_snapshot(remote['snapshot'], connection.project_id, 'staging')
        canonical = sku.strip().casefold()
        matching = next((p for p in normalized.products if p['sku'].strip().casefold() == canonical), None)
        state = {'sku': canonical, 'exists': matching is not None}
        if matching: state.update({'product_id': matching['id'], 'entity_fingerprint': normalized.resource_fingerprints[f'product:{matching["id"]}']})
        key = 'sku:' + hashlib.sha256(canonical.encode()).hexdigest()
        return {'resource_key': key, 'state': state, 'fingerprint': digest(state)}

    def transport(request):
        remote['calls'].append((request.method, request.url.path))
        if request.url.path.endswith('/capabilities'):
            return httpx.Response(200, json={'wordpress_version': '7.1.2', 'woocommerce_version': '11.1.2',
                'theme_id': 'muse-storefront', 'supported_operations': ['create_product_draft', 'publish_product']})
        if request.url.path.endswith('/snapshot'): return httpx.Response(200, json=remote['snapshot'])
        if request.url.path.endswith('/resources'): return httpx.Response(200, json=sku_state(request.url.params['sku']))
        if '/receipts/' in request.url.path:
            receipt = remote['receipts'].get(request.url.path.rsplit('/', 1)[1])
            return httpx.Response(200 if receipt else 404, json=receipt or {})
        assert request.method == 'POST' and request.url.path.endswith('/operations')
        operation = json.loads(request.content)['operation']
        if operation['kind'] == 'create_product_draft':
            product = operation['payload']['product']
            remote['snapshot']['products'].append({'id': 21, 'sku': product['sku'], 'name': product['title'],
                'price': product['price'], 'stock_quantity': product['stock'], 'status': 'draft', 'muse_project_id': connection.project_id})
            fingerprint = sku_state(product['sku'])['fingerprint']
        else:
            remote['snapshot']['products'][0]['status'] = 'publish'
            fingerprint = normalize_snapshot(remote['snapshot'], connection.project_id, 'staging').resource_fingerprints['product:21']
        receipt = {'project_id': connection.project_id, 'connection_id': connection.connection_id, 'environment': 'staging',
                   'operation_id': operation['operation_id'], 'operation_digest': digest(operation),
                   'resource_key': operation['resource_key'], 'state': 'SUCCEEDED', 'fingerprint': fingerprint}
        remote['receipts'][operation['operation_id']] = receipt
        if remote['lose_reply']: raise httpx.ReadTimeout('fixture private transport failure', request=request)
        return httpx.Response(200, json=receipt)
    lock = {'verified': True, 'wordpress': '7.1.2', 'woocommerce': '11.1.2', 'theme': 'muse-storefront',
            'php': '8.4.26', 'database': '11.4.12',
            'images': {name: name + '@sha256:' + 'a' * 64 for name in ('wordpress', 'database', 'cli')}}
    publisher = ProductReleasePublisher(connection, service, ProductReleaseAuthority(b'x' * 32, clock=lambda: product_review[-1][0]),
        versions_lock=lock, execution_enabled=True, transport=httpx.MockTransport(transport))
    return publisher, remote, grant, connection


@pytest.mark.asyncio
async def test_v2_publisher_runs_private_frozen_steps_and_duplicate_completion_has_no_post(product_publisher, product_review):
    publisher, remote, grant, connection = product_publisher
    first = await publisher.publish_next(grant.id)
    assert first.state == 'SUCCEEDED' and first.index == 0
    second = await publisher.publish_next(grant.id)
    assert second.state == 'SUCCEEDED' and second.index == 1
    assert await publisher.publish_next(grant.id) == second
    assert len([call for call in remote['calls'] if call[0] == 'POST']) == 2
    assert product_review[0].get_plan(product_review[2].id, project_id=connection.project_id).state == 'SUCCEEDED'


@pytest.mark.asyncio
async def test_v2_publisher_lost_response_reconciles_after_expiry_without_second_post(product_publisher, product_review):
    publisher, remote, grant, _connection = product_publisher
    remote['lose_reply'] = True
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    product_review[-1][0] = grant.expires_at
    remote['calls'].clear()
    result = await publisher.publish_next(grant.id)
    assert result.state == 'SUCCEEDED'
    assert all(method == 'GET' for method, _ in remote['calls'])
    assert len(remote['receipts']) == 1
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['disabled', 'lock', 'source'])
async def test_v2_publisher_unavailable_boundary_or_changed_source_sends_nothing(product_publisher, product_review, change):
    publisher, remote, grant, connection = product_publisher
    if change == 'disabled': publisher.execution_enabled = False
    elif change == 'lock': publisher.lock['verified'] = False
    else:
        repo = product_review[0]
        current = repo.get_plan(product_review[2].id, project_id=connection.project_id)
        repo.save_plan(current.model_copy(update={'state': 'CANCELLED'}), current.revision)
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    assert remote['calls'] == []


@pytest.mark.asyncio
async def test_v2_publisher_crash_after_begin_before_journal_mark_is_get_only(product_publisher, product_review):
    publisher, remote, grant, connection = product_publisher
    snapshot = product_review[0].get_context(connection.project_id, 'staging').snapshot
    attempt = publisher.journal.prepare(grant.id, connection, snapshot, absence(product_review[3]))
    publisher.ledger.prepare(connection.project_id, connection.connection_id, connection.environment, attempt.operation)
    publisher.ledger.begin(connection.project_id, connection.connection_id, connection.environment, attempt.operation.operation_id)
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    assert remote['calls'] and all(method == 'GET' and '/receipts/' in path for method, path in remote['calls'])
    assert publisher.journal.get_attempt(attempt.id, connection).state == 'NEEDS_RECONCILIATION'
    assert not remote['receipts']


@pytest.mark.asyncio
async def test_v2_publisher_retargeted_connection_cannot_read_or_resend(product_publisher):
    publisher, remote, grant, connection = product_publisher
    publisher.connection = WordPressConnection(connection.connection_id, connection.project_id, connection.environment,
                                                'https://other.test', 'service', 'fixture')
    with pytest.raises(CommerceFailure) as error: await publisher.publish_next(grant.id)
    assert error.value.public.code == 'RESOURCE_CONFLICT'
    assert not remote['calls']


@pytest.mark.asyncio
async def test_v2_publisher_revocation_after_begin_blocks_post_but_keeps_recovery_fence(product_publisher, monkeypatch):
    publisher, remote, grant, connection = product_publisher
    original = publisher.journal.mark_sent
    def revoke_before_send(identity, configured):
        result = original(identity, configured)
        publisher.approvals.revoke(grant.id, project_id=connection.project_id)
        return result
    monkeypatch.setattr(publisher.journal, 'mark_sent', revoke_before_send)
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    assert not any(method == 'POST' for method, _ in remote['calls'])
    remote['calls'].clear()
    with pytest.raises(CommerceFailure): await publisher.publish_next(grant.id)
    assert all(method == 'GET' and '/receipts/' in path for method, path in remote['calls'])
