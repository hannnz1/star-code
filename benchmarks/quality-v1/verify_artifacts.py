"""Integrity checks only; does not fill or compare human judgments."""
import collections,csv,hashlib,json
from pathlib import Path
import scorer,manual_review
ROOT=Path(__file__).resolve().parents[1];csv.field_size_limit(10_000_000)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(name):
 with (ROOT/'results'/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
 study=read(ROOT/'results/context-quality-study.json');freeze=read(ROOT/'quality-v1/freeze.json');protocol=read(ROOT/'quality-v1/protocol.json')
 assert len(study['runs'])==40
 assert collections.Counter(r['arm'] for r in study['runs'])=={'old':20,'new':20}
 for name,value in protocol['frozen_files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value,name
 checkout=Path(freeze['arms']['new']['checkout'])
 for name,value in freeze['arms']['new']['source_hashes'].items():
  assert hashlib.sha256((checkout/name).read_bytes()).hexdigest()==value,'Frozen checkout changed: '+name
  assert (ROOT.parent/name).read_bytes().replace(b'\r\n',b'\n')==(checkout/name).read_bytes().replace(b'\r\n',b'\n'),'Main production/test source content changed: '+name
 blind=rows('manual-review-blind.csv');key=rows('manual-review-key.csv');mapping={r['review_id']:r for r in key}
 assert len(blind)==len(mapping)==160
 assert set(blind[0])=={'review_id','fact_category','original_fact','source_context','compressed_context_or_summary','human_label','human_notes'}
 facts=read(ROOT/'context-retention/facts.json')['facts'];by_id={f['id']:f for f in facts}
 for r in blind:
  k=mapping[r['review_id']]
  assert r['original_fact']==by_id[k['fact_id']]['statement']
  assert r['original_fact'] in r['source_context']
  assert hashlib.sha256(r['compressed_context_or_summary'].encode()).hexdigest()==k['source_sha256']
  assert r['human_label']==r['human_notes']=='','Human data already entered; do not claim pending/overwrite'
 assert collections.Counter(k['version'] for k in key)=={'OLD':80,'NEW':80}
 assert set(collections.Counter(r['fact_category'] for r in blind).values())=={20}
 # Broader post-freeze positive-control audit. Preserve the frozen scorer/results.
 controls=[]
 for f in facts:
  result=scorer.evaluate(f,f['statement']);controls.append({'fact_id':f['id'],'category':f['category'],'expected_semantic':'SUPPORTED','actual':result,'exact_applicable':f['category'] in scorer.EXACT_CATEGORIES})
 audit={'timing':'Post-freeze diagnostic; no scorer or production modifications','semantic_supported':sum(r['actual']['semantic']=='SUPPORTED' for r in controls),'semantic_total':50,'exact_pass':sum(r['actual']['exact'] is True for r in controls),'exact_applicable':sum(r['exact_applicable'] for r in controls),'cases':controls}
 (ROOT/'results/evaluator-original-positive-controls.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
 # Verify reproducible sampling and preservation without re-running model analysis.
 batch=ROOT/'results/raw/context-quality-ab'/study['study_id'];details=[]
 for r in study['runs']:details.extend(read(batch/r['run_id']/'forensics/fact-judgments.json'))
 before=hashlib.sha256((ROOT/'results/manual-review-blind.csv').read_bytes()).hexdigest()
 manual_review.prepare(batch,details,facts)
 assert hashlib.sha256((ROOT/'results/manual-review-blind.csv').read_bytes()).hexdigest()==before
 result={'integrity':'PASS','selected_model_attempts':40,'all_started_attempts':len(study['all_started_runs']),'blind_records':160,'human_labels_filled':0,'sampling_reproducible':True,'production_sources_unchanged':True,'original_control_semantic_supported':audit['semantic_supported'],'original_control_exact_pass':audit['exact_pass'],'original_control_exact_applicable':audit['exact_applicable']}
 (ROOT/'results/quality-artifact-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
