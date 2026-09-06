"""Read genuine returned human labels; never invent missing reviewers or decisions."""
import csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=json.loads((ROOT/'quality-v1/protocol.json').read_text())
key_path=ROOT/'results/raw/context-quality-ab'/p['study_id']/'human-audit-key.json'
if not key_path.exists():raise SystemExit('Audit sample not ready; complete the forty attempts and analyze.')
key={r['case_id']:r for r in json.loads(key_path.read_text())}
sheet=ROOT/'results/context-quality-human-audit/review-sheet.csv'
with sheet.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
valid=[];errors=[];seen=set()
for r in rows:
 if not r.get('human_label','').strip():continue
 case=r['case_id'];label=r['human_label'].strip().upper()
 if case in seen or case not in key or label not in ['SUPPORTED','DISTORTED','MISSING','CONFLICT','UNCERTAIN'] or not r.get('reviewer','').strip() or not r.get('reviewed_at','').strip() or not r.get('human_reason','').strip():errors.append(case);continue
 seen.add(case);k=key[case]
 valid.append(dict(**k,human_label=label,reviewer=r['reviewer'],human_reason=r['human_reason'],human_evidence=r['human_evidence'],disagrees=(k['automatic_state']=='SUPPORTED')!=(label=='SUPPORTED') if label!='UNCERTAIN' else None))
scored=[r for r in valid if r['disagrees'] is not None]
result=dict(required_sample=len(key),completed=len(valid),uncertain=len(valid)-len(scored),invalid_rows=errors,status='COMPLETE_REQUIRES_ANALYST_REVIEW' if len(valid)==len(key) and not errors else 'INCOMPLETE',binary_support_disagreement_rate=sum(r['disagrees'] for r in scored)/len(scored) if scored else None,definition='SUPPORTED vs non-supported, excluding human UNCERTAIN; not general semantic accuracy',judgments=valid)
(ROOT/'results/human-audit-results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='judgments'}))
