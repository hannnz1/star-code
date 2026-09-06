"""Offline aggregation; never invokes an Agent, changes labels, or merges code."""
from pathlib import Path
from collections import Counter
import json, csv, hashlib

root=Path(__file__).resolve().parents[1]; out=root/'results'
batch=root/(out/'multi-agent-v2-latest.txt').read_text().strip()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
environment=read(batch/'environment.json')
rows=[]
for p in sorted(batch.glob('*/run.json')):
    r=read(p);directory=p.parent
    calls=[read(f) for f in sorted((directory/'calls').glob('*.json'))]
    usages=[];missing=0
    for f in sorted((directory/'wire').glob('*-response.sse')):
        found=None
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.startswith('data:'):continue
            try:e=json.loads(line[5:])
            except ValueError:continue
            if e.get('type')=='response.completed':found=e.get('response',{}).get('usage')
        if found:usages.append(found)
        else:missing+=1
    row={'case':directory.name[len(batch.name)+1:],'status':r['status'],
         'main_completed':r.get('main_completed',False),'main_verified_after_changes':r.get('main_verified_after_changes',False),
         'explicitly_collected_results':r.get('explicitly_collected_results',0),
         'unified_test_passed':r.get('unified_test_passed',False),'workers':r.get('subagent_count',0),
         'worktrees':r.get('independent_worktree_count',0),'overlap_seconds':r.get('maximum_pair_overlap_seconds'),
         'wall_clock_seconds':r['wall_clock_seconds'],'main_calls':sum(c.get('agent_kind')=='main' for c in calls),
         'child_calls':sum(c.get('agent_kind')=='subagent' for c in calls),'all_calls':len(calls),
         'failed_calls':sum(c['status']!='SUCCESS' for c in calls),'usage_records':len(usages),'missing_response_usage':missing,
         'known_input_tokens':sum(u.get('input_tokens',0) for u in usages),
         'known_output_tokens':sum(u.get('output_tokens',0) for u in usages),
         'known_total_tokens':sum(u.get('total_tokens',0) for u in usages),
         'failure_reason':r.get('failure_reason'),'raw_directory':directory.relative_to(root).as_posix()}
    rows.append(row)
passed=len(rows)==3 and all(r['status']=='PASS' for r in rows)
result={'status':'PASS' if passed else 'BLOCKED','speedup_status':'NOT_MEASURED',
        'environment':environment,'completed_cases':len(rows),'passed_cases':sum(r['status']=='PASS' for r in rows),'runs':rows,
        'limitations':['Three synthetic independent-file tasks, one attempt each; no speed comparison or confidence claim.',
                      'Parent40/100 default budget differs from old10/50; previous failures retained, not paired timing controls.',
                      'Conflicting edits, coupled changes, long-run reliability and OS sandbox are not tested.',
                      'Explicit TaskGet collection is required by this gate; notification-only collection is not credited.',
                      'No model seed is set; seed20260905 describes fixture provenance only.']}
(out/'multi-agent-v2-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8',newline='')
with (out/'multi-agent-v2-runs.csv').open('w',encoding='utf-8',newline='') as f:
    if rows:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
lines=['# Multi-Agent v2 complete workflow gate','',f"**{result['status']}** — {result['passed_cases']}/3 required distinct contracts passed. Speedup NOT_MEASURED.",'',
       f"Implementation commit `{environment['implementation_commit']}`; Main budget {environment['main_max_turns']} turns/{environment['main_max_tool_calls']} tool calls.",
       '','| Case | Strict status | Main complete | Main verifier | Unified test | Workers / trees | Overlap seconds | Wall seconds | Calls |',
       '|---|---|---|---|---|---|---:|---:|---:|']
for r in rows:
    lines.append(f"| {r['case']} | {r['status']} | {r['main_completed']} | {r['main_verified_after_changes']} | {r['unified_test_passed']} | {r['workers']} / {r['worktrees']} | {r['overlap_seconds']} | {r['wall_clock_seconds']:.3f} | {r['all_calls']} |")
lines+=['','Raw requests/responses, per-agent lifecycle, collection, Worktree diffs, main changes, unchanged verifier and independent test output are retained under the recorded raw directories. Actual provider usage coverage and exceptions are in CSV/JSON. No harness decomposition, code implementation or integration occurred.','',
        '## Limits','']+['- '+s for s in result['limitations']]
lines+=['','## Reproduce','',
        'After committing production and compiling all sources using benchmarks/run.ps1 compile, invoke bench.GateSuiteCurrent with bench.root/bench.harness.sha and generated classes + dependency JAR. Uses paid configured model calls. Regenerate summary offline with python benchmarks/multi-agent-v2/summarize.py. Preserve raw/build hashes/frozen fixtures and artifact index together.']
(out/'multi-agent-v2-final.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='')
files=sorted(p for p in batch.rglob('*') if p.is_file())
(out/'multi-agent-v2-artifact-index.json').write_text(json.dumps([{'path':p.relative_to(root).as_posix(),
    'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],indent=2),encoding='utf-8',newline='')
print(json.dumps({'status':result['status'],'runs':rows},indent=2))
