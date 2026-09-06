"""Produce review CSV and a completion seal; never opens the unblinding key."""
import csv,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
 freeze=read(HERE/'freeze.json');source=ROOT/'results/manual-review-blind.csv'
 assert hashlib.sha256(source.read_bytes()).hexdigest()==freeze['blind_csv_sha256']
 samples=read(HERE/'blind-samples.json');results=[];hashes={}
 for sample in samples:
  rid=sample['review_id'];p=ROOT/'results/raw/llm-blind-review-v1'/rid/'review.json'
  assert p.exists(),'Review incomplete; key must remain closed: '+rid
  r=read(p);assert r['review_id']==rid
  assert r['reviewer_label'] in ['PASS','PARTIAL','FAIL','UNCERTAIN']
  assert r['reviewer_confidence'] in ['HIGH','MEDIUM','LOW'] and r['reviewer_notes'].strip()
  results.append({k:r[k] for k in ['review_id','reviewer_label','reviewer_notes','reviewer_confidence']});hashes[rid]=hashlib.sha256(p.read_bytes()).hexdigest()
 assert len(results)==160 and len({r['review_id'] for r in results})==160
 destination=ROOT/'results/llm-blind-review.csv'
 with destination.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,list(results[0]));w.writeheader();w.writerows(results)
 seal={'completed_reviews':160,'output_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'blind_input_sha256':freeze['blind_csv_sha256'],'review_hashes':hashes,'unblinding_permitted':True,'method':'Independent LLM Blind Review, not human annotation'}
 (HERE/'completed.json').write_text(json.dumps(seal,indent=2),encoding='utf-8')
 print('160_REVIEWS_SEALED; KEY_NOT_READ; UNBLINDING_NOW_PERMITTED')
if __name__=='__main__':main()
