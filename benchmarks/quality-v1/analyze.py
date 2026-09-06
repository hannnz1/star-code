"""Offline operational/forensic analysis. No paid calls, no production mutation."""
import collections,csv,hashlib,json,math,random,re,statistics,sys
from pathlib import Path
import scorer
ROOT=scorer.ROOT
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def csvwrite(p,rows):
 if not rows:return
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)
def messages(p):return '\n\n'.join(m.get('content') or '' for m in read(p)) if p.exists() else ''
def percentile(v,q):
 v=sorted(v);pos=(len(v)-1)*q;lo=int(pos);hi=math.ceil(pos);return v[lo]+(v[hi]-v[lo])*(pos-lo)
def distribution(values):
 v=[x for x in values if isinstance(x,(float,int))]
 return dict(n=len(v),mean=statistics.mean(v),median=statistics.median(v),p10=percentile(v,.1),p25=percentile(v,.25),p75=percentile(v,.75),p90=percentile(v,.9),min=min(v),max=max(v),sample_sd=statistics.stdev(v) if len(v)>1 else None) if v else {'n':0}
def wire(d):
 results=[]
 for p in sorted((d/'wire').glob('*-response.sse')):
  delta=[];usage=None;completed=False;model=None
  for line in p.read_text(encoding='utf-8',errors='replace').splitlines():
   if not line.startswith('data:'):continue
   try:e=json.loads(line[5:].strip())
   except ValueError:continue
   if e.get('type')=='response.output_text.delta':delta.append(e.get('delta',''))
   if e.get('type')=='response.completed':completed=True;usage=e.get('response',{}).get('usage');model=e.get('response',{}).get('model')
  results.append(dict(raw=''.join(delta),usage=usage,completed=completed,model=model,path=str(p.relative_to(ROOT))))
 return results
def forensic(raw):
 opening=re.search(r'<\s*summary\s*>',raw,re.I);closes=list(re.finditer(r'<\s*/\s*summary\s*>',raw,re.I))
 if not opening:return raw.strip(),'RAW_WITHOUT_OPEN_MARKER'
 end=next((x.start() for x in reversed(closes) if x.start()>opening.end()),None)
 return raw[opening.end():end].strip(),'CLOSED_SPAN' if end is not None else 'OPEN_THROUGH_EOF_INCOMPLETE'
def pct(rows,key,applicable=False):
 v=[r[key] for r in rows if r.get(key) is not None];return 100*sum(v)/len(v) if v else None
def analyze_run(d,facts):
 r=read(d/'run.json');ws=wire(d);raw=ws[-1]['raw'] if ws else ''
 # Raw wire is available even if the production client threw before returning Completion.
 if not raw:
  calls=[read(p) for p in sorted((d/'calls').glob('*.json'))]
  raw=next((c.get('response_text','') for c in reversed(calls) if c.get('response_text')),'')
 text,boundary=forensic(raw);operational=r.get('operational_success',r.get('status')=='SUCCESS')
 summary=(d/'summary.txt').read_text(encoding='utf-8') if operational and (d/'summary.txt').exists() else text
 recent=messages(d/'forensic-recent.json') or messages(d/'retained-recent.json')
 recovery=next((p.read_text(encoding='utf-8') for p in [d/'forensic-recovery.txt',d/'recovery.txt'] if p.exists()),'')
 sources={'summary':summary,'retained recent messages':recent,'recovery attachment':recovery}
 analysis=d/'forensics';analysis.mkdir(exist_ok=True)
 (analysis/'raw-response.txt').write_text(raw,encoding='utf-8');(analysis/'summary.txt').write_text(summary,encoding='utf-8')
 effective_text=messages(d/'effective-context.json') if operational and (d/'effective-context.json').exists() else '\n\n'.join([summary,recovery,recent])
 (analysis/'effective.txt').write_text(effective_text,encoding='utf-8')
 details=[]
 for f in facts:
  results={k:scorer.evaluate(f,v) for k,v in sources.items()}
  origins=[k for k,v in results.items() if v['semantic']=='SUPPORTED'];conflict=any(v['semantic'] in ['CONFLICT','DISTORTED'] for v in results.values())
  full='CONFLICT' if origins and conflict else 'SUPPORTED' if origins else 'DISTORTED' if conflict else 'UNVERIFIED'
  row=dict(run_id=d.name,arm=r.get('arm','historical'),id=f['id'],category=f['category'],position=f['position'],operational_success=operational,summary_state=results['summary']['semantic'],effective_state=full,summary_semantic_supported=results['summary']['semantic']=='SUPPORTED',effective_semantic_supported=full=='SUPPORTED',summary_exact=results['summary']['exact'],effective_exact=any(v['exact'] is True for v in results.values()) if f['category'] in scorer.EXACT_CATEGORIES else None,sources=origins or ['missing/unverified'],source_results=results)
  details.append(row)
 write(analysis/'fact-judgments.json',details)
 usages=[w['usage'] for w in ws];known=[u for u in usages if u is not None];usage_complete=bool(ws) and len(known)==len(ws)
 out=dict(run_id=d.name,arm=r.get('arm','historical'),status=r.get('status'),operational_success=operational,parse_failure_reason=r.get('failure_reason',r.get('exception','')),summary_available_for_forensics=bool(summary),forensic_boundary=boundary,forensic_effective_is_hypothetical=not operational,raw_response_length=len(raw),summary_characters=len(summary),summary_tokens_estimated=round(len(summary)/3.5),token_estimation_method='characters/3.5, estimated not provider tokens',wall_clock_seconds=r.get('wall_clock_seconds'),model_calls=len(ws),retry_count=max(0,len(ws)-1),usage_complete=usage_complete,raw_directory=str(d.relative_to(ROOT)))
 for field in ['input_tokens','output_tokens','total_tokens']:
  values=[u.get(field,u.get('input_tokens',0)+u.get('output_tokens',0) if field=='total_tokens' else 0) for u in known]
  out[field]=sum(values) if usage_complete else None;out['known_'+field]=sum(values) if known else None
  retry=[w['usage'] for w in ws[1:]]
  out['retry_'+field]=sum(u.get(field,u.get('input_tokens',0)+u.get('output_tokens',0) if field=='total_tokens' else 0) for u in retry) if all(u is not None for u in retry) else None
 out['estimated_retry_currency_cost']=None;out['retry_currency_cost_reason']='Actual provider/cache unit prices unavailable; retry token overhead is reported.'
 for view in ['summary','effective']:
  out[view+'_exact_retention']=pct(details,view+'_exact') if summary else None
  out[view+'_semantic_verified_percent']=pct(details,view+'_semantic_supported') if summary else None
  out[view+'_unverified_percent']=100*sum(x[view+'_state']=='UNVERIFIED' for x in details)/len(facts) if summary else None
  out['operational_'+view+'_semantic_verified_percent']=out[view+'_semantic_verified_percent'] if operational else None
 out['summary_retention']=out['summary_semantic_verified_percent'];out['effective_context_retention']=out['effective_semantic_verified_percent'];out['quality_metric_status']='UNVALIDATED_EVIDENCE_SCREEN; not definitive semantic retention'
 out['first_response_tokens_estimated']=round(len(ws[0]['raw'])/3.5) if ws else None
 out['retry_response_tokens_estimated']=round(len(ws[-1]['raw'])/3.5) if len(ws)>1 else None
 out['response_models']=[w['model'] for w in ws]
 out['first_attempt_summary_semantic_verified_percent']=100*sum(scorer.evaluate(f,forensic(ws[0]['raw'])[0])['semantic']=='SUPPORTED' for f in facts)/len(facts) if len(ws)>1 else out['summary_semantic_verified_percent']
 return out,details
def summarize(rows):
 result=dict(attempts=len(rows),successful_compactions=sum(r['operational_success'] for r in rows),failed_compactions=sum(not r['operational_success'] for r in rows),success_rate=100*sum(r['operational_success'] for r in rows)/len(rows) if rows else None,retry_rate=100*sum(r['retry_count']>0 for r in rows)/len(rows) if rows else None)
 for key in ['summary_exact_retention','effective_exact_retention','summary_semantic_verified_percent','effective_semantic_verified_percent','operational_summary_semantic_verified_percent','operational_effective_semantic_verified_percent','wall_clock_seconds','model_calls','input_tokens','output_tokens','total_tokens','retry_input_tokens','retry_output_tokens','retry_total_tokens','summary_tokens_estimated','first_response_tokens_estimated','retry_response_tokens_estimated']:
  result[key]=distribution(r.get(key) for r in rows)
 result['all_usage_known']=all(r['usage_complete'] for r in rows)
 result['known_total_tokens']=sum(r['known_total_tokens'] or 0 for r in rows)
 for label,subset in [('successful', [r for r in rows if r['operational_success']]),('failed',[r for r in rows if not r['operational_success']]),('retry',[r for r in rows if r['retry_count']]),('no_retry',[r for r in rows if not r['retry_count']])]:
  result[label+'_forensic_quality']=distribution(r['effective_semantic_verified_percent'] for r in subset)
 return result
def audit_packet(batch,details,facts):
 cases=[(r,view) for r in details for view in ['summary','effective']]
 rng=random.Random(20260905);rng.shuffle(cases);sample=cases[:math.ceil(.2*len(cases))]
 dest=ROOT/'results/context-quality-human-audit';dest.mkdir(exist_ok=True);source_dir=dest/'sources';source_dir.mkdir(exist_ok=True)
 rows=[];key=[];mapped={}
 for n,(r,view) in enumerate(sample,1):
  source_key=(r['run_id'],view)
  if source_key not in mapped:
   alias='source-'+hashlib.sha256(('blind-20260905'+repr(source_key)).encode()).hexdigest()[:12]+'.txt';mapped[source_key]=alias
   (source_dir/alias).write_text((batch/r['run_id']/'forensics'/f'{view}.txt').read_text(encoding='utf-8'),encoding='utf-8')
  case=f'J{n:04d}';fact=next(f for f in facts if f['id']==r['id'])
  rows.append(dict(case_id=case,fact_id=r['id'],fact= fact['statement'],source_file='sources/'+mapped[source_key],human_label='',human_evidence='',human_reason='',reviewer='',reviewed_at=''))
  key.append(dict(case_id=case,run_id=r['run_id'],arm=r['arm'],view=view,fact_id=r['id'],automatic_state=r[view+'_state']))
 sheet=dest/'review-sheet.csv'
 if sheet.exists():
  with sheet.open(encoding='utf-8-sig',newline='') as f:existing=list(csv.DictReader(f))
  assert [(r['case_id'],r['fact_id'],r['source_file']) for r in existing]==[(r['case_id'],r['fact_id'],r['source_file']) for r in rows],'Existing human sample differs; never overwrite it'
 else:csvwrite(sheet,rows)
 write(batch/'human-audit-key.json',key)
 (dest/'README.md').write_text('''# Human audit (blind)

This is a seeded random 20% sample of fact/view judgments. OLD/NEW labels and automatic decisions are withheld. Read the entire referenced source, not only keywords. Label the proposition SUPPORTED, DISTORTED, MISSING, CONFLICT, or UNCERTAIN; provide a source quote/reason and reviewer identity/date. Synonyms are valid when subject, relation, values, units, polarity and task state are preserved. Missing means no supporting fact after full-source inspection. Do not consult the separate raw audit key until review is complete. These blank rows are NOT completed human judgments. Do not let the agent fill reviewer fields while claiming human review.
''',encoding='utf-8')
 return dict(population=len(cases),sample_size=len(sample),fraction=len(sample)/len(cases) if cases else None,status='PENDING_HUMAN_REVIEW',manual_disagreement_rate=None,path=str(dest.relative_to(ROOT)))
def main():
 facts=read(ROOT/'context-retention/facts.json')['facts'];protocol=read(ROOT/'quality-v1/protocol.json')
 for p,h in protocol['frozen_files'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,'Frozen input changed: '+p
 batch=ROOT/'results/raw/context-quality-ab'/protocol['study_id'];rows=[];details=[];all_started=[]
 selection=read(batch/'recovery-selection.json') if (batch/'recovery-selection.json').exists() else None
 selected_names=set(selection.values()) if selection is not None else None
 recovery_plan=read(ROOT/'quality-v1/recovery-plan.json') if (ROOT/'quality-v1/recovery-plan.json').exists() else {}
 excluded=recovery_plan.get('excluded_from_model_cohort',{})
 for p in sorted(batch.glob('*/run.json')):
  if read(p).get('status')=='RUNNING' and excluded.get(p.parent.name)!='OPERATOR_INTERRUPTED':continue
  r,fs=analyze_run(p.parent,facts)
  if excluded.get(p.parent.name)=='OPERATOR_INTERRUPTED':r['status']='OPERATOR_INTERRUPTED';r['parse_failure_reason']='Operator stopped the batch after repeated TLS failures; raw RUNNING record preserved.'
  r['model_cohort_eligible']=selected_names is None or p.parent.name in selected_names
  all_started.append(r)
  if r['model_cohort_eligible']:rows.append(r);details.extend(fs)
 result={'study_id':protocol['study_id'],'conclusion':'INCONCLUSIVE','reason':'Semantic screen unvalidated; required human audit pending. No production optimization allowed.','arms':{arm:summarize([r for r in rows if r['arm']==arm]) for arm in ['old','new']},'runs':rows,'all_started_arms':{arm:summarize([r for r in all_started if r['arm']==arm]) for arm in ['old','new']},'all_started_runs':all_started,'infrastructure_recovery_plan':recovery_plan}
 for arm in ['old','new']:csvwrite(ROOT/f'results/context-ab-{arm}.csv',[r for r in rows if r['arm']==arm])
 csvwrite(ROOT/'results/context-ab-all-started.csv',all_started)
 csvwrite(ROOT/'results/old-version-forensic.csv',[r for r in rows if r['arm']=='old'])
 category=[]
 for arm in ['old','new']:
  for cat in sorted({f['category'] for f in facts}):
   for view in ['summary','effective']:
    rs=[r for r in details if r['arm']==arm and r['category']==cat];counts=collections.Counter(r[view+'_state'] for r in rs)
    category.append(dict(arm=arm,category=cat,view=view,fact_judgments=len(rs),retained_count=counts['SUPPORTED'],lost_count=None,distorted_count=counts['DISTORTED'],conflict_count=counts['CONFLICT'],unverified_count=counts['UNVERIFIED'],retention_percent=100*counts['SUPPORTED']/len(rs) if rs else None,metric_status='screen-only; lost_count requires human review'))
 csvwrite(ROOT/'results/fact-category-analysis.csv',category);result['categories']=category
 pairs=[(r['summary_exact'],r['summary_semantic_supported']) for r in details if r['summary_exact'] is not None]+[(r['effective_exact'],r['effective_semantic_supported']) for r in details if r['effective_exact'] is not None]
 result['exact_semantic_disagreement']={'n':len(pairs),'rate':sum(a!=b for a,b in pairs)/len(pairs) if pairs else None,'meaning':'Different constructs on applicable facts; not human-validated evaluator error'}
 controls=[]
 for d in sorted(batch.iterdir()):
  requests=sorted((d/'wire').glob('*-request.json'))
  if not requests:continue
  request=read(requests[0]);common={k:v for k,v in request.items() if k!='input'}
  history=request.get('input',[])[:-1]
  fingerprint=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  controls.append(dict(run=d.name,request_configuration_sha256=fingerprint(common),history_sha256=fingerprint(history),temperature=request.get('temperature','UNSET'),max_output_tokens=request.get('max_output_tokens','UNSET'),model=request.get('model')))
 result['request_controls']={'all_first_request_configs_equal':len({c['request_configuration_sha256'] for c in controls})==1,'all_first_request_histories_equal':len({c['history_sha256'] for c in controls})==1,'records':controls}
 if len(rows)==40:
  import manual_review
  result['human_audit']=manual_review.prepare(batch,details,facts)
 else:result['human_audit']={'status':'PENDING; WAITING_FOR_ALL_40_RUNS'}
 write(ROOT/'results/context-quality-study.json',result)
 print(json.dumps({'attempts':len(rows),'arms':{k:{f:v[f] for f in ['attempts','successful_compactions','failed_compactions','retry_rate']} for k,v in result['arms'].items()},'human_audit':result['human_audit']}))
if __name__=='__main__':main()
