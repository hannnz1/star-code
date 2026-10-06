import pytest
from test_agent_loop import ScriptedProvider

from muse.commerce.models import PlatformCapabilities, SiteBrief, StoreSnapshot
from muse.commerce.repository import CommerceRepository
from muse.config import ProviderSettings, load_settings


@pytest.fixture
def workflow(tmp_path):
    from muse.agent.loop import AgentRunner
    from muse.commerce.orchestration import CommerceWorkflowService
    from muse.tasks.repository import TaskRepository
    from muse.tasks.worker import Worker
    settings = load_settings(data_dir=tmp_path / 'state', require_provider=False).model_copy(update={
        'provider': ProviderSettings(base_url='https://example.invalid/v1', model='original-model', api_key='provider-secret')})
    repo = TaskRepository(settings.data_dir / 'state.sqlite3')
    worker = Worker(settings, repo, AgentRunner(ScriptedProvider([])), worker_id='worker')
    space = tmp_path / 'space'
    space.mkdir()
    project = CommerceRepository(repo).create_project(repo.register_workspace(str(space))['id'],
        SiteBrief(brand_name='Cup Store', language='en-US', currency='USD',
                  merchant_supplied_policies={'shipping': 'Ship in 3 days', 'returns': 'Return in 14 days', 'privacy': 'Merchant privacy policy'}), 'project')
    commerce = CommerceRepository(repo)
    from muse.commerce.models import EnvironmentRef
    project = commerce.attach_connection(project.id, EnvironmentRef(id='stage', connector_ref='stage', project_id=project.id,
        environment='staging', public_url='https://shop.test'), 'bind', project.revision)
    commerce.save_context(project.id, 'stage', StoreSnapshot(project_id=project.id, environment='staging',
        settings={'currency': 'USD', 'language': 'en-US', 'shipping_confirmed': True, 'payment_confirmed': True},
        theme_identity={'stylesheet': 'muse-storefront'}),
        PlatformCapabilities(wordpress_version='7.1.2', woocommerce_version='11.1.2', theme_id='muse-storefront', supported_operations=[]), project.revision)
    project = commerce.get_project(project.id)
    service = CommerceWorkflowService(commerce, settings)
    plan = service.create_workflow(project.id, 'build_site', 'Prepare the shop', 'workflow', project.revision, max_requests=8)
    yield service, repo, plan, worker


