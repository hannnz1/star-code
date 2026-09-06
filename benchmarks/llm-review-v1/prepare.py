"""Reads the blind CSV only. Never opens the key or old scores."""
import csv,hashlib,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
csv.field_size_limit(10_000_000)
def main():
 source=ROOT/'results/manual-review-blind.csv'
 with source.open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f);headers=reader.fieldnames;rows=list(reader)
 assert set(headers)=={'review_id','fact_category','original_fact','source_context','compressed_context_or_summary','human_label','human_notes'}
 assert len(rows)==160 and len({r['review_id'] for r in rows})==160
 samples=[]
 suspect=re.compile(r'\b(?:OLD|NEW)[ _-]+(?:VERSION|ARM)\b|\bautomatic[ _]+(?:semantic|exact|evaluator)\b|\b(?:retention[ _]+score|run[ _]+total[ _]+score)\b',re.I)
 for r in rows:
  assert not r['human_label'].strip() and not r['human_notes'].strip(),'Annotations present; stop'
  clean={k:r[k] for k in ['review_id','fact_category','original_fact','source_context','compressed_context_or_summary']}
  assert not any(suspect.search(v) for v in clean.values()),'Potential explicit metadata leak in '+r['review_id']
  samples.append(clean)
 payload=json.dumps(samples,ensure_ascii=False,indent=2)
 # Hash the actual saved bytes: Windows text writes can translate LF to CRLF.
 sample_file=HERE/'blind-samples.json'
 if sample_file.exists():
  assert sample_file.read_text(encoding='utf-8')==payload,'Frozen sample content differs'
 else:
  encoded=payload.encode('utf-8')
  if (HERE/'freeze.json').exists():
   expected=json.loads((HERE/'freeze.json').read_text(encoding='utf-8'))['samples_sha256']
   if hashlib.sha256(encoded).hexdigest()!=expected:
    encoded=payload.replace('\n','\r\n').encode('utf-8')
   assert hashlib.sha256(encoded).hexdigest()==expected,'Cannot reproduce frozen export bytes'
  sample_file.write_bytes(encoded)
 freeze={'blind_csv_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'samples_sha256':hashlib.sha256(sample_file.read_bytes()).hexdigest(),'sample_count':160,'input_fields':list(samples[0]),'leak_scan':'schema and explicit metadata patterns PASS; content/style inference remains possible','orchestrator_context':'Previously exposed to versions/scores; must not supply judgments. Fresh stateless external model requests are the reviewer.','rubric_sha256':hashlib.sha256((HERE/'rubric.txt').read_bytes()).hexdigest(),'temperature':0,'max_output_tokens':2048,'max_attempts_per_sample':2,'unblinding_gate':'All160 valid reviews saved and sealed before key access','annotation_method':'Independent LLM Blind Review; not human annotation'}
 for p,content in [(HERE/'blind-samples.json',payload),(HERE/'freeze.json',json.dumps(freeze,indent=2))]:
  if p.exists():assert p.read_text(encoding='utf-8')==content,'Frozen file differs'
  else:p.write_text(content,encoding='utf-8')
 print('160 SAMPLES; LEAK_SCAN_PASS; ORIGINAL_UNCHANGED; KEY_NOT_READ')
if __name__=='__main__':main()
