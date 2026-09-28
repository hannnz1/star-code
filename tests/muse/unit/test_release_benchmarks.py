import json

import pytest


def test_manifest_is_exclusive_and_rejects_missing_evidence(tmp_path):
    from benchmarks.release_manifest import verify_manifest, write_manifest
    output = tmp_path / 'evidence'
    path = write_manifest(output)
    data = json.loads(path.read_text())
    assert data['files']['src/muse/agent/context.py']
    assert data['planned_attempts'] == 60
    assert data['human_review'] == 'PENDING'
    with pytest.raises(FileExistsError):
        write_manifest(output)
    assert verify_manifest(path)
    data['files']['nonexistent-required-evidence'] = 'bad'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='changed|missing'):
        verify_manifest(path)


def test_release_gate_keeps_missing_and_unreviewed_attempts_in_denominator():
    from benchmarks.release_manifest import acceptance
    rows = [{'case': f'{prefix}{i:02}', 'round': r, 'result': 'AUTO_PASS_REVIEW_REQUIRED'}
            for r in range(1, 4) for prefix in 'RDCBP' for i in range(1, 5)]
    result = acceptance(rows)
    assert result['planned'] == 60
    assert result['release_gate'] == 'NOT_ACCEPTED'
    assert result['pending_human'] == 60
    assert acceptance(rows[:-1])['missing'] == 1
    with pytest.raises(ValueError, match='Duplicate'):
        acceptance(rows + rows[:1])


def test_context_probe_rejects_wrong_types_and_missing_facts():
    from benchmarks.long_context_python import score_answer
    assert score_answer('{"limit": true}', {'limit': 1, 'path': 'src/a.py'}) == {'limit': False, 'path': False}
    assert score_answer('not JSON', {'limit': 1}) == {'limit': False}
    assert score_answer('{"limit": 1}', {'limit': 1}) == {'limit': True}


def test_multi_agent_overlap_requires_actual_running_intervals():
    from benchmarks.multi_agent_python import approve_fixture_action, overlap_seconds
    assert overlap_seconds([(0, 2)], [(3, 4)]) == 0
    assert overlap_seconds([(0, 3)], [(2, 4)]) == 1
    assert approve_fixture_action('verify_command', {'command': 'powershell.exe -NoProfile -File ./verify.ps1'})
    assert not approve_fixture_action('run_command', {'command': 'git status; Remove-Item C:\\data -Recurse'})
    assert not approve_fixture_action('run_command', {'command': 'git push origin HEAD'})
    assert approve_fixture_action('run_command', {'command': 'git add src/stats/Mean.java && git commit -m "Implement mean"'})
    assert not approve_fixture_action('run_command', {'command': 'git add src/stats/Mean.java && git push origin HEAD'})
    assert approve_fixture_action('verify_command', {'command': 'javac -d build src/stats/Mean.java'})
    assert not approve_fixture_action('verify_command', {'command': 'javac -d C:/outside src/stats/Mean.java'})


def test_full_catalog_adapter_keeps_activation_task_local_and_execution_approval(tmp_path):
    from test_agent_loop import ScriptedProvider, runtime

    from benchmarks.mcp_paired_python import FullCatalogRegistry
    from muse.tools.context import ExecutionContext
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    config = tmp_path / 'mcp.yaml'
    config.write_text('mcp_servers:\n  - name: fixture\n    command: synthetic\n')
    ctx = ExecutionContext(worker.settings.model_copy(update={'config_path': config}), repo, task, 'test')
    registry = FullCatalogRegistry(ctx)
    ctx.cp['mcp_catalogs'] = {'fixture': {'fingerprint': registry.mcp.fingerprint('fixture'),
        'tools': {f'lookup_{i}': {'description': '', 'schema': {'type': 'object', 'properties': {f'field_{i}': {'type': 'string'}}}} for i in range(100)}}}
    definitions = registry.definitions()
    call = next(d for d in definitions if d.name == 'mcp_call')
    assert len(call.parameters['oneOf']) == 100
    assert call.risk == 'execute'
    assert 'mcp_active' not in ctx.cp
    from muse.tools.registry import ToolRegistry
    production = next(d for d in ToolRegistry(ctx).definitions() if d.name == 'mcp_call')
    assert 'oneOf' not in production.parameters


def test_paired_mcp_report_requires_each_frozen_case_once_per_mode():
    from benchmarks.mcp_paired_python import paired_report

    cases = ['task-01', 'task-02', 'task-03']
    records = [{'case': case, 'mode': mode, 'passed': True}
               for mode in ('FULL', 'LAZY') for case in cases]
    assert paired_report(records, cases)['planned'] == 6
    assert paired_report(records, cases)['passed']
    assert not paired_report(records[:-1], cases)['passed']
    assert not paired_report(records[:-1] + [records[0]], cases)['passed']
    assert not paired_report(records[:-1] + [{**records[-1], 'passed': False}], cases)['passed']


def test_paired_mcp_mode_order_can_be_reversed_for_counterbalance():
    from benchmarks.mcp_paired_python import mode_sequence

    assert [mode for mode, _ in mode_sequence('FULL_LAZY')] == ['FULL', 'LAZY']
    assert [mode for mode, _ in mode_sequence('LAZY_FULL')] == ['LAZY', 'FULL']


def test_full_catalog_is_available_before_first_model_request(tmp_path):
    from test_agent_loop import ScriptedProvider, runtime

    from benchmarks.mcp_paired_python import FullCatalogRegistry
    from muse.tools.context import ExecutionContext
    repo, task, worker = runtime(tmp_path, ScriptedProvider([]))
    config = tmp_path / 'mcp.yaml'
    config.write_text('mcp_servers:\n  - name: fixture\n    command: synthetic\n')
    ctx = ExecutionContext(worker.settings.model_copy(update={'config_path': config}), repo, task, 'test')
    FullCatalogRegistry.fixture_tools = [
        {'name': f'lookup_{i}', 'description': f'Tool {i}', 'inputSchema': {'type': 'object'}}
        for i in range(100)
    ]
    try:
        registry = FullCatalogRegistry(ctx)
        definitions = registry.definitions()
    finally:
        FullCatalogRegistry.fixture_tools = None
    call = next(definition for definition in definitions if definition.name == 'mcp_call')
    assert len(call.parameters['oneOf']) == 100
    assert len(ctx.cp['mcp_catalogs']['fixture']['tools']) == 100


def test_multi_agent_gate_rejects_idle_children_even_when_parent_verifier_passes():
    from benchmarks.multi_agent_python import contributions_valid
    assert not contributions_valid('base', ['a.py', 'b.py'], [
        {'commit': 'base', 'changed': [], 'reviewed': True, 'integrated': True, 'ancestor': True, 'files_equal': True},
        {'commit': 'base', 'changed': [], 'reviewed': True, 'integrated': True, 'ancestor': True, 'files_equal': True}])
    good = [{'commit': name, 'changed': [name], 'reviewed': True, 'integrated': True, 'ancestor': True, 'files_equal': True}
            for name in ['a.py', 'b.py']]
    assert contributions_valid('base', ['a.py', 'b.py'], good)
    good[1]['integrated'] = False
    assert not contributions_valid('base', ['a.py', 'b.py'], good)


def test_multi_agent_controller_stops_for_child_input_without_treating_it_as_pass():
    from benchmarks.multi_agent_python import (
        approve_fixture_action,
        intervention_required,
    )
    assert intervention_required(['PAUSED', 'WAITING_INPUT', 'SUCCEEDED'])
    assert intervention_required(['RUNNING', 'INTERRUPTED'])
    assert not intervention_required(['PAUSED', 'FAILED', 'RUNNING'])
    assert not intervention_required(['RUNNING', 'SUCCEEDED'])
    assert approve_fixture_action('run_command', {'command': 'javac -d build src/stats/Mean.java'})
    assert not approve_fixture_action('run_command', {'command': 'javac -d C:/outside src/stats/Mean.java'})


def test_integrated_source_comparison_uses_git_content_across_line_endings(tmp_path):
    import subprocess

    from benchmarks.multi_agent_python import integrated_source_equal

    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Fixture'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 'fixture@example.invalid'], cwd=repo, check=True)
    (repo / 'source.txt').write_bytes(b'first\nsecond\n')
    subprocess.run(['git', 'add', 'source.txt'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-qm', 'source'], cwd=repo, check=True)
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    subprocess.run(['git', 'config', 'core.autocrlf', 'true'], cwd=repo, check=True)
    (repo / 'source.txt').write_bytes(b'first\r\nsecond\r\n')
    assert integrated_source_equal(repo, source, ['source.txt'])
    (repo / 'source.txt').write_bytes(b'first\r\nchanged\r\n')
    assert not integrated_source_equal(repo, source, ['source.txt'])


def test_export_uses_the_actual_frozen_manifest(tmp_path):
    from benchmarks.export import export
    source = tmp_path / 'campaign'
    source.mkdir()
    (source / 'manifest.json').write_text(json.dumps({'head': 'candidate-identity',
        'effective_settings': {'model': 'original-config-model'}, 'files': {}}))
    target = tmp_path / 'export'
    export(source, target, 'candidate-identity')
    manifest = json.loads((target / 'run-manifest.json').read_text())
    assert manifest['head'] == 'candidate-identity'
    assert manifest['effective_settings']['model'] == 'original-config-model'
    assert manifest['semantic_reviewer'] is None
