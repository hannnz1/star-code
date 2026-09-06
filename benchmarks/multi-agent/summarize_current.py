"""Reconstruct current gate evidence without invoking an Agent or merging code."""
from pathlib import Path
from collections import Counter
import json, hashlib

root = Path(__file__).resolve().parents[1]
batch = root / (root / 'results/multi-agent-current-latest.txt').read_text().strip()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
run, environment = read(batch/'run.json'), read(batch/'environment.json')
calls = [read(p) for p in sorted((batch/'calls').glob('*.json'))]
tasks = read(batch/'tasks.json') if (batch/'tasks.json').exists() else []
conversation = read(batch/'parent-conversation.json') if (batch/'parent-conversation.json').exists() else []
terminal = conversation[-1].get('content', '') if conversation else ''
main_completed = bool(terminal.strip()) and not terminal.startswith('[Agent run ended with ')
strict_status = 'PASS' if run['status'] == 'PASS' and main_completed else 'BLOCKED'
errors = [{'name': r.get('name'), 'error_code': r.get('errorCode'), 'output': r.get('output')}
          for m in conversation for r in m.get('toolResults', []) if not r.get('success', True)]
usage, missing = [], []
for p in sorted((batch/'wire').glob('*-response.sse')):
    found = None
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.startswith('data:'): continue
        try: event = json.loads(line[5:])
        except ValueError: continue
        if event.get('type') == 'response.completed': found = event.get('response', {}).get('usage')
    if found: usage.append(found)
    else: missing.append(p.name)
result = {'status': strict_status, 'component_gate_status': run['status'], 'main_completed': main_completed,
          'main_terminal_message': terminal, 'speedup_status': 'NOT_MEASURED', 'raw_directory': str(batch),
          'environment': environment, 'gate': run, 'calls_by_role': dict(Counter(c.get('agent_kind') for c in calls)),
          'calls_by_status': dict(Counter(c['status'] for c in calls)),
          'task_statuses': {t['name']: t['status'] for t in tasks}, 'main_tool_errors': errors,
          'known_provider_usage': {k: sum(u.get(k, 0) for u in usage) for k in ('input_tokens','output_tokens','total_tokens')},
          'usage_records': len(usage), 'responses_missing_usage': missing,
          'limitations': ['A changed main-checkout file does not prove integration of a worker result.',
                         'Task states are captured at Main Agent return, before resource shutdown.',
                         'Independent verifier PASS does not prove the Main Agent completed verification.',
                         'Role attribution follows presence of the Agent tool; thread IDs and prompts are preserved for audit.']}
out = root/'results'
(out/'multi-agent-current-summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
(batch/'audited-summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
index = [{'path': p.relative_to(root).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
          'bytes': p.stat().st_size} for p in sorted(batch.rglob('*')) if p.is_file()]
(out/'multi-agent-current-artifact-index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
print(json.dumps({k: result[k] for k in ('status','calls_by_role','calls_by_status','task_statuses','known_provider_usage','usage_records')}))
