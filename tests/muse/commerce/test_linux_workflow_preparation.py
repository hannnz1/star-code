"""Synthetic role seeding must produce genuine receipts, never verifier reports."""
from scripts.commerce.verify_linux_workflow import prepare_roles


def test_linux_acceptance_seed_uses_role_receipts_and_sealed_code(workflow):
    service, tasks, plan, worker = workflow
    result = prepare_roles(service, tasks, worker.settings, plan)
    assert result.state == 'BLOCKED' and result.error_code == 'VERIFICATION_UNAVAILABLE'
    assert result.code_revision and all(step.status == 'SUCCEEDED' and step.output_hash for step in result.steps)
    assert all(tasks.get(step.task_id).status == 'SUCCEEDED' for step in result.steps)
    assert len(service.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='commerce_output'")) == 3
    assert not service.repo.db.rows("SELECT id FROM commerce_artifacts WHERE kind='trusted_merchant_verification'")


def test_two_flow_evidence_does_not_report_success_after_only_first_flow():
    from scripts.commerce.verify_linux_workflow import record_flow_progress
    evidence = {'passed': False, 'flows': []}
    record_flow_progress(evidence, {'kind': 'build_site', 'passed': True})
    record_flow_progress(evidence, {'kind': 'launch_products', 'state': 'NEEDS_RECONCILIATION'})
    assert evidence['passed'] is False
    assert evidence['kind'] == 'launch_products'


def test_second_flow_progress_does_not_inherit_first_flow_publication():
    from scripts.commerce.verify_linux_workflow import record_flow_progress
    evidence = {'passed': False, 'flows': [{'kind': 'build_site', 'passed': True}]}
    record_flow_progress(evidence, {'kind': 'build_site', 'completed_steps': 18,
        'total_steps': 18, 'final_facts_pass': True, 'review_checks': {'test': True}})
    record_flow_progress(evidence, {'kind': 'launch_products', 'phases': ['reference']})
    assert evidence['passed'] is False and evidence['flows'][0]['passed'] is True
    assert not any(k in evidence for k in ('completed_steps', 'total_steps', 'final_facts_pass', 'review_checks'))
def test_diagnostic_handler_preserves_evidence_and_reconciliation():
    import asyncio
    from scripts.commerce.verify_linux_workflow import DiagnosticHandler

    class Handler:
        async def __call__(self, job):
            raise ValueError('private credential text')

        def evidence(self, project, identity):
            return {'preview_id': identity}

        async def reconcile(self, project, identity):
            return identity

    failures = []
    wrapped = DiagnosticHandler(Handler(), 'browser', failures.append)
    assert wrapped.evidence('project', 'preview') == {'preview_id': 'preview'}
    assert asyncio.run(wrapped.reconcile('project', 'preview')) == 'preview'
    try:
        asyncio.run(wrapped(None))
    except ValueError:
        pass
    assert failures[0]['phase'] == 'browser'
    assert failures[0]['type'] == 'ValueError'
    assert 'private credential text' not in str(failures)
