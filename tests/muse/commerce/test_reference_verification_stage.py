"""Fixed stage/service integration with an explicit fake provisioning runner."""
# ruff: noqa: F811
import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.reference_environment import load_reference_assets
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.verification_jobs import PHASES, VerificationJobRepository
from muse.commerce.verification_target import VerificationTargetRepository
from muse.commerce.verification_worker import VerificationWorker
from muse.commerce_connector.reference_service import ReferenceEnvironmentService
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401
from tests.muse.commerce.test_reference_environment import archive, manifest
from tests.muse.commerce.test_staging_source import staging_source_inputs  # noqa: F401


class FixtureRunner:
    """No daemon or CMS; these receipts cannot count as Linux acceptance."""
    def __init__(self, refs, jobs, job, mode):
        self.refs, self.jobs, self.job, self.mode, self.calls = refs, jobs, job, mode, []

    async def prepare(self, ref, bundle):
        self.calls.append('prepare')
        self.refs.begin(ref.id, expected_revision=ref.revision)
        if self.mode == 'cancel':
            current = self.jobs.read(self.job.project_id, self.job.id)
            self.jobs.cancel(current.project_id, current.id, current.revision)

    async def bootstrap(self, ref, bundle, **kwargs):
        self.calls.append('bootstrap')
        safety = {'job_id': ref.id, 'environment': 'staging', **dict.fromkeys([
            'email_disabled', 'external_requests_disabled', 'indexing_disabled', 'cron_disabled', 'offline_gateway_only'], True)}
        self.refs.ready(ref.id, ref.revision, {'job_id': ref.id, 'asset_digest': ref.asset_digest,
            'containers': dict.fromkeys(['wordpress', 'database', 'cli'], 'b' * 64),
            'volumes': [ref.resource_names['database_volume'], ref.resource_names['site_volume']],
            'network': ref.resource_names['network'], 'safety': safety})
        if self.mode == 'lost': raise TimeoutError('explicit lost bootstrap reply')

    async def verify(self, ref, bundle, *, _code=None):
        self.calls.append('verify')
        assert ref.state == 'READY'
        if _code is not None:
            from muse.commerce.coding import verify_coding_artifact
            verify_coding_artifact(_code)
            assert _code.project_id == ref.project_id
        return {'site_ready': True}


def setup(inputs, tmp_path, mode=None):
    from muse.commerce.reference_verification_stage import ReferenceVerificationStage
    repo, project, plan, *_ = inputs
    jobs = VerificationJobRepository(repo)
    job = jobs.reserve(project.id, plan.id, plan.revision, 'worker-reference')
    refs = ReferenceJobRepository(repo)
    data = archive(); path = tmp_path / 'woo.zip'; path.write_bytes(data)
    bundle = load_reference_assets(manifest(data), path)
    runner = FixtureRunner(refs, jobs, job, mode)
    service = ReferenceEnvironmentService(refs, runner, bundle, ports=(63669,))
    stage = ReferenceVerificationStage(jobs, service)
    async def unavailable(job): raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
    handlers = dict.fromkeys(PHASES, unavailable); handlers['reference'] = stage
    return jobs, job, runner, stage, VerificationWorker(jobs, handlers)


@pytest.mark.asyncio
async def test_fixed_reference_stage_reserves_owns_provisions_and_accounts_ready(staging_source_inputs, tmp_path):
    jobs, job, runner, _stage, worker = setup(staging_source_inputs, tmp_path)
    saved = await worker.run_step(job.project_id, job.id)
    assert saved.state == 'QUEUED' and len(saved.completed) == 1
    assert runner.calls == ['prepare', 'bootstrap']
    target = VerificationTargetRepository(jobs).target(job.project_id, job.plan_id)
    assert target.public_url == 'http://127.0.0.1:63669'
    assert jobs.repo.get_project(job.project_id) == staging_source_inputs[1]


@pytest.mark.asyncio
async def test_lost_provision_reply_recovers_only_by_readback_without_reinstall(staging_source_inputs, tmp_path):
    jobs, job, runner, stage, worker = setup(staging_source_inputs, tmp_path, 'lost')
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    assert jobs.read(job.project_id, job.id).state == 'NEEDS_RECONCILIATION'
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    saved = await stage.reconcile(job.project_id, job.id)
    assert saved.state == 'QUEUED' and runner.calls == ['prepare', 'bootstrap', 'verify']
    with pytest.raises(CommerceFailure): await stage.reconcile(job.project_id, job.id)
    assert runner.calls.count('bootstrap') == 1


@pytest.mark.asyncio
async def test_cancel_after_resource_creation_stops_before_cms_install(staging_source_inputs, tmp_path):
    jobs, job, runner, _stage, worker = setup(staging_source_inputs, tmp_path, 'cancel')
    with pytest.raises(CommerceFailure): await worker.run_step(job.project_id, job.id)
    assert runner.calls == ['prepare']
    assert jobs.read(job.project_id, job.id).cancel_requested is True
    assert runner.refs.list(job.project_id)[0].state == 'UNKNOWN'


def test_reference_stage_requires_a_real_host_service(staging_source_inputs):
    from muse.commerce.reference_verification_stage import ReferenceVerificationStage
    jobs = VerificationJobRepository(staging_source_inputs[0])
    with pytest.raises(CommerceFailure): ReferenceVerificationStage(jobs, {'passed': True})
