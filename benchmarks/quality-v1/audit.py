import importlib.util,json
from pathlib import Path
import scorer
ROOT=scorer.ROOT
facts=json.loads((ROOT/'context-retention/facts.json').read_text())['facts']
spec=importlib.util.spec_from_file_location('prior',ROOT/'reliability-v1/evaluate.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
cases=[
 ('F04','RetryQueue waits 730 seconds before the first retry.',False,'wrong unit'),
 ('F08','AccountMigration must not delete unrelated rows.',False,'wrong prohibited action'),
 ('F07','CartCache TTL 900 seconds was successful, but an unrelated task failed.',False,'unrelated failure'),
 ('F04','OtherQueue must wait 730 milliseconds before the first retry.',False,'wrong owner'),
 ('F04','RetryQueue must wait 731 milliseconds before the first retry.',False,'wrong number'),
 ('F08','AccountMigration must leave customer_ref unchanged.',True,'paraphrased constraint'),
 ('F18','Keep historical rows intact when fixing SubscriptionExpiry.',True,'paraphrased constraint'),
 ('F07','CartCache: TTL 900 seconds did not solve the problem.',True,'paraphrased failure'),
 ('F19','TokenRefresh: pending test for concurrent refresh requests.',True,'paraphrased task'),
 ('F04','RetryQueue must not wait 730 milliseconds before the first retry.',False,'reversed polarity'),
 ('F13','Customer suspension uses HTTP GET on /v3/customers/suspension.',False,'wrong verb'),
 ('F23','Inventory reservation accepts POST /v9/wrong.',False,'wrong API path')]
rows=[]
for fid,source,expected,kind in cases:
 f=next(f for f in facts if f['id']==fid)
 legacy=scorer.legacy.score(f,{'value':f['expected'],'evidence':source},source,scorer.legacy.OWNERS[int(fid[1:])-1])[0]
 current=scorer.evaluate(f,source);got=current['semantic']=='SUPPORTED'
 rows.append(dict(fact_id=fid,source=source,expected_supported=expected,case=kind,legacy_supported=legacy,prior_rule_supported=bool(prior.semantic(f,source)),new_screen=current,screen_matches_expected=got==expected))
# Challenge fixtures are authored examples, not human labels for real model output.
report={'challenge_cases':rows,'challenge_count':len(rows),'screen_correct':sum(r['screen_matches_expected'] for r in rows),'legacy_correct':sum(r['legacy_supported']==r['expected_supported'] for r in rows),'manual_audit_status':'PENDING_HUMAN_REVIEW','manual_disagreement_rate':None,'scope':'Synthetic challenges; not proof of semantic evaluator validity.'}
(ROOT/'quality-v1/audit-challenges.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='challenge_cases'}))
