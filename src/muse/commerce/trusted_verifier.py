"""Fixed private report producer. A report is not review or permission to write."""
import asyncio
import hashlib
import math
from dataclasses import dataclass

from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.code_bridge import load_captured_code
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_release import (
    MerchantReleaseIntent,
    prepare_merchant_release,
)
from muse.commerce.models import VerificationReport
from muse.commerce.preview_repository import PreviewRepository
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.repository import digest, encode
from muse.commerce.verification import verify_staging_facts
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce.verification_runtime import VerificationRuntime
from muse.commerce_connector.wordpress import WordPressConnection, WordPressReader

KINDS = frozenset({'verification_job', 'verification_reference', 'verification_reference_owner',
    'reference_job', 'staging_source', 'staging_source_grant', 'staging_release_attempt',
    'buyer_probe', 'buyer_order_readback', 'buyer_price_fact', 'buyer_fixture_binding', 'verification_readback',
    'commerce_preview', 'commerce_preview_frame', 'theme_code_draft', 'product_media'})


def evidence_stamp(conn, project_id):
    # Hash bytes as well as the stored digest; never trust a stale digest column.
    entries = []
    for row in conn.execute(text('SELECT id,kind,data,digest FROM commerce_artifacts '
            'WHERE project_id=:project ORDER BY id'), {'project': project_id}).mappings():
        if row['kind'] in KINDS:
            entries.append([row['id'], row['digest'], hashlib.sha256(row['data'].encode()).hexdigest()])
    return digest(entries)


def validate_provenance(conn, report, intent, *, clock, fresh=True):
    """Approval rechecks generated reports without requiring VERIFYING state."""
    from muse.commerce.release_approval import ProductReleaseApprovalRepository
    key = digest([report.id, 'merchant_verification_provenance'])
    row, proof = ProductReleaseApprovalRepository._read(conn, key, 'merchant_verification_provenance')
    now = clock()
    if (set(proof) != {'job_id', 'job_digest', 'source_binding', 'intent_digest', 'report_digest',
                      'issued_at', 'expires_at', 'evidence_stamp'}
            or row['project_id'] != intent.project_id or row['plan_id'] != intent.plan_id
            or proof['intent_digest'] != intent.digest or proof['report_digest'] != digest(report)
            or proof['evidence_stamp'] != evidence_stamp(conn, intent.project_id)):
        raise CommerceFailure('REVIEW_STALE')
    if (any(type(value) not in (int, float) or not math.isfinite(value)
            for value in (now, proof['issued_at'], proof['expires_at']))
            or (fresh and not proof['issued_at'] <= now < proof['expires_at'])
            or not 0 < proof['expires_at'] - proof['issued_at'] <= 1800):
        raise CommerceFailure('APPROVAL_EXPIRED', 403)
    job = VerificationJobRepository._read(conn, intent.project_id, proof['job_id'])
    if (job.state != 'COLLECTED' or job.cancel_requested or job.plan_id != intent.plan_id
            or digest(job) != proof['job_digest'] or job.source_binding != proof['source_binding']):
        raise CommerceFailure('REVIEW_STALE')


def reviewed_source(conn, jobs, job):
    """Allow frozen diagnostic reads after review, never a fresh stage send."""
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    approvals = MerchantReleaseApprovalRepository(jobs.repo)
    project, plan = ApprovalRepository._source(conn, job.project_id, job.plan_id)
    if (plan.state not in {'REVIEW_REQUIRED', 'APPROVED', 'PUBLISHING', 'SUCCEEDED'}
            or jobs._source_binding(conn, project, plan, job.plan_revision) != job.source_binding):
        raise CommerceFailure('REVIEW_STALE')
    approvals._not_cancelled(conn, plan)
    _, anchor = approvals._read(conn, digest([job.id, 'verification_review_transition']), 'verification_review_transition')
    if set(anchor) != {'job_digest', 'source_binding', 'review_id', 'report_id'}:
        raise CommerceFailure('REVIEW_STALE')
    _, review = approvals._read(conn, anchor['review_id'], approvals.review_kind)
    intent = MerchantReleaseIntent.model_validate(review['intent'])
    _, envelope = approvals._read(conn, anchor['report_id'], approvals.verification_kind)
    report = VerificationReport.model_validate(envelope['report'])
    if (anchor['job_digest'] != digest(job) or anchor['source_binding'] != job.source_binding
            or intent.project_id != job.project_id or intent.plan_id != job.plan_id
            or anchor['review_id'] != approvals._id(approvals.review_kind, intent.digest)
            or review['verification_id'] != report.id or report.id != anchor['report_id']):
        raise CommerceFailure('REVIEW_STALE')
    validate_provenance(conn, report, intent, clock=approvals.clock, fresh=False)
    return anchor, review


@dataclass(frozen=True)
class VerifiedMerchantCandidate:
    intent: MerchantReleaseIntent
    report: VerificationReport


class TrustedMerchantVerifier:
    def __init__(self, runtime, *, transport=None):
        if type(runtime) is not VerificationRuntime:
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self.runtime, self.jobs, self.transport = runtime, runtime.jobs, transport
        self.source = runtime.worker.handlers['source_capture']

    def _current(self, project_id, identity):
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            if (job.state != 'COLLECTED' or job.cancel_requested
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding):
                raise CommerceFailure('REVIEW_STALE')
            return job

    async def collect(self, project_id, identity, *, connection):
        try:
            async with asyncio.timeout(180):
                return await self._collect(project_id, identity, connection)
        except TimeoutError:
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 503) from None

    async def request_review(self, project_id, identity, *, connection):
        from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
        with self.jobs.db.transaction() as conn:
            job = self.jobs._read(conn, project_id, identity)
            _, plan = ApprovalRepository._source(conn, project_id, job.plan_id)
            if plan.state == 'REVIEW_REQUIRED':
                anchor, value = reviewed_source(conn, self.jobs, job)
                approvals = MerchantReleaseApprovalRepository(self.jobs.repo, clock=self.source.clock)
                row, _ = approvals._read(conn, anchor['review_id'], approvals.review_kind)
                intent, _, _, report = approvals._current(conn, row, value, connection)
                return VerifiedMerchantCandidate(intent, report)
        try:
            async with asyncio.timeout(180):
                return await self._collect(project_id, identity, connection, review=True)
        except TimeoutError:
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 503) from None

    async def _collect(self, project_id, identity, connection, *, review=False):
        job = self._current(project_id, identity)
        staging_connection = self.source._connection(job)
        with self.jobs.db.transaction() as conn:
            project, plan = ApprovalRepository._source(conn, project_id, job.plan_id)
            target = next((ref for ref in project.environment_refs if isinstance(connection, WordPressConnection)
                and ref.connector_ref == connection.connection_id and ref.environment == connection.environment
                and ref.public_url == connection.base_url), None)
            if (target is None or connection.project_id != project_id
                    or connection.base_url == staging_connection.base_url
                    or connection.connection_id == staging_connection.connection_id):
                raise CommerceFailure('PERMISSION_DENIED', 403)
            code = load_captured_code(self.jobs.repo, plan, connection=conn)
        grant = self.source.source(project_id, identity, staged=True)
        with self.jobs.db.transaction() as conn:
            staging, history = self.source.sources._verification_source(conn, grant.id, staging_connection, fresh=True)
            _, source_record = self.source.sources._read(conn,
                self.source.sources._id('staging_source', grant.intent_digest), 'staging_source')
        expected = digest([job.source_binding, staging.digest, grant.id,
            [item.receipt.model_dump(mode='json') for item in history]])
        if job.completed[2].evidence_digest != expected:
            raise CommerceFailure('REVIEW_STALE')
        ref_id = staging_connection.connection_id[4:]
        ref = self.source.service.jobs.read(project_id, ref_id)
        await self.source.service.execute(project_id, ref_id, ref.revision, 'verify', _code=code)
        buyer = self.runtime.worker.handlers['buyer']
        probe_id = digest([project_id, job.plan_id, 'buyer_probe', ref_id])
        order = await buyer.sender.reconcile(project_id, job.plan_id, probe_id)
        sku = next((product.sku for product in staging.products if product.stock >= 1), None)
        if sku is None:
            from muse.commerce.buyer_fixture import BuyerFixtureRepository
            with self.jobs.db.transaction() as conn:
                fixture = BuyerFixtureRepository.read(conn, self.jobs, project_id, job.plan_id, ref_id, staging)
            if await buyer.sender.disposable_product(project_id, ref_id, currency=fixture.draft.currency) != fixture:
                raise CommerceFailure('REVIEW_STALE')
            sku = fixture.draft.sku
        if buyer._evidence(job, staging, ref_id, sku, order) != job.completed[3].evidence_digest:
            raise CommerceFailure('REVIEW_STALE')
        with self.jobs.db.transaction() as conn:
            stamp = evidence_stamp(conn, project_id)
        browser = self.runtime.worker.handlers['browser'].evidence(project_id, identity)
        facts = self.runtime.worker.handlers['facts'].evidence(project_id, identity)
        if browser['preview_id'] != facts['preview_id'] or browser['snapshot_hash'] != facts['snapshot_hash']:
            raise CommerceFailure('REVIEW_STALE')

        async def read(reader, method, value=None):
            self._current(project_id, identity)
            if method == 'snapshot': return await reader.read('snapshot', remaining_seconds=20)
            return await getattr(reader, method)(value, remaining_seconds=20)

        reader = WordPressReader(staging_connection, transport=self.transport)
        snapshot = normalize_snapshot(await read(reader, 'snapshot'), project_id, 'staging')
        media = {}
        for image in staging.images:
            proof = await read(reader, 'read_media_sha256', image.image.sha256)
            media[proof['resource_key']] = proof
        fresh_facts = verify_staging_facts(plan, code, snapshot, connection=staging_connection,
            images=staging.images, media_proofs=media)
        if digest(snapshot) != facts['snapshot_hash'] or fresh_facts != facts['facts']:
            raise CommerceFailure('REVIEW_STALE')
        target_reader = WordPressReader(connection, transport=self.transport)
        target_snapshot = normalize_snapshot(await read(target_reader, 'snapshot'), project_id, connection.environment)
        absence = {}
        if plan.kind == 'build_site':
            for page in plan.blueprint.pages:
                if page.kind != 'product':
                    proof = await read(target_reader, 'read_page_slug', page.slug)
                    absence[proof['resource_key']] = proof
        for product in plan.products:
            proof = await read(target_reader, 'read_sku', product.sku)
            absence[proof['resource_key']] = proof
        from muse.commerce.design_resources import publication_images
        target_images = publication_images(plan.kind, plan.blueprint, plan.products, staging.images)
        for image in target_images:
            proof = await read(target_reader, 'read_media_sha256', image.image.sha256)
            absence[proof['resource_key']] = proof
        intent = prepare_merchant_release(project, plan, target, target_snapshot, code, absence,
            target_images, connection=connection)
        with self.jobs.db.transaction() as conn:
            if (self.jobs._read(conn, project_id, identity) != job
                    or self.jobs._source(conn, project_id, job.plan_id, job.plan_revision) != job.source_binding
                    or evidence_stamp(conn, project_id) != stamp):
                raise CommerceFailure('REVIEW_STALE')
            self.source.sources._verification_source(conn, grant.id, staging_connection, fresh=True)
            ref = ReferenceJobRepository._read(conn, project_id, ref_id)
            if ref.state != 'READY': raise CommerceFailure('REVIEW_STALE')
            preview = PreviewRepository(self.jobs.repo)._report(conn, project_id, job.plan_id,
                job.plan_revision, facts['preview_id'])
            self.source.sources._attestation(source_record['source']['attestation'])
            checks = {**preview.checks, 'os_boundary': True, 'buyer_flow': True,
                      'product_facts': fresh_facts['passed'], 'media': fresh_facts['passed']}
            if any(value is not True for value in checks.values()):
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            report = VerificationReport(id='verification-' + digest([job.id, intent.digest, facts]),
                changeset_digest=intent.digest, code_revision=plan.code_revision, snapshot_hash=plan.snapshot_hash,
                passed=True, checks=[{'name': name, 'passed': value} for name, value in sorted(checks.items())],
                evidence_refs=[job.id, ref_id, self.source.sources._id(self.source.sources.grant_kind, grant.id),
                    facts['preview_id'], digest([probe_id, 'buyer_order_readback'])])
            envelope = {'report': report.model_dump(mode='json'), 'target': target.model_dump(mode='json'),
                'source_digest': code.source_digest, 'package_sha256': code.package.package_sha256}
            from muse.commerce.release_approval import (
                ProductReleaseApprovalRepository as Records,
            )
            old = conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': report.id}).first()
            if old:
                _, previous = Records._read(conn, report.id, 'trusted_merchant_verification')
                if previous != envelope: raise CommerceFailure('RESOURCE_CONFLICT')
                validate_provenance(conn, report, intent, clock=self.source.clock)
            else:
                Records._insert(conn, report.id, project_id, job.plan_id, 'trusted_merchant_verification', envelope)
                provenance = {'job_id': job.id, 'job_digest': digest(job), 'source_binding': job.source_binding,
                    'intent_digest': intent.digest, 'report_digest': digest(report),
                    'issued_at': grant.approved_at, 'expires_at': grant.expires_at,
                    'evidence_stamp': stamp}
                Records._insert(conn, digest([report.id, 'merchant_verification_provenance']), project_id,
                    job.plan_id, 'merchant_verification_provenance', provenance)
            if review:
                from muse.commerce.merchant_approval import (
                    MerchantReleaseApprovalRepository,
                )
                saved = plan.model_copy(update={'state': 'REVIEW_REQUIRED', 'error_code': None, 'revision': plan.revision + 1})
                conn.execute(text('UPDATE commerce_plans SET revision=:revision,data=:data WHERE id=:id AND project_id=:project'),
                    {'revision': saved.revision, 'data': encode(saved), 'id': plan.id, 'project': project_id})
                approvals = MerchantReleaseApprovalRepository(self.jobs.repo, clock=self.source.clock)
                approvals._stage_review(conn, intent, report.id, connection, saved.revision)
                Records._insert(conn, digest([job.id, 'verification_review_transition']), project_id,
                    plan.id, 'verification_review_transition', {'job_digest': digest(job),
                    'source_binding': job.source_binding, 'review_id': approvals._id(approvals.review_kind, intent.digest),
                    'report_id': report.id})
                self.jobs.repo.event(conn, project_id, 'verification_review_ready', {'job_id': job.id, 'plan_id': plan.id})
            return VerifiedMerchantCandidate(intent, report)
