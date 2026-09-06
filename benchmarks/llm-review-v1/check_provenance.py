"""Read blind inputs and synthetic fixtures only; never opens the review key."""
import hashlib,json,re,os
from pathlib import Path
from urllib.parse import urlparse
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
samples=read(HERE/'blind-samples.json')
facts=read(ROOT/'context-retention/facts.json')['facts']
conversation=read(ROOT/'context-retention/conversation.json')
statements={f['statement'] for f in facts}
messages={m['content'] for m in conversation}
assert all(s['original_fact'] in statements for s in samples)
assert all(s['source_context'] in messages for s in samples)
assert 'Frozen synthetic fixtures' in (ROOT/'generate_fixtures.py').read_text(encoding='utf-8')
config=(ROOT.parent/'config.yaml').read_text(encoding='utf-8')
endpoint=re.search(r'base_url:\s*(\S+)',config)[1].strip('\"\'')
env_name=re.search(r'api_key_env:\s*(\S+)',config)[1].strip('\"\'')
secret=os.environ.get(env_name,'')
payload=(HERE/'blind-samples.json').read_text(encoding='utf-8')
assert secret and secret not in payload,'Missing credential or credential appears in data'
assert not re.search(r'sk-[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY-----',payload)
result={'samples':len(samples),'all_original_facts_from_frozen_synthetic_dataset':True,
 'all_source_contexts_exact_frozen_synthetic_messages':True,
 'compressed_text':'Existing model outputs generated in the prior synthetic-fixture benchmark; no repository source files loaded by reviewer',
 'api_key_in_payload':False,'private_key_pattern_in_payload':False,
 'configured_destination_host':urlparse(endpoint).hostname,
 'configured_destination_scheme':urlparse(endpoint).scheme,
 'payload_sha256':hashlib.sha256((HERE/'blind-samples.json').read_bytes()).hexdigest(),
 'key_read':False,'limitations':'Pattern checks cannot prove absence of all sensitive text; source equality establishes the fixture provenance.'}
(HERE/'provenance-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
