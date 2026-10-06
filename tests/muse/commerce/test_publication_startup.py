import pytest

from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_merchant_journal import merchant_review  # noqa: F401


def lock():
    return {'verified': True, 'wordpress': '7.1.2', 'woocommerce': '11.1.2',
        'images': {name: name + '@sha256:' + 'a' * 64 for name in ('wordpress', 'database', 'cli')}}


def test_connector_publication_requires_linux_verified_lock_existing_database_and_exact_secret_registry(tmp_path, monkeypatch):
    from muse.commerce_connector.runtime import create_publication_service
    for condition in ['windows', 'lock', 'database', 'secret']:
        monkeypatch.setattr('muse.commerce_connector.runtime.platform.system', lambda current=condition: 'Windows' if current == 'windows' else 'Linux')
        manifest = lock(); manifest['verified'] = condition != 'lock'
        with pytest.raises(CommerceFailure):
            create_publication_service({}, {'unknown': b'x' * 32} if condition == 'secret' else {},
                runtime_database=tmp_path / 'not-created.sqlite', private_directory=tmp_path,
                versions_lock=manifest)
    assert not (tmp_path / 'not-created.sqlite').exists()
    assert not (tmp_path / 'publication-ledger.sqlite').exists()


def test_private_connector_startup_builds_bound_v4_brokers_and_never_returns_secrets(merchant_review, workflow, tmp_path, monkeypatch):  # noqa: F811
    from muse.commerce_connector.runtime import create_publication_service
    repo, project, plan, _intent, _, connection, clock, _ = merchant_review
    monkeypatch.setattr('muse.commerce_connector.runtime.platform.system', lambda: 'Linux')
    directory = tmp_path / 'connector-private'; directory.mkdir(); directory.chmod(0o700)
    service = create_publication_service({connection.connection_id: connection}, {connection.connection_id: b'x' * 32},
        runtime_database=workflow[3].settings.data_dir / 'state.sqlite3', private_directory=directory,
        versions_lock=lock(), clock=lambda: clock[0])
    publisher = service._publisher(connection)
    assert publisher.connection == connection and publisher.execution_enabled is True
    assert publisher.authority.version == 4
    with pytest.raises(CommerceFailure): service.publisher_for_connection('unknown')
    assert repo.get_plan(plan.id, project_id=project.id).state == 'REVIEW_REQUIRED'
    assert service.approvals.db.rows("SELECT id FROM commerce_artifacts WHERE kind='merchant_release_grant'") == []
    service.approvals.db.engine.dispose()
