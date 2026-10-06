"""Private target ownership contracts; READY fixture is not Linux evidence."""
# ruff: noqa: F811
from dataclasses import replace

import pytest
from sqlalchemy import text

from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.repository import digest
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_preview_repository import capture_fixture
from tests.muse.commerce.test_staging_source import (
    ExplicitFixtureSession,
    staging_source_inputs,  # noqa: F401
)


def setup(inputs):
    from muse.commerce.verification_target import VerificationTargetRepository
    repo, project, plan, *_ = inputs
    jobs = VerificationJobRepository(repo)
    job = jobs.reserve(project.id, plan.id, plan.revision, 'private-preview')
    claimed = jobs.claim(project.id, job.id, job.revision, 'reference')
    refs = ReferenceJobRepository(repo)
    ref = refs.reserve(project.id, project.revision, 'private-ref', 'a' * 64, 63669)
    targets = VerificationTargetRepository(jobs)
    binding = targets.attach(project.id, job.id, claimed.active.token, ref.id)
    return jobs, claimed, refs, ref, targets, binding


def ready(refs, ref):
    started = refs.begin(ref.id, expected_revision=ref.revision)
    safety = {'job_id': ref.id, 'environment': 'staging', **dict.fromkeys([
        'email_disabled', 'external_requests_disabled', 'indexing_disabled', 'cron_disabled', 'offline_gateway_only'], True)}
    return refs.ready(ref.id, started.revision, {'job_id': ref.id, 'asset_digest': ref.asset_digest,
        'containers': dict.fromkeys(['wordpress', 'database', 'cli'], 'b' * 64),
        'volumes': [ref.resource_names['database_volume'], ref.resource_names['site_volume']],
        'network': ref.resource_names['network'], 'safety': safety})


def complete_reference(inputs):
    jobs, job, refs, ref, targets, binding = setup(inputs)
    ref = ready(refs, ref)
    jobs.record(job.project_id, job.id, job.active.token, digest([binding.model_dump(mode='json'), ref.evidence]))
    return jobs, job, refs, ref, targets, binding


def test_private_binding_keeps_project_and_plan_unchanged_and_requires_ready_receipt(staging_source_inputs):
    jobs, job, refs, ref, targets, binding = setup(staging_source_inputs)
    repo, project, plan, *_ = staging_source_inputs
    assert repo.get_project(project.id) == project
    assert repo.get_plan(plan.id, project_id=project.id) == plan
    with pytest.raises(CommerceFailure): targets.target(project.id, plan.id)
    ref = ready(refs, ref)
    with pytest.raises(CommerceFailure): targets.target(project.id, plan.id)
    jobs.record(project.id, job.id, job.active.token, digest([binding.model_dump(mode='json'), ref.evidence]))
    target = targets.target(project.id, plan.id)
    assert target.connector_ref == 'ref-' + ref.id and target.public_url == 'http://127.0.0.1:63669'
    assert target not in project.environment_refs


@pytest.mark.parametrize('change', ['cancel', 'source', 'cleanup', 'binding', 'wrong_receipt'])
def test_private_target_cannot_escape_source_lifecycle_or_integrity(staging_source_inputs, change):
    jobs, job, refs, ref, targets, _binding = complete_reference(staging_source_inputs)
    repo, project, plan, *_ = staging_source_inputs
    if change == 'cancel':
        current = jobs.read(project.id, job.id); jobs.cancel(project.id, job.id, current.revision)
    elif change == 'source': repo.update_brief(project.id, project.brief, project.revision)
    elif change == 'cleanup': refs.begin_cleanup(ref.id, ref.revision)
    elif change == 'wrong_receipt':
        with repo.db.transaction() as conn:
            current = jobs._read(conn, project.id, job.id)
            changed = current.completed[0].model_copy(update={'evidence_digest': 'e' * 64})
            jobs._write(conn, current, completed=[changed])
    else:
        with repo.db.transaction() as conn:
            conn.execute(text('UPDATE commerce_artifacts SET digest=:bad WHERE project_id=:project AND kind=:kind'),
                {'bad': 'f' * 64, 'project': project.id, 'kind': 'verification_reference'})
    with pytest.raises(CommerceFailure): targets.target(project.id, plan.id)


def test_binding_refuses_ready_existing_project_targets_and_wrong_claim(staging_source_inputs):
    _jobs, job, refs, ref, targets, _ = setup(staging_source_inputs)
    with pytest.raises(CommerceFailure): targets.attach(job.project_id, job.id, '0' * 32, ref.id)
    other = refs.reserve(job.project_id, ref.project_revision, 'second-ref', 'a' * 64, 63670)
    with pytest.raises(CommerceFailure): targets.attach(job.project_id, job.id, job.active.token, other.id)
    with pytest.raises(CommerceFailure): targets.target('other-project', job.plan_id)


@pytest.mark.asyncio
async def test_private_target_authorizes_staging_source_and_saves_scoped_preview(staging_source_inputs, tmp_path):
    from muse.commerce.preview_repository import PreviewRepository
    from muse.commerce.staging_source import StagingSourceRepository
    _jobs, _job, _refs, _ref, targets, _binding = complete_reference(staging_source_inputs)
    repo, project, plan, original, old_connection, clock, proofs = staging_source_inputs
    target = targets.target(project.id, plan.id)
    connection = WordPressConnection(target.connector_ref, project.id, 'staging', target.public_url, 'service', 'fixture', approved_development_http=True)
    intent = targets.prepare_source(project.id, plan.id, original.initial_snapshot, proofs, original.images, connection=connection)
    assert intent.target == target and intent.plan_source_hash == original.plan_source_hash
    source = StagingSourceRepository(repo, clock=lambda: clock[0])
    grant = await source.authorize(intent, connection=connection, expected_plan_revision=plan.revision,
        boundary=ExplicitFixtureSession(tmp_path / 'boundary'))
    assert source.load(grant.id, connection).intent == intent
    capture = capture_fixture((repo, project, plan, original, 'unused', old_connection, clock))
    with pytest.raises(CommerceFailure): PreviewRepository(repo).save(project.id, plan.id, plan.revision, capture)
    capture = replace(capture, connection_id=connection.connection_id, target_url=connection.base_url)
    saved = PreviewRepository(repo).save(project.id, plan.id, plan.revision, capture)
    assert PreviewRepository(repo).latest(project.id, plan.id, plan.revision) == saved
    assert repo.get_project(project.id) == project
    assert load_captured_code(repo, plan).package.code_revision == plan.code_revision
    assert repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'") == []


@pytest.mark.asyncio
async def test_new_private_target_runs_the_complete_staging_journal(staging_source_inputs, tmp_path):
    from types import SimpleNamespace

    from tests.muse.commerce.test_release_approval import send_fence
    from tests.muse.commerce.test_site_release_steps import outcome
    from tests.muse.commerce.test_staging_journal import prepare
    _jobs, _job, refs, ref, targets, _binding = complete_reference(staging_source_inputs)
    repo, project, plan, original, _old_connection, clock, proofs = staging_source_inputs
    target = targets.target(project.id, plan.id)
    connection = WordPressConnection(target.connector_ref, project.id, 'staging', target.public_url,
        'service', 'fixture', approved_development_http=True)
    intent = targets.prepare_source(project.id, plan.id, original.initial_snapshot, proofs, original.images, connection=connection)
    journal, grant = await prepare((repo, project, plan, intent, connection, clock, proofs), tmp_path)
    snapshot, code = intent.initial_snapshot, journal.approvals.frozen_code(intent)
    for index in range(len(intent.steps)):
        attempt = journal.prepare(grant.id, connection, snapshot, proofs)
        assert attempt.index == index
        send_fence(journal, attempt, connection)
        done, snapshot = outcome(intent, connection, code, SimpleNamespace(operation=attempt.operation), snapshot, proofs)
        journal.ledger.confirm(project.id, connection.connection_id, connection.environment, attempt.operation.operation_id,
            operation_digest=done.receipt.operation_digest, succeeded=True, fingerprint=done.receipt.fingerprint)
        assert journal.record_success(attempt.id, connection, done, proofs).effect_verified
    frozen, history = journal.approvals.verification_source(grant.id, connection)
    assert frozen == intent and len(history) == 18
    assert repo.get_project(project.id) == project
    assert repo.get_plan(plan.id, project_id=project.id) == plan
    refs.begin_cleanup(ref.id, ref.revision)
    with pytest.raises(CommerceFailure): journal.approvals.verification_source(grant.id, connection)


def test_unbound_new_target_does_not_gain_permission_from_a_forged_copy(staging_source_inputs):
    from muse.commerce.staging_source import StagingSourceRepository
    repo, project, plan, original, _connection, clock, _proofs = staging_source_inputs
    forged = original.model_copy(deep=True)
    forged.target.connector_ref = 'ref-' + 'a' * 32
    forged.target.public_url = 'http://127.0.0.1:63669'
    forged.digest = digest(forged.model_dump(mode='json', exclude={'digest'}))
    connection = WordPressConnection(forged.target.connector_ref, project.id, 'staging', forged.target.public_url, 'service', 'fixture', approved_development_http=True)
    with repo.db.transaction() as conn, pytest.raises(CommerceFailure):
        StagingSourceRepository(repo, clock=lambda: clock[0])._source_current(conn, forged, connection, plan.revision)
