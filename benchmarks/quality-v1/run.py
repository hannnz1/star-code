"""Run exactly 20 pairs, randomized within-pair order, sequential on one machine.
Resume never repeats an attempted directory. No paid model extraction/LLM judge.
"""
import hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=json.loads((ROOT/'quality-v1/build.json').read_text());protocol=json.loads((ROOT/'quality-v1/protocol.json').read_text())
 for name,value in protocol['frozen_files'].items():assert sha(ROOT/name)==value,'Frozen study file changed: '+name
 for name,value in m['fixture_hashes'].items():assert sha(ROOT/name)==value,'Frozen fixture changed: '+name
 for arm,v in m['arms'].items():
  for name,value in v['class_hashes'].items():assert sha(Path(v['classes'])/name)==value,'Class changed'
 batch=ROOT/'results/raw/context-quality-ab'/protocol['study_id'];batch.mkdir(parents=True,exist_ok=True)
 (ROOT/'results/context-quality-latest.txt').write_text(str(batch.relative_to(ROOT)),encoding='utf-8')
 for item in m['schedule']:
  directory=batch/item['run_id'];record=directory/'run.json';arm=item['arm']
  if record.exists():
   r=json.loads(record.read_text())
   if r.get('status')=='RUNNING':raise SystemExit('Unfinished run needs forensic review, not blind repeat: '+str(directory))
   continue
  if directory.exists():raise SystemExit('Partial attempt directory exists: '+str(directory))
  directory.mkdir();print('START '+item['run_id'],flush=True)
  with (directory/'process.log').open('w',encoding='utf-8') as out:
   p=subprocess.Popen(['java','-Dbench.root='+str(ROOT),'-Dbench.harness.sha='+sha(ROOT/'quality-v1/build.json'),'-cp',m['arms'][arm]['classes']+';'+m['dependency_jar'],'bench.ABRun',str(directory),arm,m['arms'][arm]['commit']],stdout=out,stderr=subprocess.STDOUT)
   try:code=p.wait(timeout=1860)
   except subprocess.TimeoutExpired:
    p.kill();p.wait();code=-1
    r=json.loads(record.read_text()) if record.exists() else {'arm':arm,'run_id':item['run_id']}
    r.update(status='HARNESS_TIMEOUT',operational_success=False,failure_reason='Outer 1860 second deadline',wall_clock_seconds=1860);record.write_text(json.dumps(r,indent=2),encoding='utf-8')
  if code and not record.exists():raise SystemExit('Preflight/process failure: '+str(directory/'process.log'))
  r=json.loads(record.read_text());print('END '+item['run_id']+' '+r['status']+' '+str(round(r.get('wall_clock_seconds',0),2))+'s',flush=True)
  if r.get('failure_type') in ['ConfigException','IllegalStateException'] or 'AUTHENTICATION' in r.get('failure_reason',''):raise SystemExit('Infrastructure/configuration failure; batch stopped for review')
 print('ALL_40_ATTEMPTS_COMPLETE',flush=True)
if __name__=='__main__':main()
