"""After sealing, hash local raw evidence without loading large files into RAM."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def main():
 seal=json.loads((HERE/'completed.json').read_text(encoding='utf-8'))
 assert seal['completed_reviews']==160 and seal['unblinding_permitted']
 assert sha(ROOT/'results/llm-blind-review.csv')==seal['output_sha256']
 folders=['context-retention','context-reliability','context-quality-ab','llm-blind-review-v1']
 rows=[]
 for folder in folders:
  for p in sorted((ROOT/'results/raw'/folder).rglob('*')):
   if p.is_file():rows.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 for name in ['manual-review-blind.csv','manual-review-key.csv','llm-blind-review.csv',
              'llm-blind-review-unblinded.csv','llm-blind-review-analysis.json',
              'context-ab-old.csv','context-ab-new.csv','context-ab-all-started.csv',
              'context-quality-supplemental-v2.json','validation-full-tests-step1.txt',
              'validation-full-tests-step1.json']:
  p=ROOT/'results'/name
  assert p.exists(),str(p)
  rows.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 result={'schema_version':1,'purpose':'Local raw evidence index; retain indexed files with this manifest',
  'files':len(rows),'bytes':sum(r['bytes'] for r in rows),'artifacts':rows}
 (ROOT/'results/context-validation-artifact-index.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='artifacts'}))
if __name__=='__main__':main()
