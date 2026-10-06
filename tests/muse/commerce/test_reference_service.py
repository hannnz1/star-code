import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_reference_runner import inputs


class Runner:
    def __init__(self, jobs, job):
        self.jobs, self.job, self.calls = jobs, job, []
    async def prepare(self, job, bundle):
        self.calls.append('prepare')
        self.jobs.begin(job.id, expected_revision=job.revision)
    async def bootstrap(self, job, bundle, **kwargs):
        self.calls.append(('bootstrap', kwargs))
        raise TimeoutError()
    async def verify(self, job, bundle):
        self.calls.append('verify')
        return {'site_ready': False}
    async def recover(self, job):
        self.calls.append('recover')
        return {'site_ready': False}
    async def cleanup(self, job):
        self.calls.append('cleanup')
        return self.jobs.begin_cleanup(job.id, job.revision)


async def test_service_provision_timeout_never_relaunches_on_repeat(workflow, tmp_path):
    from muse.commerce_connector.reference_service import ReferenceEnvironmentService
    jobs, job, bundle, _ = inputs(workflow, tmp_path)
    runner = Runner(jobs, job)
    service = ReferenceEnvironmentService(jobs, runner, bundle, ports=(63660, 63661))
    with pytest.raises(CommerceFailure): await service.execute(job.project_id, job.id, job.revision, 'provision')
    current = jobs.read(job.project_id, job.id)
    assert current.state == 'UNKNOWN'
    with pytest.raises(CommerceFailure): await service.execute(job.project_id, job.id, current.revision, 'provision')
    assert len(runner.calls) == 2
    await service.execute(job.project_id, job.id, current.revision, 'recover')
    assert runner.calls[-1] == 'recover'


def test_service_reserve_ports_are_host_fixed_and_idempotent(workflow, tmp_path):
    from muse.commerce_connector.reference_service import ReferenceEnvironmentService
    jobs, job, bundle, _ = inputs(workflow, tmp_path)
    service = ReferenceEnvironmentService(jobs, Runner(jobs, job), bundle, ports=(63660, 63661))
    project = jobs.repo.get_project(job.project_id)
    reserved = service.reserve(project.id, project.revision, 'second')
    assert reserved.port == 63661
    assert service.reserve(project.id, project.revision, 'second') == reserved
    with pytest.raises(CommerceFailure): service.reserve(project.id, project.revision, 'third')


@pytest.mark.parametrize('identity', ['live', 'ref-' + 'f' * 32, '../connection.json'])
def test_registry_never_resolves_unready_or_arbitrary_connections(workflow, tmp_path, identity):
    from muse.commerce_connector.reference_service import ReferenceEnvironmentService
    jobs, job, bundle, _ = inputs(workflow, tmp_path)
    service = ReferenceEnvironmentService(jobs, Runner(jobs, job), bundle, ports=(63660,))
    with pytest.raises(CommerceFailure): service.resolve_connection(identity, job.project_id)
    with pytest.raises(CommerceFailure): service.resolve_connection('ref-' + job.id, job.project_id)


async def test_service_stale_revision_or_unknown_action_never_calls_runner(workflow, tmp_path):
    from muse.commerce_connector.reference_service import ReferenceEnvironmentService
    jobs, job, bundle, _ = inputs(workflow, tmp_path)
    runner = Runner(jobs, job)
    service = ReferenceEnvironmentService(jobs, runner, bundle, ports=(63660,))
    for revision, action in ((job.revision + 1, 'provision'), (job.revision, 'shell')):
        with pytest.raises(CommerceFailure): await service.execute(job.project_id, job.id, revision, action)
    assert runner.calls == []

def test_cleanup_detaches_owned_reference_and_invalidates_project_context(workflow, tmp_path):
    from muse.commerce.models import EnvironmentRef
    jobs, job, _, _ = inputs(workflow, tmp_path)
    project = jobs.repo.get_project(job.project_id)
    reference = EnvironmentRef(id='ref-' + job.id, connector_ref='ref-' + job.id, project_id=project.id,
        environment='staging', public_url='http://127.0.0.1:' + str(job.port))
    bound = jobs.repo.attach_connection(project.id, reference, 'cleanup-bind', project.revision)
    started = jobs.begin_cleanup(job.id, job.revision)
    updated = jobs.repo.get_project(project.id)
    assert started.state == 'CLEANUP_UNKNOWN'
    assert updated.revision == bound.revision + 1
    assert all(ref.connector_ref != reference.id for ref in updated.environment_refs)
