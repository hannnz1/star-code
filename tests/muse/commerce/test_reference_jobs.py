import pytest

from muse.commerce.errors import CommerceFailure


def test_reservation_survives_restart_and_unknown_launch_never_requeues(workflow):
    from muse.commerce.reference_jobs import ReferenceJobRepository
    service, _, plan, _ = workflow
    jobs = ReferenceJobRepository(service.repo)
    project = service.repo.get_project(plan.project_id)
    job = jobs.reserve(project.id, project.revision, 'request', 'a' * 64, 63660)
    assert job.state == 'RESERVED'
    assert jobs.reserve(project.id, project.revision, 'request', 'a' * 64, 63660) == job
    started = jobs.begin(job.id, expected_revision=job.revision)
    assert started.state == 'UNKNOWN'
    restarted = ReferenceJobRepository(service.repo)
    assert restarted.reserve(project.id, project.revision, 'request', 'a' * 64, 63660) == started
    with pytest.raises(CommerceFailure): restarted.begin(job.id, expected_revision=started.revision)
    assert restarted.read(project.id, job.id) == started


def test_foreign_scope_changed_inputs_and_occupied_port_fail_before_launch(workflow):
    from muse.commerce.reference_jobs import ReferenceJobRepository
    service, _, plan, _ = workflow
    jobs = ReferenceJobRepository(service.repo)
    project = service.repo.get_project(plan.project_id)
    job = jobs.reserve(project.id, project.revision, 'request', 'a' * 64, 63660)
    for request, asset, port in [('request', 'b' * 64, 63660), ('request', 'a' * 64, 63661), ('other', 'a' * 64, 63660)]:
        with pytest.raises(CommerceFailure): jobs.reserve(project.id, project.revision, request, asset, port)
    with pytest.raises(CommerceFailure): jobs.read('other-project', job.id)
    service.repo.update_brief(project.id, project.brief, project.revision)
    with pytest.raises(CommerceFailure): jobs.begin(job.id, expected_revision=job.revision)


def test_ready_requires_all_owned_runtime_and_safety_evidence_and_cleanup_keeps_unknown(workflow):
    from muse.commerce.reference_jobs import ReferenceJobRepository
    service, _, plan, _ = workflow
    jobs = ReferenceJobRepository(service.repo)
    project = service.repo.get_project(plan.project_id)
    job = jobs.reserve(project.id, project.revision, 'request', 'a' * 64, 63660)
    started = jobs.begin(job.id, expected_revision=job.revision)
    with pytest.raises(CommerceFailure): jobs.ready(job.id, started.revision, {'passed': True})
    failed = jobs.failed(job.id, started.revision, 'EXECUTION_BOUNDARY_UNAVAILABLE')
    assert failed.state == 'BLOCKED'
    cleaning = jobs.begin_cleanup(job.id, failed.revision)
    assert cleaning.state == 'CLEANUP_UNKNOWN'
    with pytest.raises(CommerceFailure): jobs.reserve(project.id, project.revision, 'second', 'a' * 64, 63660)
    complete = jobs.cleaned(job.id, cleaning.revision, absent_names=set(job.resource_names.values()))
    assert complete.state == 'CLEANED'
    next_job = jobs.reserve(project.id, project.revision, 'second', 'a' * 64, 63660)
    assert next_job.id != job.id
