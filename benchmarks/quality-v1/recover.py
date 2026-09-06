"""Documented infrastructure recovery. Preserve failed/aborted raw attempts.
Never retry a production failure with HTTP200; it is a valid experimental outcome.
"""
import datetime,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,o):p.write_text(json.dumps(o,indent=2),encoding='utf-8')
def received(d):return any(read(p).get('http_status')==200 for p in (d/'wire').glob('*-meta.json'))
def main():
 m=read(ROOT/'quality-v1/build.json');protocol=read(ROOT/'quality-v1/protocol.json');batch=ROOT/'results/raw/context-quality-ab'/protocol['study_id']
 for name,h in protocol['frozen_files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,'Frozen file changed'
 for arm,v in m['arms'].items():
  for name,h in v['class_hashes'].items():assert hashlib.sha256((Path(v['classes'])/name).read_bytes()).hexdigest()==h
 plan_path=ROOT/'quality-v1/recovery-plan.json';selection_path=batch/'recovery-selection.json'
 if not plan_path.exists():
  selected={};excluded={}
  for item in m['schedule']:
   d=batch/item['run_id']
   if not (d/'run.json').exists():continue
   r=read(d/'run.json')
   if received(d) and r['status']!='RUNNING':selected[item['run_id']]=d.name
   else:excluded[d.name]='OPERATOR_INTERRUPTED' if r['status']=='RUNNING' else 'NO_UPSTREAM_HTTP_200; TLS forwarding error'
  plan=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),reason='TLS handshake failures in both arms after pair7; first fourteen completed HTTP200 experiments retained',criterion='First completed physical attempt per logical slot with any upstream HTTP200; production parsing failure still counts. No HTTP response and operator interruption remain in all-started denominator.',target_model_attempts_per_arm=20,initial_selected=selected,excluded_from_model_cohort=excluded,schedule=m['schedule'],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),stopping='Stop immediately at next non200/infrastructure failure; never automatically exhaust retries')
  write(plan_path,plan);write(selection_path,selected)
 plan=read(plan_path);selected=read(selection_path)
 assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==plan['script_sha256']
 for item in m['schedule']:
  logical=item['run_id'];arm=item['arm']
  if logical in selected:continue
  directory=batch/(logical+'-recovery-01')
  if directory.exists():raise SystemExit('Recovery attempt already exists; inspect before any further retry')
  directory.mkdir();print('START '+directory.name,flush=True)
  with (directory/'process.log').open('w',encoding='utf-8') as out:
   p=subprocess.Popen(['java','-Dbench.root='+str(ROOT),'-Dbench.harness.sha='+hashlib.sha256((ROOT/'quality-v1/build.json').read_bytes()).hexdigest(),'-cp',m['arms'][arm]['classes']+';'+m['dependency_jar'],'bench.ABRun',str(directory),arm,m['arms'][arm]['commit']],stdout=out,stderr=subprocess.STDOUT)
   try:code=p.wait(timeout=1860)
   except subprocess.TimeoutExpired:p.kill();p.wait();raise SystemExit('Outer timeout: preserve partial attempt and stop')
  if code or not (directory/'run.json').exists():raise SystemExit('Process/configuration failure: stop')
  r=read(directory/'run.json');print('END '+directory.name+' '+r['status']+' '+str(round(r.get('wall_clock_seconds',0),2))+'s',flush=True)
  if not received(directory):raise SystemExit('Infrastructure failure before upstream200; stopped immediately. Raw preserved.')
  selected[logical]=directory.name;write(selection_path,selected)
 print('ALL_40_HTTP200_MODEL_ATTEMPTS_COMPLETE; all infrastructure attempts retained separately',flush=True)
if __name__=='__main__':main()
