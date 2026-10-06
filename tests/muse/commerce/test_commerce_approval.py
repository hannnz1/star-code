import asyncio

import pytest

from muse.commerce.approval import ApprovalRepository
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    ChangeOperation,
    ChangeSet,
    CommercePlan,
    EnvironmentRef,
    SiteBrief,
    VerificationReport,
)
from muse.commerce.repository import CommerceRepository, digest
from muse.commerce_connector.wordpress import WordPressConnection
from muse.tasks.repository import TaskRepository


@pytest.fixture
def review(tmp_path):
    runtime = TaskRepository(tmp_path / 'state.sqlite3')
    root = tmp_path / 'space'; root.mkdir()
    repo = CommerceRepository(runtime)
    project = repo.create_project(runtime.register_workspace(str(root))['id'], SiteBrief(brand_name='Shop', language='en', currency='USD'), 'project')
    ref = EnvironmentRef(id='stage', project_id=project.id, environment='staging', public_url='https://store.example', connector_ref='stage')
    project = repo.attach_connection(project.id, ref, 'bind', project.revision)
    plan = repo.save_plan(CommercePlan(id='plan', project_id=project.id, kind='build_site', state='REVIEW_REQUIRED',
                                      snapshot_hash='a'*64, content_hash='c'*64), 0)
    op = ChangeOperation(operation_id='op-1', kind='publish_owned_page', resource_key='page:12', expected_fingerprint='b'*64, payload={'page_id':12})
    changeset = ChangeSet(id='set', plan_id=plan.id, project_id=project.id, environment='staging', operations=[op],
                         resource_preconditions={'page:12':'b'*64}, content_hash=plan.content_hash, digest='')
    changeset.digest = digest(changeset.model_dump(mode='json', exclude={'digest'}))
    report = VerificationReport(id='report', changeset_digest=changeset.digest, code_revision=None, snapshot_hash=plan.snapshot_hash,
                                passed=True, checks=[{'name':'fixture_check','passed':True}], evidence_refs=['fixture-evidence'])
    clock = [1000.0]
    store = ApprovalRepository(repo, clock=lambda:clock[0])
    return repo, project, plan, changeset, report, clock, store


def stage(review):
    _repo, project, plan, changeset, report, _clock, store = review
    store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision, expected_plan_revision=plan.revision)
    return store.approve(changeset.id, changeset.digest, expected_revision=plan.revision)


def test_approval_survives_restart_and_duplicate_does_not_extend_expiry(review):
    repo, project, plan, changeset, _report, clock, _store = review
    grant = stage(review)
    assert grant.expires_at == 2800
    assert repo.get_plan(plan.id, project_id=project.id).state == 'APPROVED'
    clock[0] = 1100
    restarted = ApprovalRepository(CommerceRepository(TaskRepository(repo.db.engine.url.database)), clock=lambda:clock[0])
    assert restarted.approve(changeset.id, changeset.digest, expected_revision=plan.revision) == grant
    connection = WordPressConnection('stage', project.id, 'staging', 'https://store.example', 'service', 'not-real')
    value = asyncio.run(restarted.provider(connection)(grant.id))
    assert value.approval == grant
    assert value.changeset == changeset


@pytest.mark.parametrize('change', ['expired','revoke','brief','plan','cancel','target'])
def test_current_provider_rejects_stale_or_revoked_approval(review, change):
    repo, project, plan, _changeset, _report, clock, store = review
    grant = stage(review)
    connection = WordPressConnection('stage', project.id, 'staging', 'https://store.example', 'service', 'not-real')
    if change == 'expired':
        clock[0] = grant.expires_at
    elif change == 'revoke':
        store.revoke(grant.id, project_id=project.id)
    elif change == 'brief':
        repo.update_brief(project.id, project.brief.model_copy(update={'style':'Changed'}), project.revision)
    elif change in ('plan','cancel'):
        current = repo.get_plan(plan.id, project_id=project.id)
        repo.save_plan(current.model_copy(update={'state':'CANCELLED' if change=='cancel' else 'BUILDING'}), current.revision)
    elif change == 'target':
        connection = WordPressConnection('stage', project.id, 'staging', 'https://other.example', 'service', 'not-real')
    with pytest.raises(CommerceFailure):
        asyncio.run(store.provider(connection)(grant.id))


@pytest.mark.parametrize('invalid', ['digest','report','content','snapshot','code','checks'])
def test_invalid_review_is_not_saved_or_approved(review, invalid):
    repo, project, plan, changeset, report, _clock, store = review
    if invalid == 'digest': changeset.digest='d'*64
    elif invalid == 'report': report.passed=False
    elif invalid == 'content': changeset.content_hash='d'*64
    elif invalid == 'snapshot': report.snapshot_hash='d'*64
    elif invalid == 'code': report.code_revision='d'*40
    elif invalid == 'checks': report.checks=[]
    with pytest.raises(CommerceFailure):
        store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision, expected_plan_revision=plan.revision)
    assert not repo.db.rows('SELECT * FROM commerce_changesets')
    assert not repo.db.rows('SELECT * FROM commerce_approvals')



def test_revoke_updates_plan_status_and_does_not_revive_duplicate_approval(review):
    repo, project, plan, changeset, _report, _clock, store = review
    grant = stage(review)
    store.revoke(grant.id, project_id=project.id)
    current = repo.get_plan(plan.id, project_id=project.id)
    assert current.state == 'REVIEW_REQUIRED'
    revision = current.revision
    store.revoke(grant.id, project_id=project.id)
    assert repo.get_plan(plan.id, project_id=project.id).revision == revision
    with pytest.raises(CommerceFailure):
        store.approve(changeset.id, changeset.digest, expected_revision=plan.revision)


def test_corrupted_stored_report_cannot_create_initial_approval(review):
    import json

    from sqlalchemy import text
    repo, project, plan, changeset, report, _clock, store = review
    store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision, expected_plan_revision=plan.revision)
    with repo.db.transaction() as conn:
        value = json.loads(conn.execute(text('SELECT verification FROM commerce_changesets WHERE id=:id'), {'id':changeset.id}).scalar())
        value['report']['passed'] = False
        conn.execute(text('UPDATE commerce_changesets SET verification=:data WHERE id=:id'), {'id':changeset.id,'data':json.dumps(value)})
    with pytest.raises(CommerceFailure):
        store.approve(changeset.id, changeset.digest, expected_revision=plan.revision)
    assert not repo.db.rows('SELECT * FROM commerce_approvals')
    assert repo.get_plan(plan.id, project_id=project.id).state == 'REVIEW_REQUIRED'


def test_concurrent_duplicate_approvals_share_one_grant(review):
    from concurrent.futures import ThreadPoolExecutor
    repo, project, plan, changeset, report, _clock, store = review
    store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision, expected_plan_revision=plan.revision)
    def approve(_):
        return store.approve(changeset.id, changeset.digest, expected_revision=plan.revision)
    with ThreadPoolExecutor(max_workers=2) as executor:
        grants = list(executor.map(approve, [1,2]))
    assert grants[0] == grants[1]
    assert len(repo.db.rows('SELECT * FROM commerce_approvals')) == 1


def test_expiry_column_cannot_extend_stored_grant_lifetime(review):
    from sqlalchemy import text
    repo, project, _plan, _changeset, _report, _clock, store = review
    grant = stage(review)
    with repo.db.transaction() as conn:
        conn.execute(text('UPDATE commerce_approvals SET expires_at=9999 WHERE id=:id'), {'id':grant.id})
    connection = WordPressConnection('stage', project.id, 'staging', 'https://store.example', 'service', 'not-real')
    with pytest.raises(CommerceFailure):
        asyncio.run(store.provider(connection)(grant.id))

@pytest.mark.parametrize('bad', ['snapshot','content','code'])
def test_placeholder_provenance_is_not_approvable(review, bad):
    repo, project, plan, changeset, report, _clock, store = review
    modified = plan.model_copy(deep=True)
    if bad == 'snapshot': modified.snapshot_hash = report.snapshot_hash = 'snapshot'
    elif bad == 'content': modified.content_hash = changeset.content_hash = 'content'
    else: modified.code_revision = report.code_revision = 'unknown'
    saved = repo.save_plan(modified, plan.revision)
    changeset.digest = digest(changeset.model_dump(mode='json', exclude={'digest'}))
    report.changeset_digest = changeset.digest
    with pytest.raises(CommerceFailure):
        store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision, expected_plan_revision=saved.revision)


def test_expiry_refresh_restores_review_required_without_overwriting_newer_plan(review):
    repo, project, plan, _changeset, _report, clock, store = review
    grant = stage(review)
    clock[0] = grant.expires_at
    connection = WordPressConnection('stage', project.id, 'staging', 'https://store.example', 'service', 'not-real')
    with pytest.raises(CommerceFailure):
        asyncio.run(store.provider(connection)(grant.id))
    assert repo.get_plan(plan.id, project_id=project.id).state == 'REVIEW_REQUIRED'


@pytest.mark.parametrize('bad', ['package','code','content', None])
def test_theme_package_metadata_must_match_reviewed_source(review, bad):
    import base64

    from muse.commerce.models import StoreSnapshot
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.theme import build_site_archive
    repo, project, plan, changeset, report, _clock, store = review
    blueprint = build_site_blueprint(project.brief, StoreSnapshot(project_id=project.id, environment='staging'))
    metadata, archive = build_site_archive(blueprint, [], code_revision='a'*40)
    saved = repo.save_plan(plan.model_copy(update={'code_revision':'a'*40, 'content_hash':metadata.content_sha256}), plan.revision)
    changeset.content_hash=metadata.content_sha256; changeset.package_hash=metadata.package_sha256
    changeset.operations=[ChangeOperation(operation_id='theme-1',kind='install_theme_package',resource_key='theme:muse-storefront',
                          expected_fingerprint='b'*64, payload={'package':metadata.model_dump(mode='json'), 'archive_base64':base64.b64encode(archive).decode()})]
    changeset.resource_preconditions={'theme:muse-storefront':'b'*64}
    report.code_revision=saved.code_revision
    if bad=='package': changeset.package_hash='d'*64
    elif bad=='code':
        saved=repo.save_plan(saved.model_copy(update={'code_revision':'d'*40}),saved.revision); report.code_revision='d'*40
    elif bad == 'content':
        changeset.content_hash='d'*64; saved=repo.save_plan(saved.model_copy(update={'content_hash':'d'*64}),saved.revision)
    changeset.digest=digest(changeset.model_dump(mode='json',exclude={'digest'})); report.changeset_digest=changeset.digest
    if bad is None:
        store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision, expected_plan_revision=saved.revision)
        grant = store.approve(changeset.id, changeset.digest, expected_revision=saved.revision)
        assert grant.changeset_digest == changeset.digest
        return
    with pytest.raises(CommerceFailure):
        store.stage_review(changeset, report, connection_id='stage', expected_project_revision=project.revision, expected_plan_revision=saved.revision)


@pytest.mark.parametrize('action', ['revoke', 'expire'])
def test_invalidating_approval_preserves_newer_plan(review, action):
    repo, project, plan, _changeset, _report, clock, store = review
    grant = stage(review)
    current = repo.get_plan(plan.id, project_id=project.id)
    newer = repo.save_plan(current.model_copy(update={'state': 'BUILDING'}), current.revision)
    if action == 'revoke':
        store.revoke(grant.id, project_id=project.id)
    else:
        clock[0] = grant.expires_at
        store.expire_due()
    assert repo.get_plan(plan.id, project_id=project.id) == newer


def test_changed_report_evidence_is_rejected_by_current_provider(review):
    import json

    from sqlalchemy import text

    repo, project, _plan, changeset, _report, _clock, store = review
    grant = stage(review)
    with repo.db.transaction() as conn:
        value = json.loads(conn.execute(text('SELECT verification FROM commerce_changesets WHERE id=:id'), {'id': changeset.id}).scalar())
        value['report']['evidence_refs'] = ['different-evidence']
        conn.execute(text('UPDATE commerce_changesets SET verification=:data WHERE id=:id'), {'id': changeset.id, 'data': json.dumps(value)})
    connection = WordPressConnection('stage', project.id, 'staging', 'https://store.example', 'service', 'not-real')
    with pytest.raises(CommerceFailure):
        asyncio.run(store.provider(connection)(grant.id))
