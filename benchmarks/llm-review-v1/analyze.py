"""Offline analysis. Refuses to read the key until 160 reviews are hash-sealed."""
import collections,csv,hashlib,json
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OUT=ROOT/'results'
LABELS=['PASS','PARTIAL','FAIL','UNCERTAIN']
AUTO={'SUPPORTED':'PASS','DISTORTED':'FAIL','CONFLICT':'FAIL','UNVERIFIED':'UNCERTAIN'}
WEIGHT={'PASS':1.,'PARTIAL':.5,'FAIL':0.}
csv.field_size_limit(10_000_000)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csvread(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def csvwrite(p,rows):
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def pct(v):return 'N/A' if v is None else f'{100*v:.2f}%'
def distribution(rows):
 count=collections.Counter(r['reviewer_label'] for r in rows)
 valid=[r for r in rows if r['reviewer_label']!='UNCERTAIN']
 return {'total':len(rows),'labels':{k:count[k] for k in LABELS},'scored':len(valid),
  'strict':sum(r['reviewer_label']=='PASS' for r in valid)/len(valid) if valid else None,
  'weighted':sum(WEIGHT[r['reviewer_label']] for r in valid)/len(valid) if valid else None}
def agreement(rows,field):
 # Reviewer UNCERTAIN is excluded. Automatic UNVERIFIED remains a distinct label
 # for nominal agreement and receives zero only in the declared strict score.
 valid=[r for r in rows if r['reviewer_label']!='UNCERTAIN']
 matrix={h:{a:0 for a in LABELS} for h in LABELS[:3]}
 for r in valid:matrix[r['reviewer_label']][AUTO[r[field]]]+=1
 n=len(valid)
 out={'n':n,'reviewer_uncertain':len(rows)-n,'confusion_matrix_reviewer_rows_automatic_columns':matrix}
 if not n:return dict(out,raw_agreement=None,disagreement_rate=None,strict_agreement=None,
  strict_disagreement=None,weighted_agreement_credit=None,weighted_disagreement=None,cohens_kappa_strict=None)
 a=[int(AUTO[r[field]]=='PASS') for r in valid];h=[int(r['reviewer_label']=='PASS') for r in valid]
 w=[WEIGHT[r['reviewer_label']] for r in valid]
 raw=sum(AUTO[r[field]]==r['reviewer_label'] for r in valid)/n
 strict=sum(x==y for x,y in zip(a,h))/n;pa=sum(a)/n;ph=sum(h)/n
 chance=pa*ph+(1-pa)*(1-ph);distance=sum(abs(x-y) for x,y in zip(a,w))/n
 return dict(out,raw_agreement=raw,disagreement_rate=1-raw,strict_agreement=strict,
  strict_disagreement=1-strict,weighted_agreement_credit=1-distance,weighted_disagreement=distance,
  cohens_kappa_strict=(strict-chance)/(1-chance) if chance<1 else None,
  automatic_unverified=sum(AUTO[r[field]]=='UNCERTAIN' for r in valid))
def grouped(rows,key,fn):return {v:fn([r for r in rows if r[key]==v]) for v in sorted({r[key] for r in rows})}
def selftest():
 r=[{'reviewer_label':h,'auto':a} for h,a in [('PASS','SUPPORTED'),('PARTIAL','SUPPORTED'),('FAIL','DISTORTED'),('UNCERTAIN','SUPPORTED')]]
 m=agreement(r,'auto');assert m['n']==3 and m['reviewer_uncertain']==1
 assert abs(m['strict_agreement']-2/3)<1e-9 and abs(m['weighted_agreement_credit']-5/6)<1e-9
 assert abs(m['cohens_kappa_strict']-.4)<1e-9
 assert distribution(r)['weighted']==.5
 assert agreement([{'reviewer_label':'PASS','auto':'SUPPORTED'}],'auto')['cohens_kappa_strict'] is None
 assert agreement([{'reviewer_label':'UNCERTAIN','auto':'SUPPORTED'}],'auto')['n']==0
def main():
 selftest()
 # No operation above this gate opens any mapping or old evaluator data.
 seal=read(HERE/'completed.json');assert seal['completed_reviews']==160 and seal['unblinding_permitted']
 assert sha(OUT/'llm-blind-review.csv')==seal['output_sha256']
 assert sha(OUT/'manual-review-blind.csv')==seal['blind_input_sha256']
 for rid,digest in seal['review_hashes'].items():
  assert sha(OUT/'raw/llm-blind-review-v1'/rid/'review.json')==digest
 reviews=csvread(OUT/'llm-blind-review.csv')
 assert len(reviews)==160 and len({r['review_id'] for r in reviews})==160
 assert all(r['reviewer_label'] in LABELS for r in reviews)
 keys={r['review_id']:r for r in csvread(OUT/'manual-review-key.csv')}
 blind={r['review_id']:r for r in csvread(OUT/'manual-review-blind.csv')}
 assert set(keys)=={r['review_id'] for r in reviews}==set(blind)
 assert all(not r['human_label'] and not r['human_notes'] for r in blind.values())
 rows=[dict(keys[r['review_id']],**{k:v for k,v in r.items() if k!='review_id'}) for r in reviews]
 csvwrite(OUT/'llm-blind-review-unblinded.csv',rows)
 result={'method':'Independent LLM Blind Review','human_audit':'NOT_PERFORMED',
  'overall':distribution(rows),'by_version':grouped(rows,'version',distribution),
  'by_category':grouped(rows,'fact_category',distribution),
  'by_version_category':grouped(rows,'version',lambda g:grouped(g,'fact_category',distribution)),
  'definitions':{'raw_agreement':'Exact nominal reviewer/automatic label match, excludes reviewer UNCERTAIN',
   'strict':'PASS=1; PARTIAL/FAIL=0; automatic SUPPORTED=1 and all other screen labels=0',
   'weighted':'Reviewer PARTIAL=.5; 1-mean absolute score difference; not nominal agreement or weighted kappa',
   'kappa':'Cohen kappa on strict binary labels; null when marginals degenerate',
   'population':'160 stratified fact/view records of 800 candidates from 4000 records; not 160 independent compaction runs',
   'causal_inference':'Descriptive sampled-record comparison only; no preregistered noninferiority margin or cluster-adjusted population estimate'},
  'evaluator':{},'review_seal_sha256':sha(HERE/'completed.json'),'conclusion':'PENDING_FINAL_ANALYSIS',
  'context_validation':'PENDING_FINAL_ANALYSIS','resume_status':'PENDING_FINAL_ANALYSIS'}
 decision_path=HERE/'analysis-decision.json'
 if decision_path.exists():
  decision=read(decision_path)
  assert decision['review_seal_sha256']==result['review_seal_sha256']
  assert decision['conclusion'] in ['SUPPORTED','PARTIALLY_SUPPORTED','INCONCLUSIVE','NOT_SUPPORTED']
  assert decision['context_validation'] in ['READY','NEEDS_MORE_TESTING','REGRESSION_FOUND']
  for k in ['conclusion','context_validation','resume_status','rationale']:result[k]=decision[k]
 for name,field in [('frozen_v1','automatic_semantic_result'),('supplemental_v2','v2_semantic_result')]:
  assert all(r[field] in AUTO for r in rows)
  result['evaluator'][name]={'overall':agreement(rows,field),
   'by_category':grouped(rows,'fact_category',lambda g:agreement(g,field)),
   'by_version':grouped(rows,'version',lambda g:agreement(g,field))}
  result['evaluator'][name]['categories_by_disagreement']=sorted(
   [{'category':k,**v} for k,v in result['evaluator'][name]['by_category'].items()],
   key=lambda r:r['disagreement_rate'] if r['disagreement_rate'] is not None else -1,reverse=True)
 if rows and 'view' in rows[0]:
  result['by_view']=grouped(rows,'view',distribution)
  result['by_version_view']=grouped(rows,'version',lambda g:grouped(g,'view',distribution))
 # All attempts including the retained rate-limit error; missing usage is not zero.
 calls=[read(p) for p in (OUT/'raw/llm-blind-review-v1').glob('*/attempt-*/call.json')]
 complete=[c for c in calls if c.get('usage')]
 result['review_calls']={'attempts':len(calls),'status_counts':dict(collections.Counter(c['status'] for c in calls)),
  'usage_records':len(complete),'missing_usage':len(calls)-len(complete),
  'known_usage':{k:sum(c['usage'].get(k,0) for c in complete) for k in ['input_tokens','output_tokens','total_tokens']},
  'request_wall_clock_seconds_sum':sum(c['wall_clock_seconds'] for c in calls),
  'pacing_seconds_sum':sum(c.get('pre_request_pacing_ms',0) for c in calls)/1000,
  'first_start':min(c['started_at'] for c in calls),'last_end':max(c['ended_at'] for c in calls)}
 timing=result['review_calls']
 timing['observed_batch_span_seconds']=(datetime.fromisoformat(timing['last_end'].replace('Z','+00:00'))-datetime.fromisoformat(timing['first_start'].replace('Z','+00:00'))).total_seconds()
 timing['span_caveat']='Includes interruption, compilation/recovery and pacing; not compression latency or pure model latency.'
 (OUT/'llm-blind-review-analysis.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
 md=['# Independent LLM Blind Review','',
  '**This was an independent LLM blind review, not a human audit.**','',
  '## Method','',
  'The existing 160 records were retained without resampling (seed 20260905): 80 per arm, eight categories with 20 each. These are 20% of the 800-candidate pool and 4% of 4000 fact/view records. The external reviewer receives one record per fresh request, no history/tools/key. Same configured model family as generation can share biases; independence is request isolation, not an independent ground truth.',
  '', '## Blindness Controls','',
  'The orchestrating Codex conversation had prior exposure to treatments/aggregate results and cannot itself be a blind judge. It supplied no labels. External model requests contain only the frozen rubric and blind sample. All 160 valid labels were hash-sealed before this script opened the key. Original CSV and empty human columns remain unchanged. Style, length and contents can reveal treatment indirectly; explicit label blinding cannot prevent that.',
  '', '## Rubric','',
  'PASS preserves the actionable fact; PARTIAL loses important detail; FAIL loses/reverses/confuses the fact; UNCERTAIN lacks sufficient basis. Equivalent wording and numeric units are valid. Failed-attempt reasons are required only when the original supplies them. See llm-review-v1/rubric.txt.',
  '', '## Label Distribution','',str(result['overall']), '', '## OLD vs NEW','',
  '| Arm | N | PASS | PARTIAL | FAIL | UNCERTAIN | Strict | Weighted |','|---|---:|---:|---:|---:|---:|---:|---:|']
 for k,v in result['by_version'].items():md.append(f"| {k} | {v['total']} | "+' | '.join(str(v['labels'][x]) for x in LABELS)+f" | {pct(v['strict'])} | {pct(v['weighted'])} |")
 md+=['','These are descriptive scores of sampled records. Summary and effective views may duplicate facts; some failure-context views are forensic, not usable production compact output. Do not quote pooled scores as operational retention or independent run-level success. Version/view breakdowns are in the analysis JSON.','',
  '## Category Analysis','','| Category | N | PASS | PARTIAL | FAIL | UNCERTAIN | Strict | Weighted |','|---|---:|---:|---:|---:|---:|---:|---:|']
 for k,v in result['by_category'].items():md.append(f"| {k} | {v['total']} | "+' | '.join(str(v['labels'][x]) for x in LABELS)+f" | {pct(v['strict'])} | {pct(v['weighted'])} |")
 md+=['','OLD/NEW by category and each evaluator category/arm disagreement are available in llm-blind-review-analysis.json. No new architectural-decision/tool-result category was invented.','', '## Agreement','',
  '| Evaluator | Raw agreement | Disagreement | Strict agreement | Weighted credit | Strict kappa |','|---|---:|---:|---:|---:|---:|']
 for k,v in result['evaluator'].items():
  m=v['overall'];md.append(f"| {k} | {pct(m['raw_agreement'])} | {pct(m['disagreement_rate'])} | {pct(m['strict_agreement'])} | {pct(m['weighted_agreement_credit'])} | {m['cohens_kappa_strict']} |")
 md+=['','Reviewer UNCERTAIN excluded from primary denominator; automatic UNVERIFIED retains its own nominal column. Weighted credit = 1−mean absolute score difference, with PARTIAL=.5. Strict kappa collapses PARTIAL/FAIL to zero; null indicates degenerate marginals. Full confusion matrices are in the JSON. Frozen-v1 exact results are provenance only after its punctuation defect; corrected v2 is supplemental.','',
  '## Disagreement Examples','',
  'The first disagreement in review_id order from each category is shown, not selected by treatment or magnitude. Reviewer notes are model judgments, not verified truth.']
 seen=set()
 for r in sorted(rows,key=lambda x:x['review_id']):
  if r['fact_category'] in seen or r['reviewer_label']=='UNCERTAIN' or AUTO[r['v2_semantic_result']]==r['reviewer_label']:continue
  seen.add(r['fact_category']);s=blind[r['review_id']]
  md+=['',f"- {r['review_id']} / {r['fact_category']} / {r['version']}: automatic-v2={r['v2_semantic_result']}; reviewer={r['reviewer_label']}. Fact: {s['original_fact']} Notes: {r['reviewer_notes']}"]
 md+=['','## Limitations','',
  '- A single synthetic 50-fact conversation, correlated fact/view samples, two versions and one model family; no human labels or cross-family replication.',
  '- The reviewer can make mistakes and share generator biases. Agreement validates consistency only; it cannot certify true semantic retention.',
  '- Frozen v1 exact punctuation defect; v2 corrected after generation and evaluated separately. No favorable replacement of prior raw outputs.',
  '- Initial export checksum used LF before Windows CRLF translation. Actual bytes were checked against original CSV; correction archived before first review. No sample/rubric change.',
  '- R0014 attempt1 failed with service TPM rate limit and no output delta; raw error retained. Pacing added afterward; same sample retried. Calls and missing usage are included below.',
  '- No noninferiority margin, cluster-powered design or equivalence test. A small score gap is not proof of regression or improvement.',
  '',json.dumps(result['review_calls'],ensure_ascii=False,indent=2),'', '## Conclusion','',
  f"**{result['conclusion']}; Context status {result['context_validation']}.** "+result.get('rationale','Descriptive statistics are complete; final interpretation must be recorded after inspecting unblinded results. No success/regression conclusion was predetermined in this script.')]
 (OUT/'llm-blind-review-report.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
 print(json.dumps({'reviews':160,'by_version':result['by_version'],'calls':result['review_calls'],'status':result['context_validation']}))
if __name__=='__main__':main()
