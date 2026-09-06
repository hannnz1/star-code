import datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 path=ROOT/'quality-v1/protocol.json'
 if path.exists():raise SystemExit('Protocol already frozen')
 files=['quality-v1/scorer.py','quality-v1/audit.py','quality-v1/audit-challenges.json','quality-v1/ABRun.java','quality-v1/QualityWireRecorder.java','quality-v1/run.py','quality-v1/build.json','quality-v1/freeze.json','quality-v1/model-config.json','src/bench/Common.java','src/bench/RecordingClient.java']
 p=dict(study_id=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ'),attempts_per_arm=20,optional_30_runs=False,seed=20260905,allocation='twenty consecutive pairs, seeded randomized order within each pair; no concurrency',response_deadline_seconds=900,outer_run_deadline_seconds=1860,operational_endpoint='actual production compact result; no forensic rescue counted',quality_endpoint='offline exact literals and three-way conservative semantic evidence screening; unmatched is UNVERIFIED, not lost',semantic_validity_gate='Human audit >=20% of semantic judgments pending; cannot establish noninferiority until valid',human_sample_fraction=.2,noninferiority_reference_percentage_points=5,noninferiority_reference_status='project-specific analysis reference, not universal standard',production_change_gate='CONFIRMED_REGRESSION only; otherwise no production changes',paid_judge_calls=0,frozen_files={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files})
 path.write_text(json.dumps(p,indent=2),encoding='utf-8');print('PROTOCOL_FROZEN='+p['study_id'])
if __name__=='__main__':main()
