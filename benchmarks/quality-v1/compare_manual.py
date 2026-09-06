"""Compute agreement only after the user supplies human labels. No model calls."""
import collections,csv,json,math
from pathlib import Path
csv.field_size_limit(10_000_000)
ROOT=Path(__file__).resolve().parents[1]
def readcsv(name):
 with (ROOT/'results'/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def metrics(rows):
 uncertain=sum(r['human']=='UNCERTAIN' for r in rows);valid=[r for r in rows if r['human']!='UNCERTAIN'];n=len(valid)
 confusion=collections.defaultdict(lambda:collections.Counter())
 for r in valid:confusion[r['human']][r['auto_label']]+=1
 if not n:return dict(n=0,uncertain=uncertain,raw_agreement=None,disagreement_rate=None,cohens_kappa_strict=None,confusion_matrix={})
 h=[int(r['human']=='PASS') for r in valid];a=[int(r['auto_label']=='PASS') for r in valid];w=[{'PASS':1,'PARTIAL':.5,'FAIL':0}[r['human']] for r in valid]
 strict=sum(x==y for x,y in zip(a,h))/n;pa=sum(a)/n;ph=sum(h)/n;chance=pa*ph+(1-pa)*(1-ph)
 raw=sum(r['human']==r['auto_label'] for r in valid)/n
 return dict(n=n,uncertain=uncertain,raw_agreement=raw,disagreement_rate=1-raw,strict_binary_agreement=strict,strict_binary_disagreement=1-strict,weighted_agreement_credit=1-sum(abs(x-y) for x,y in zip(a,w))/n,weighted_absolute_disagreement=sum(abs(x-y) for x,y in zip(a,w))/n,human_strict_mean=sum(h)/n,human_weighted_mean=sum(w)/n,automatic_supported_mean=pa,cohens_kappa_strict=(strict-chance)/(1-chance) if chance<1 else None,automatic_unverified_count=sum(r['auto_label']=='UNCERTAIN' for r in valid),confusion_matrix={k:dict(v) for k,v in confusion.items()})
def main():
 # Synthetic arithmetic checks, never substituted for human review.
 example=[dict(human=h,auto_label=a) for h,a in [('PASS','PASS'),('PARTIAL','PASS'),('FAIL','FAIL')]]
 assert abs(metrics(example)['strict_binary_agreement']-2/3)<1e-9
 assert abs(metrics(example)['weighted_agreement_credit']-5/6)<1e-9
 assert abs(metrics(example)['cohens_kappa_strict']-.4)<1e-9
 if not (ROOT/'results/manual-review-blind.csv').exists():raise SystemExit('Blind sample not prepared yet')
 keys={r['review_id']:r for r in readcsv('manual-review-key.csv')};rows=[];blank=0;errors=[];seen=set()
 for r in readcsv('manual-review-blind.csv'):
  rid=r['review_id'];label=r['human_label'].strip().upper()
  if rid in seen or rid not in keys:errors.append(rid);continue
  seen.add(rid)
  if not label:blank+=1;continue
  if label not in ['PASS','PARTIAL','FAIL','UNCERTAIN']:errors.append(rid);continue
  k=keys[rid];auto={'SUPPORTED':'PASS','DISTORTED':'FAIL','CONFLICT':'FAIL','UNVERIFIED':'UNCERTAIN'}[k['automatic_semantic_result']]
  v2={'SUPPORTED':'PASS','DISTORTED':'FAIL','CONFLICT':'FAIL','UNVERIFIED':'UNCERTAIN'}.get(k.get('v2_semantic_result'))
  rows.append(dict(review_id=rid,human=label,auto_label=auto,v2_auto_label=v2,category=k['fact_category'],version=k['version'],human_notes=r['human_notes']))
 result=dict(status='PENDING' if not rows else 'INCOMPLETE' if blank or errors or len(seen)!=len(keys) else 'COMPLETED',expected=len(keys),annotated=len(rows),blank=blank,invalid_ids=errors,overall=metrics(rows),by_category={k:metrics([r for r in rows if r['category']==k]) for k in sorted({r['category'] for r in rows})},by_version={k:metrics([r for r in rows if r['version']==k]) for k in ['OLD','NEW']},definitions={'raw_agreement':'literal PASS/PARTIAL/FAIL match; automatic UNVERIFIED mapped UNCERTAIN; human UNCERTAIN excluded','strict':'PASS=1, PARTIAL/FAIL=0; automatic SUPPORTED=1 else0','weighted':'human PARTIAL=.5; agreement credit=1-mean absolute score error, not standard nominal agreement','kappa':'Cohen kappa on strict binary labels, N/A for degenerate marginals','sampling':'Stratified human sample; unweighted rates describe reviewed sample, not unbiased population rates'})
 result['categories_most_disagreement']=sorted([{'category':k,'disagreement_rate':v['disagreement_rate'],'n':v['n']} for k,v in result['by_category'].items() if v['n']],key=lambda x:x['disagreement_rate'],reverse=True)
 v2_rows=[dict(r,auto_label=r['v2_auto_label']) for r in rows if r['v2_auto_label'] is not None]
 result['supplemental_v2']={'version':'post-generation punctuation correction; same human sample','overall':metrics(v2_rows),'by_category':{k:metrics([r for r in v2_rows if r['category']==k]) for k in sorted({r['category'] for r in v2_rows})},'by_version':{k:metrics([r for r in v2_rows if r['version']==k]) for k in ['OLD','NEW']}}
 (ROOT/'results/manual-review-comparison.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
 (ROOT/'results/manual-review-comparison.md').write_text('# Human review comparison\n\n'+json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 print(json.dumps({'status':result['status'],'annotated':len(rows),'required':len(keys),'overall':result['overall']}))
if __name__=='__main__':main()
