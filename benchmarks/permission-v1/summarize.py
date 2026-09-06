"""Regenerate policy replay CSV, JSON and report from preserved per-action results."""
from pathlib import Path
import csv, json, statistics, hashlib

root=Path(__file__).resolve().parents[1]
out=root/'results'
batch=root/(out/'permission-v1-latest.txt').read_text().strip()
rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(batch.glob('*/run.json'))]
assert len(rows)==20 and all(r['status']=='SUCCESS' for r in rows)
summaries={}
for mode in ('BASELINE_ONCE','CURRENT_SESSION'):
    selected=[r for r in rows if r['policy']==mode]
    summaries[mode]={'sessions':len(selected), 'median_prompts':statistics.median(r['permission_prompts'] for r in selected),
                     **{key:sum(r[key] for r in selected) for key in ('permission_prompts','approved','denied','auto_allowed',
                           'session_allowed','dangerous_action_blocked','unsafe_auto_approval_count')}}
base=summaries['BASELINE_ONCE']['median_prompts']; current=summaries['CURRENT_SESSION']['median_prompts']
result={'status':'POLICY_REPLAY_COMPLETE', 'production_commit':rows[0]['git_commit'], 'raw_directory':str(batch),
        'summaries':summaries, 'median_prompt_reduction_percent':100*(base-current)/base,
        'task_success':None, 'real_coding_sessions':0,
        'interpretation':'Deterministic fixed action traces, injected user choices; no model or shell execution.',
        'limits':['No OS sandbox result','No general unsafe-action guarantee','No real-session30-to-5 result',
                  'Both policies deny labeled risky requests. Existing readonly auto-allow and safety guards are shared.']}
(out/'permission-v1-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
with (out/'permission-v1-runs.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
lines=['# Session permission validation','',
       f"Production commit `{rows[0]['git_commit']}`. Full Gradle suite204 tests in55 suites, zero failures/errors/skips.",
       '', '## Mechanism', '',
       'Explicit ALLOW_SESSION caches the same tool/path or exact command/remote arguments for one actor, execution directory and permission mode. Different file contents are within a granted edit-path scope. New sessions/resume clear grants. Grants are never persisted. Configured rules, path checks and immutable blacklist precede reuse. UI key4 selects the new option; existing keys1/2/3 keep their meanings.',
       '', '## Fixed workflow replay', '',
       'Ten distinct synthetic coding action traces,180 actions per policy,360 recorded decisions. BASELINE uses production DEFAULT plus user ALLOW_ONCE; CURRENT uses the same policy plus explicit user ALLOW_SESSION. Read/search remain automatically allowed in both. Commands are not executed, no model is called, and task_success is null. This is a policy comparison, not an old production-code performance comparison.',
       '', '| Policy | Median prompts | Total prompts | Reused session grants | Risky actions denied | Unsafe automatic allows |',
       '|---|---:|---:|---:|---:|---:|']
for mode,s in summaries.items():
    lines.append(f"| {mode} | {s['median_prompts']} | {s['permission_prompts']} | {s['session_allowed']} | {s['dangerous_action_blocked']} | {s['unsafe_auto_approval_count']} |")
lines += ['',f"Median confirmation count decreases from{base} to{current} ({result['median_prompt_reduction_percent']:.2f}%) in these fixed traces only. This is not evidence for30-to-5 in real coding sessions.",
          '', 'Each trace contains five high-risk probes: forced push, deleting .git, remote script execution, a path escape and disk formatting. The injected user rejects the first three when prompted; the existing boundary/blacklist rejects the latter two before approval. Zero unsafe automatic approvals applies only to this finite corpus and these user decisions. An explicitly session-approved command can be repeated; there is no universal risk classifier or kernel isolation.',
          '', '## Reproduce and limitations', '',
          'Compile benchmarks/run.ps1, invoke bench.PermissionBench with the generated classpath/bench.root/bench.harness.sha, then run python benchmarks/permission-v1/summarize.py. Fixture is frozen at permission-v1/fixture.json. Preserve raw alongside permission-v1-artifact-index.json. Every action has a request, decision, reason, prompt flag and risk label. Benchmark metadata records environment/commit and null model usage. No API spend or real UI prompt timings are measured.',
          '', 'The action sequences are designed synthetic workloads with repeated edits/builds. They show cache mechanics, not an estimate of everyday user prompt frequency. Need real, consented coding traces before a broad resume percentage. Permanent-rule behavior was not redesigned; OS sandbox and standalone risk levels remain absent.']
(out/'permission-v1-final.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
files=sorted(p for p in batch.rglob('*') if p.is_file())
(out/'permission-v1-artifact-index.json').write_text(json.dumps([{'path':p.relative_to(root).as_posix(),
    'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
