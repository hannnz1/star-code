"""Repeatable local parity checks. Uses fixtures, not paid APIs or a live store."""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = [
    'tests/muse/commerce/test_follow_up_models.py', 'tests/muse/commerce/test_task_automation.py',
    'tests/muse/commerce/test_task_queue.py', 'tests/muse/commerce/test_follow_ups.py',
    'tests/muse/commerce/test_code_disposition.py', 'tests/muse/commerce/test_task_drafts.py',
    'tests/muse/commerce/test_code_integration.py', 'tests/muse/commerce/test_code_bridge.py',
    'tests/muse/commerce/test_board_archives.py', 'tests/muse/commerce/test_commerce_restore.py',
    'tests/muse/commerce/test_commerce_export.py', 'tests/muse/commerce/test_commerce_workflow.py',
    'tests/muse/commerce/test_workflow_api.py', 'tests/muse/commerce/test_commerce_migration.py',
    'tests/muse/commerce/test_generated_commerce_types.py', 'tests/test_state_backup.py',
    'tests/test_durable_delegation.py', 'tests/muse/unit/test_agent_loop.py', 'tests/muse/unit/test_config.py',
]
BROWSER = ['tests/muse/commerce/test_follow_ups_browser.py', 'tests/muse/commerce/test_queue_automation_browser.py',
           'tests/muse/commerce/test_team_browser.py', 'tests/muse/commerce/test_code_integration_browser.py',
           'tests/muse/commerce/test_board_status_browser.py']


def verification_scope(scope):
    if scope == 'task-board':
        return BACKEND, BROWSER
    commerce = sorted(str(path.relative_to(ROOT)).replace('\\', '/')
                      for path in (ROOT / 'tests/muse/commerce').glob('test_*.py'))
    backend = [name for name in commerce if not name.endswith('_browser.py')]
    browser = [name for name in commerce if name.endswith('_browser.py')]
    backend.extend(name for name in BACKEND if not name.startswith('tests/muse/commerce/'))
    return backend, browser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('task-board', 'merchant'), default='task-board',
                        help='merchant covers all commerce backend and browser contracts')
    args = parser.parse_args()
    backend, browser = verification_scope(args.scope)
    stamp = datetime.datetime.now(datetime.UTC).strftime('%Y%m%dT%H%M%SZ')
    evidence = ROOT / 'work' / (args.scope + '-evidence') / stamp
    evidence.mkdir(parents=True)
    node = shutil.which('node') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'nodejs/node.exe')
    commands = [
        ('backend', [sys.executable, '-m', 'pytest', *backend, '-q', '-ra',
            '--basetemp=' + str(evidence / 'tmp-backend'), '--junitxml=' + str(evidence / 'backend.xml')], ROOT),
        ('typescript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], ROOT / 'frontend'),
        ('build', [node, 'node_modules/vite/bin/vite.js', 'build'], ROOT / 'frontend'),
        ('openapi', [sys.executable, '-m', 'muse.openapi_types', '--check'], ROOT),
        ('browser', [sys.executable, '-m', 'pytest', *browser, '-q', '-ra',
            '--basetemp=' + str(evidence / 'tmp-browser'), '--junitxml=' + str(evidence / 'browser.xml')], ROOT),
    ]
    summary = {'created_at_utc': stamp, 'scope': args.scope, 'evidence_kind': 'local fixture regression',
               'paid_api_calls': 0, 'live_store_writes': 0, 'checks': {}, 'tests': {}, 'sha256': {}}
    for name, command, cwd in commands:
        print('Checking ' + name, flush=True)
        with (evidence / (name + '.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=False)
        summary['checks'][name] = {'exit_code': result.returncode, 'command': command}
        (evidence / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        if result.returncode:
            raise SystemExit(f'{name} failed; inspect {evidence / (name + ".log")}')
        if name in {'backend', 'browser'}:
            suites = ET.parse(evidence / (name + '.xml')).getroot().findall('testsuite')
            summary['tests'][name] = {key: sum(int(suite.get(key, '0')) for suite in suites)
                                     for key in ('tests', 'failures', 'errors', 'skipped')}
    sources = [*backend, *browser,
               *[str(path.relative_to(ROOT)) for directory in ('src/muse/commerce', 'src/muse/commerce_connector',
                    'frontend/src/commerce', 'wordpress/muse-connector', 'wordpress/muse-storefront')
                 for path in (ROOT / directory).rglob('*') if path.is_file() and path.suffix in {'.py', '.php', '.tsx', '.ts', '.css'}],
               'scripts/commerce/verify_task_board.py', 'src/muse/tasks/worker.py', 'src/muse/tasks/repository.py',
               'src/muse/config.py', 'frontend/src/main.tsx', 'frontend/src/api.generated.ts', 'deploy/commerce/versions.lock.json']
    for name in sorted(set(sources)):
        summary['sha256'][name.replace('\\', '/')] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    for directory in ('work/task-board-ui-2026-10-05', 'work/task-board-status-2026-10-05'):
        for path in sorted((ROOT / directory).glob('*.png')):
            summary['sha256'][str(path.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(path.read_bytes()).hexdigest()
    (evidence / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary['tests'], ensure_ascii=False), flush=True)
    print('Evidence: ' + str(evidence), flush=True)


if __name__ == '__main__':
    main()
