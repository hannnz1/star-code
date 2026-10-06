"""Private authorization to materialize frozen source in staging, not publish.

The actual Docker capture is required before a preview grant is persisted.
It leaves the business plan VERIFYING and creates no merchant verification or
approval. Preview source/attempt kinds are independent of live publication.
"""
import base64
import copy
import io
import math
import re
import uuid
import zipfile
from dataclasses import asdict, dataclass

from sqlalchemy import text

from muse.commerce.approval import ApprovalRepository
from muse.commerce.code_bridge import load_captured_code
from muse.commerce.coding import capture_static_tar, verify_coding_artifact
from muse.commerce.errors import CommerceFailure
from muse.commerce.isolation import DockerCodingSession
from muse.commerce.media import MediaRepository
from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
from muse.commerce.merchant_release import (
    prepare_merchant_release,
    validate_merchant_release,
)
from muse.commerce.release import release_source_hash
from muse.commerce.repository import digest
from muse.commerce.theme import ALLOWED_FILES
from muse.commerce.verification_jobs import VerificationJobRepository
from muse.commerce.verification_target import VerificationTargetRepository
from muse.commerce_connector.staging_authorization import StagingReleaseGrant

PROBES = {'uid': 65532, 'capabilities': 0, 'network_blocked': True, 'root_blocked': True,
    'docker_socket_absent': True, 'secrets_absent': True}


def prepare_staging_source(project, plan, target, snapshot, code, absence_proofs, images, *, connection=None):
    if target.environment != 'staging' or (connection is not None and connection.environment != 'staging'):
        raise CommerceFailure('PERMISSION_DENIED', 403)
    # A launch is also previewed on an independent complete storefront. Its
    # private preview graph includes pages, while its business source hash and
    # original captured code remain those of the merchant's launch workflow.
    preview_plan = plan.model_copy(deep=True,update={'kind': 'build_site'})
    # Preserve every frozen blueprint field, including the launch marker, so
    # its sealed content hash stays valid. The build graph installs the exact
    # theme; retention applies only to the launch graph on the merchant target.
    intent = prepare_merchant_release(project, preview_plan, target, snapshot, code, absence_proofs, images, connection=connection)
    intent.plan_source_hash = release_source_hash(plan)
    intent.digest = digest(intent.model_dump(mode='json', exclude={'digest'}))
    return validate_merchant_release(intent, connection=connection)


@dataclass(frozen=True)
class AuthorizedStagingSource:
    intent: object
    grant: StagingReleaseGrant


class StagingSourceRepository(MerchantReleaseApprovalRepository):
    review_kind = 'staging_source'
    grant_kind = 'staging_source_grant'
    event_prefix = 'staging_source'
    grant_type = StagingReleaseGrant

    def _source_current(self, conn, intent, connection, expected_revision):
        self.validate_intent(intent, connection=connection)
        project, plan = ApprovalRepository._source(conn, intent.project_id, intent.plan_id)
        self._not_cancelled(conn, plan)
        private_target = VerificationTargetRepository(VerificationJobRepository(self.commerce))._target(conn, project.id, plan.id)
        target_matches = intent.target == private_target if private_target is not None else intent.target in project.environment_refs
        if (connection.environment != 'staging' or intent.workflow != 'build_site' or not target_matches
                or plan.state != 'VERIFYING' or type(expected_revision) is not int or plan.revision != expected_revision
                or project.revision != intent.project_revision or release_source_hash(plan) != intent.plan_source_hash
                or plan.snapshot_hash != intent.snapshot_hash or plan.content_hash != intent.content_hash
                or plan.code_revision != intent.code_revision or not plan.steps
                or any(step.status != 'SUCCEEDED' or not step.output_hash for step in plan.steps)):
            raise CommerceFailure('REVIEW_STALE')
        code = load_captured_code(self.commerce, plan, connection=conn)
        self._check_source_code(intent, code)
        for image in intent.images:
            record, content = MediaRepository._read(conn, intent.project_id, image.media_ref)
            if (base64.b64encode(content).decode('ascii') != image.content_base64
                    or record.image.sha256 != image.image.sha256 or record.image.mime_type != image.image.mime_type
                    or record.image.byte_size != image.image.byte_size or record.width != image.image.width
                    or record.height != image.image.height):
                raise CommerceFailure('REVIEW_STALE')
        return project, plan, code

    @staticmethod
    def _attestation(proof):
        try:
            if (set(proof) != {'container_id', 'image_id', 'image_digest', 'probes'}
                    or not re.fullmatch(r'[a-f0-9]{64}', proof['container_id'])
                    or not re.fullmatch(r'sha256:[a-f0-9]{64}', proof['image_id'])
                    or not re.fullmatch(r'[a-zA-Z0-9._/:-]+@sha256:[a-f0-9]{64}', proof['image_digest'])
                    or set(proof['probes']) != set(PROBES)
                    or any(type(proof['probes'][key]) is not type(value) or proof['probes'][key] != value
                        for key, value in PROBES.items())):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    async def authorize(self, intent, *, connection, expected_plan_revision, boundary):
        if not isinstance(boundary, DockerCodingSession):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        with self.db.transaction() as conn:
            _, _, code = self._source_current(conn, intent, connection, expected_plan_revision)
        verify_coding_artifact(code)
        with zipfile.ZipFile(io.BytesIO(code.archive)) as archive:
            files = {name: archive.read('muse-storefront/' + name) for name in ALLOWED_FILES}
        try:
            await boundary.start(files)
            proof = copy.deepcopy(boundary.attestation)
            self._attestation(proof)
            if boundary.lock.get('verified') is not True or proof['image_digest'] != boundary.lock.get('images', {}).get('coding'):
                raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
            if capture_static_tar(await boundary.capture()) != files:
                raise CommerceFailure('REVIEW_STALE')
        except (ValueError, TypeError, KeyError):
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
        finally:
            await boundary.close()
        with self.db.transaction() as conn:
            project, plan, current_code = self._source_current(conn, intent, connection, expected_plan_revision)
            if current_code != code:
                raise CommerceFailure('REVIEW_STALE')
            now = self.clock()
            if type(now) not in (int, float) or not math.isfinite(now):
                raise CommerceFailure('INPUT_INVALID', 422)
            identity = self._id(self.review_kind, intent.digest)
            if conn.execute(text('SELECT id FROM commerce_artifacts WHERE id=:id'), {'id': identity}).first():
                raise CommerceFailure('RESOURCE_CONFLICT')  # Never refresh a partially applied preview grant.
            source = {'attestation': proof, 'source_digest': code.source_digest, 'package_sha256': code.package.package_sha256}
            grant = self.grant_type('preview-' + uuid.uuid4().hex, intent.digest, project.id, connection.connection_id,
                'staging', connection.base_url, digest(source), now, now + 1800, 'approved')
            value = {'intent': intent.model_dump(mode='json'), 'source_archive': base64.b64encode(code.archive).decode('ascii'),
                'source': source, 'project_hash': digest(project), 'plan_revision': plan.revision, 'phase': 'STAGING',
                'grant': asdict(grant), 'status': 'approved', 'history_count': 0}
            self._insert(conn, identity, project.id, plan.id, self.review_kind, value)
            self._insert(conn, self._id(self.grant_kind, grant.id), project.id, plan.id, self.grant_kind, asdict(grant))
            self.commerce.event(conn, project.id, 'staging_source_authorized', {'plan_id': plan.id, 'source_digest': code.source_digest})
            return grant

    def _load(self, conn, grant_id, connection):
        alias, frozen = self._read(conn, self._id(self.grant_kind, grant_id), self.grant_kind)
        row, value = self._read(conn, self._id(self.review_kind, frozen['intent_digest']), self.review_kind)
        try:
            grant = self.grant_type(**value['grant'])
            intent = self.intent_type.model_validate(value['intent'])
            if (value['status'] != 'approved' or value['phase'] != 'STAGING' or frozen != asdict(grant)
                    or alias['project_id'] != connection.project_id or row['project_id'] != connection.project_id
                    or row['plan_id'] != intent.plan_id or grant.id != grant_id or grant.intent_digest != intent.digest
                    or grant.status != 'approved' or connection.environment != 'staging' or grant.environment != 'staging'
                    or grant.connection_id != connection.connection_id or grant.target_url != connection.base_url
                    or grant.project_id != connection.project_id or digest(value['source']) != grant.verification_hash):
                raise CommerceFailure('APPROVAL_REQUIRED', 403)
            self._attestation(value['source']['attestation'])
            now = self.clock()
            if (any(type(number) not in (int, float) or not math.isfinite(number)
                    for number in (now, grant.approved_at, grant.expires_at))
                    or grant.approved_at > now or not 0 < grant.expires_at - grant.approved_at <= 1800 or now >= grant.expires_at):
                raise CommerceFailure('APPROVAL_EXPIRED', 403)
            project, plan, code = self._source_current(conn, intent, connection, value['plan_revision'])
            if (digest(project) != value['project_hash'] or value['source']['source_digest'] != code.source_digest
                    or value['source']['package_sha256'] != code.package.package_sha256):
                raise CommerceFailure('REVIEW_STALE')
            return AuthorizedStagingSource(intent, grant), row, value, plan
        except (ValueError, KeyError, TypeError):
            raise CommerceFailure('REVIEW_STALE') from None

    def start(self, grant_id, connection):
        return self.load(grant_id, connection)  # Does not set the merchant plan PUBLISHING.

    def verification_source(self, grant_id, connection):
        """Read completed private preview effects without renewing write rights.

        A consumed grant cannot call load/start again. Verification nevertheless
        needs the exact frozen source and every independently verified effect.
        """
        with self.db.transaction() as conn:
            return self._verification_source(conn, grant_id, connection)

    def _verification_source(self, conn, grant_id, connection, *, fresh=False):
        from muse.commerce.staging_journal import StagingReleaseJournal
        journal = StagingReleaseJournal(self, None)
        _, value, intent = journal._parent(conn, grant_id, connection)
        if value['phase'] != 'STAGED' or value['status'] != 'consumed':
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        self._attestation(value['source']['attestation'])
        project, _, code = self._source_current(conn, intent, connection, value['plan_revision'])
        if (digest(project) != value['project_hash'] or value['source']['source_digest'] != code.source_digest
                or value['source']['package_sha256'] != code.package.package_sha256):
            raise CommerceFailure('REVIEW_STALE')
        if fresh:
            now = self.clock()
            grant = value['grant']
            if (any(type(number) not in (int, float) or not math.isfinite(number)
                    for number in (now, grant['approved_at'], grant['expires_at']))
                    or grant['approved_at'] > now or not 0 < grant['expires_at'] - grant['approved_at'] <= 1800
                    or now >= grant['expires_at']):
                raise CommerceFailure('APPROVAL_EXPIRED', 403)
        history = journal._history(conn, grant_id, connection, value)
        if len(history) != len(intent.steps):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        return intent, history

    def approve(self, *args, **kwargs):
        raise CommerceFailure('PERMISSION_DENIED', 403)

    def stage_review(self, *args, **kwargs):
        raise CommerceFailure('PERMISSION_DENIED', 403)

    def expire_due(self):
        # The private _load checks time on every fresh send. Accounting must
        # remain available after expiry, without rewriting the business plan.
        return None

    def revoke(self, grant_id, *, project_id):
        with self.db.transaction() as conn:
            _, grant = self._read(conn, self._id(self.grant_kind, grant_id), self.grant_kind)
            if grant['project_id'] != project_id:
                raise CommerceFailure('NOT_FOUND', 404)
            row, value = self._read(conn, self._id(self.review_kind, grant['intent_digest']), self.review_kind)
            if value['grant'] != grant:
                raise CommerceFailure('REVIEW_STALE')
            value['status'] = 'revoked'
            self._write(conn, row, value)

