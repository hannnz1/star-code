"""Deterministic, conservative three-way evidence screening, not a semantic oracle.
Only SUPPORTED is counted as verified; UNVERIFIED is never labelled lost.
Exact applies to typed literals, not verbatim full prose. Rules are frozen pre-A/B.
"""
import importlib.util,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('legacy',ROOT/'report.py');legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
EXACT_CATEGORIES={'file','class','method','package','api','number','constraint','next'}
FAIL=r'\b(?:failed|unsuccessful|did not (?:fix|prevent|solve|help|work)|without success|no improvement|ineffective)\b'
BAN=r'\b(?:do not|must not|never|cannot|forbidden|prohibited|don.t|mustn.t)\b'
KEEP=r'\b(?:keep|preserve|retain|leave)\b.*\b(?:unchanged|intact|existing|historical|original)\b'
ACTIONS={
 'F07':[r'\bTTL\b',r'\b900\b',r'\bseconds?\b'],
 'F08':[r'\bcustomer_ref\b',r'\b(?:renam\w*|unchanged)\b'],
 'F17':[r'\b(?:clear\w*|flush\w*)\b',r'\bindex cache\b'],
 'F18':[r'\bhistorical rows\b',r'\b(?:delet\w*|keep|preserve|retain)\b'],
 'F27':[r'\bthread\w*\b',r'\b4\b',r'\b16\b'],
 'F28':[r'\bexternal dependenc\w*\b',r'\b(?:add\w*|introduc\w*)\b'],
 'F37':[r'\bfixed-rate timer\b'],
 'F38':[r'\buser-selected display names\b',r'\b(?:overwrit\w*|unchanged)\b'],
 'F47':[r'\bdisabl\w*\b',r'\bkeep-alive\b'],
 'F48':[r'\bOrderResult\b',r'\bconstructor signature\b',r'\b(?:chang\w*|unchanged)\b']}
NUMBER_RELATIONS={'F04':[r'\b(?:milliseconds?|ms)\b',r'\bfirst retry\b'],
 'F14':[r'\bbatch\w*\b',r'\bdocuments?\b'],
 'F24':[r'\b(?:max\w*|at most|limit|cap)\b',r'\b(?:route )?hops?\b'],
 'F34':[r'\b(?:cap|limit|max\w*)\b',r'\bbytes?\b'],
 'F44':[r'\b(?:at most|max\w*|limit|allow\w*)\b',r'\battempts?\b',r'\b(?:per minute|/minute)\b']}
CONTRACT={'F13':[r'PATCH',r'/v3/customers/suspension'],'F23':[r'POST',r'/v1/inventory/reservations'],'F43':[r'GET',r'/v4/accounts/summary']}
def chunks(source):
 # Lines/bullets form scope. Never join owner from one row with value from another.
 return [re.sub(r'^\s*(?:[-*]|\d+[.)])\s*','',x).strip().replace('`','') for x in re.split(r'\n|;|(?<=[.!?])\s+|,?\s+but\s+',source,flags=re.I) if x.strip()]
def literal(value,s):
 value=str(value)
 return bool(re.search(r'(?<![\w./-])'+re.escape(value)+r'(?![\w./-])',s))
def owner(f,c):
 owners=legacy.OWNERS[int(f['id'][1:])-1]
 return any(re.search(r'(?<!\w)'+re.escape(o)+r'(?:s)?(?!\w)',c,re.I) for o in owners)
def evaluate(f,source):
 applicable=f['category'] in EXACT_CATEGORIES
 exact_hit=None; semantic_hit=None; contradictions=[]
 for c in chunks(source):
  if len(c)>1500 or not owner(f,c):continue
  if re.search(r'\b(?:not true|incorrect|false claim|hypothetical|if|might|maybe|perhaps)\b',c,re.I):continue
  other=[i for i,owners in enumerate(legacy.OWNERS) if i!=int(f['id'][1:])-1 and any(re.search(r'(?<!\w)'+re.escape(o)+r'(?!\w)',c,re.I) for o in owners)]
  if other:continue
  cat=f['category'];expected=f['expected'];negative=bool(re.search(BAN,c,re.I))
  supported=False
  if cat in ['failed_attempt','negative']:
   action=all(re.search(p,c,re.I) for p in ACTIONS[f['id']])
   supported=action and bool(re.search(FAIL if cat=='failed_attempt' else BAN+'|'+KEEP,c,re.I))
   # Explicit reversal only, absence of a negative word is NOT sufficient distortion evidence.
   if action and not supported and re.search(r'\b(?:succeeded|successfully|worked|allowed to|may rename|may delete|may overwrite)\b',c,re.I):contradictions.append(c)
  elif cat=='number':
   relation=all(re.search(p,c,re.I) for p in NUMBER_RELATIONS[f['id']])
   supported=literal(expected,c) and relation and not negative
   if relation and negative and literal(expected,c):contradictions.append(c)
  else:
   allowed=[expected]+f['aliases'];value=any(str(v).casefold() in c.casefold() for v in allowed)
   supported=value and not negative
   if cat=='pending':supported=supported and bool(re.search(r'\b(?:pending|TODO|test\w*|cover\w*)\b',c,re.I))
   if cat=='next':supported=supported and bool(re.search(r'\b(?:next|inspect|run|before|command)\b',c,re.I))
   if cat=='cause':supported=supported and bool(re.search(r'\b(?:cause\w*|because|due to|bug|reason|duplication|precision loss|timeout|checksum mismatch)\b',c,re.I))
   if f['id'] in CONTRACT:supported=supported and all(literal(v,c) for v in CONTRACT[f['id']])
  if supported:
   semantic_hit=c
   if applicable and literal(expected,c):exact_hit=c
 if contradictions and semantic_hit:return {'semantic':'CONFLICT','exact':False if applicable else None,'evidence':semantic_hit,'conflict_evidence':contradictions}
 return {'semantic':'SUPPORTED' if semantic_hit else 'DISTORTED' if contradictions else 'UNVERIFIED','exact':bool(exact_hit) if applicable else None,'evidence':semantic_hit,'conflict_evidence':contradictions}
