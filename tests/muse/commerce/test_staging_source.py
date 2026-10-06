import io
import tarfile
import zipfile

import pytest

from muse.commerce.code_bridge import load_captured_code
from muse.commerce.errors import CommerceFailure
from muse.commerce.isolation import DockerCodingSession
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401


class ExplicitFixtureSession(DockerCodingSession):
    """Contract fixture only. Its successful probes are NOT Linux evidence."""
    def __init__(self, root, mode='normal'):
        super().__init__(root, {'verified': True, 'images': {'coding': 'python@sha256:' + 'c' * 64}})
        self.mode, self.closed = mode, False

    async def start(self, files):
        self.files = dict(files)
        self.attestation = {'container_id': 'a' * 64, 'image_id': 'sha256:' + 'b' * 64,
            'image_digest': self.lock['images']['coding'], 'probes': {'uid': 65532, 'capabilities': 0,
                'network_blocked': True, 'root_blocked': True, 'docker_socket_absent': True, 'secrets_absent': True}}
        if self.mode == 'probe': self.attestation['probes']['secrets_absent'] = False
        return self.attestation

    async def capture(self):
        files = dict(self.files)
        if self.mode == 'changed': files['style.css'] += b'\nbody{color:red}\n'
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w') as archive:
            for name, content in files.items():
                info = tarfile.TarInfo(name); info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        return output.getvalue()

    async def close(self): self.closed = True; self.attestation = None


@pytest.fixture
def staging_source_inputs(merchant_review):  # noqa: F811
    from sqlalchemy import text
    repo, project, plan, intent, _evidence, connection, clock, proofs = merchant_review
    with repo.db.transaction() as conn:
        conn.execute(text("DELETE FROM commerce_artifacts WHERE kind='trusted_merchant_verification'"))
    plan = repo.save_plan(plan.model_copy(update={'state': 'VERIFYING'}), plan.revision)
    return repo, project, plan, intent, connection, clock, proofs


@pytest.mark.asyncio
async def test_staging_source_authorizes_only_real_capture_path_and_leaves_merchant_plan_verifying(staging_source_inputs, tmp_path):
    from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
    from muse.commerce.staging_source import StagingSourceRepository
    repo, project, plan, intent, connection, clock, _ = staging_source_inputs
    source = StagingSourceRepository(repo, clock=lambda: clock[0])
    boundary = ExplicitFixtureSession(tmp_path / 'boundary')
    grant = await source.authorize(intent, connection=connection, expected_plan_revision=plan.revision, boundary=boundary)
    assert boundary.closed and grant.environment == 'staging'
    assert source.load(grant.id, connection).intent == intent
    assert repo.get_plan(plan.id, project_id=project.id).state == 'VERIFYING'
    with pytest.raises(CommerceFailure): MerchantReleaseApprovalRepository(repo, clock=lambda: clock[0]).load(grant.id, connection)
    clock[0] = grant.expires_at
    with pytest.raises(CommerceFailure): source.load(grant.id, connection)
    assert repo.get_plan(plan.id, project_id=project.id).state == 'VERIFYING'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['probe', 'changed', 'wrong_type', 'stale'])
async def test_staging_source_rejects_bad_boundary_capture_or_changed_plan_without_source_grant(staging_source_inputs, tmp_path, mode):
    from muse.commerce.staging_source import StagingSourceRepository
    repo, project, plan, intent, connection, clock, _ = staging_source_inputs
    boundary = ExplicitFixtureSession(tmp_path / 'boundary', mode)
    if mode == 'wrong_type': boundary = {'os_boundary': True}
    revision = plan.revision + 1 if mode == 'stale' else plan.revision
    with pytest.raises(CommerceFailure):
        await StagingSourceRepository(repo, clock=lambda: clock[0]).authorize(intent, connection=connection,
            expected_plan_revision=revision, boundary=boundary)
    assert repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='staging_source_grant'") == []
    assert repo.get_plan(plan.id, project_id=project.id).state == 'VERIFYING'


@pytest.mark.asyncio
async def test_staging_source_never_uses_stale_merchant_media_after_capture(staging_source_inputs, tmp_path):
    from sqlalchemy import text

    from muse.commerce.staging_source import StagingSourceRepository
    repo, _, plan, intent, connection, clock, _ = staging_source_inputs
    code = load_captured_code(repo, plan)
    with zipfile.ZipFile(io.BytesIO(code.archive)) as archive: assert len(archive.namelist()) == 15
    with repo.db.transaction() as conn:
        conn.execute(text("UPDATE commerce_artifacts SET digest=:sha WHERE id=:id AND kind='product_media'"),
            {'sha': 'f' * 64, 'id': intent.images[0].media_ref})
    with pytest.raises(CommerceFailure):
        await StagingSourceRepository(repo, clock=lambda: clock[0]).authorize(intent, connection=connection,
            expected_plan_revision=plan.revision, boundary=ExplicitFixtureSession(tmp_path / 'boundary'))
