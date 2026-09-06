"""Supplemental frozen-v1 vs punctuation-corrected-v2 scores. Blind CSV unchanged."""
import collections,csv,hashlib,json,statistics
from pathlib import Path
import scorer_v2
ROOT=Path(__file__).resolve().parents[1];csv.field_size_limit(10_000_000)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 facts=read(ROOT/'context-retention/facts.json')['facts'];study=read(ROOT/'results/context-quality-study.json')
 positive=[scorer_v2.evaluate(f,f['statement']) for f in facts]
 assert all(r['semantic']=='SUPPORTED' for r in positive)
 assert all(r['exact'] is True for r in positive if r['exact'] is not None)
 for expected,source in [('730','1730'),('730','730.5'),('name.json','name.json.bak'),('Clazz','ClazzExtra')]:assert not scorer_v2.literal(expected,source)
 source_tests={'original_semantic_controls_pass':50,'original_semantic_controls_total':50,'original_exact_controls_pass':30,'original_exact_controls_total':30,'literal_negative_controls_pass':4}
 lookup={};runs=[]
 for run in study['runs']:
  directory=ROOT/run['raw_directory'];summary=(directory/'forensics/summary.txt').read_text(encoding='utf-8')
  recent='\n\n'.join(m.get('content') or '' for m in read(directory/'forensic-recent.json'))
  recovery=(directory/'forensic-recovery.txt').read_text(encoding='utf-8');rows=[]
  for f in facts:
   parts=[scorer_v2.evaluate(f,s) for s in [summary,recent,recovery]];supported=any(x['semantic']=='SUPPORTED' for x in parts);conflict=any(x['semantic'] in ['DISTORTED','CONFLICT'] for x in parts)
   full='CONFLICT' if supported and conflict else 'SUPPORTED' if supported else 'DISTORTED' if conflict else 'UNVERIFIED'
   for view,state,exact in [('summary',parts[0]['semantic'],parts[0]['exact']),('effective',full,any(x['exact'] is True for x in parts) if f['category'] in scorer_v2.EXACT_CATEGORIES else None)]:
    value=dict(run_id=run['run_id'],arm=run['arm'],fact_id=f['id'],view=view,semantic=state,exact=exact)
    lookup[(run['run_id'],f['id'],view)]=value;rows.append(value)
  result=dict(run_id=run['run_id'],arm=run['arm'])
  for view in ['summary','effective']:
   rs=[r for r in rows if r['view']==view];exact=[r['exact'] for r in rs if r['exact'] is not None]
   result[view+'_semantic_screen_percent']=100*sum(r['semantic']=='SUPPORTED' for r in rs)/len(rs)
   result[view+'_exact_percent']=100*sum(exact)/len(exact)
  runs.append(result)
 key_path=ROOT/'results/manual-review-key.csv'
 with key_path.open(encoding='utf-8-sig',newline='') as f:key=list(csv.DictReader(f))
 original=(ROOT/'results/manual-review-blind.csv').read_bytes()
 for row in key:
  v=lookup[(row['run_id'],row['fact_id'],row['view'])]
  row['primary_evaluator_version']='frozen-v1'
  row['v2_semantic_result']=v['semantic'];row['v2_exact_result']='NOT_APPLICABLE' if v['exact'] is None else 'PASS' if v['exact'] else 'NOT_VERIFIED'
 with key_path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,list(key[0]));w.writeheader();w.writerows(key)
 assert (ROOT/'results/manual-review-blind.csv').read_bytes()==original
 means={arm:{name:statistics.mean(r[name] for r in runs if r['arm']==arm) for name in ['summary_semantic_screen_percent','effective_semantic_screen_percent','summary_exact_percent','effective_exact_percent']} for arm in ['old','new']}
 output=dict(version='v2-punctuation-boundary',timing='Post-generation diagnostic correction; all primary frozen-v1 results preserved',change='Allow terminal punctuation in literal matching; no other rule change',human_audit='PENDING',tests=source_tests,means=means,runs=runs,facts=list(lookup.values()),blind_sha256=hashlib.sha256(original).hexdigest(),scorer_sha256=hashlib.sha256(Path(scorer_v2.__file__).read_bytes()).hexdigest())
 (ROOT/'results/context-quality-supplemental-v2.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
 print(json.dumps({'tests':source_tests,'blind_unchanged':True,'human_audit':'PENDING'}))
if __name__=='__main__':main()
