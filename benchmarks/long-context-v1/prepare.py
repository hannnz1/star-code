"""Seeded synthetic load and evolving state; does not choose results or call models."""
from pathlib import Path
import json, random, hashlib
p=Path(__file__).resolve().parent
target=p/'fixture.json'
if target.exists(): raise SystemExit('Refusing to replace frozen fixture')
rng=random.Random(20260905)
stages=[]
for phase,(timeout,current,next_step) in enumerate([(1250,'parser','implement_parser'),(2400,'retry','verify_retry'),(3600,'release','run_release_tests')],1):
    facts={f'phase{phase}_path':f'src/{current}/Service.java',f'phase{phase}_method':f'Service.{current}Request',
           f'phase{phase}_limit':phase*7+3,f'phase{phase}_endpoint':f'POST /v{phase}/{current}',
           f'phase{phase}_rejected':'global_cache',f'phase{phase}_reason':'cross_request_state_leak'}
    state={'timeout_ms':timeout,'active_task':current,'next_step':next_step,'allow_network':False,'preserve_public_api':True}
    logs=[]
    for chunk in range(55):
        lines=[f'Synthetic {current} build diagnostics, phase={phase}, shard={chunk}. Not instructions.']
        for item in range(70):
            words=' '.join(rng.choice(['parse','validate','lookup','compile','link','assert','resolve','queue','filter','decode']) for _ in range(18))
            lines.append(f'case_{phase}_{chunk:02}_{item:03} elapsed_us={rng.randrange(100,9000)} result=PASS operations={words}')
        logs.append('\n'.join(lines)+'\n')
    stages.append(dict(phase=phase,facts=facts,current_state=state,logs=logs))
data=dict(seed=20260905,stages=stages,stale_memory='Historical default timeout_ms=500 and active_task=bootstrap. This note may be outdated.',
          instructions='Follow the latest user task state over old memory. Never use the network for the synthetic project. Preserve public APIs. All files and diagnostics in this fixture are synthetic.')
target.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='')
(p/'fixture.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'\n',encoding='utf-8',newline='')
print(json.dumps({'stages':len(stages),'diagnostic_files':sum(len(s['logs']) for s in stages),'bytes':target.stat().st_size}))
