from test_memory_maintenance import setup

from muse.memory.maintenance import MemoryMaintenance


def test_memory_consolidation_keeps_latest_duplicate_with_identical_timestamps(tmp_path, monkeypatch):
    repo, ws, settings, service, _ = setup(tmp_path)
    maintenance = MemoryMaintenance(repo, settings)
    with monkeypatch.context() as clock:
        clock.setattr('muse.memory.service.time.time', lambda: 300000.0)
        one = service.upsert(scope='project', workspace_id=ws, title='First note', content='Python 3.12')
        two = service.upsert(scope='project', workspace_id=ws, title='Latest note', content='Python 3.12')
    assert one['updated_at'] == two['updated_at']
    maintenance._consolidate({'workspace_id': ws}, service.for_task(ws), {'groups': [[one['id'], two['id']]]})
    assert [note['id'] for note in service.list()] == [two['id']]
    assert len(service.history(one['id'])) == 2


def test_repeated_memory_id_cannot_supersede_the_only_fact(tmp_path):
    repo, ws, settings, service, _ = setup(tmp_path)
    maintenance = MemoryMaintenance(repo, settings)
    note = service.upsert(scope='project', workspace_id=ws, title='Only note', content='Python 3.12')
    maintenance._consolidate({'workspace_id': ws}, service.for_task(ws), {'groups': [[note['id'], note['id']]]})
    assert [record['id'] for record in service.list()] == [note['id']]


def test_consolidation_preserves_fact_when_keeper_changed_after_snapshot(tmp_path):
    repo, ws, settings, service, _ = setup(tmp_path)
    maintenance = MemoryMaintenance(repo, settings)
    one = service.upsert(scope='project', workspace_id=ws, title='First', content='Python 3.12')
    two = service.upsert(scope='project', workspace_id=ws, title='Latest', content='Python 3.12')
    snapshot = service.for_task(ws)
    service.upsert(scope='project', workspace_id=ws, memory_id=two['id'], title='Latest', content='Python 3.11')
    maintenance._consolidate({'workspace_id': ws}, snapshot, {'groups': [[one['id'], two['id']]]})
    assert {record['content'] for record in service.list()} == {'Python 3.12', 'Python 3.11'}
