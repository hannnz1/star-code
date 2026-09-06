"""Regenerate summaries from immutable raw records. No model calls, no metric tuning."""
import csv, hashlib, importlib.metadata, json, os, re, statistics, sys, unicodedata
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.work/python'))
os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(ROOT/'.work/tiktoken'))
OUT=ROOT/'results/summary';OUT.mkdir(parents=True,exist_ok=True)
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,obj): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def latest(mode):
 p=ROOT/'results'/f'{mode}-latest.txt'
 return ROOT/p.read_text().strip() if p.exists() else None
def norm(x):return ' '.join(unicodedata.normalize('NFKC',x).split())
def csvout(name,rows):
 if not rows:return
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def actual_usage(run):
 usages=[]
 for p in sorted((run/'wire').glob('*-response.sse')):
  for line in p.read_text(encoding='utf-8').splitlines():
   if not line.startswith('data:'):continue
   try:d=json.loads(line[5:].strip())
   except ValueError:continue
   if d.get('type')=='response.completed':
    u=d.get('response',{}).get('usage')
    if u is not None:usages.append(u)
 if not usages:return dict(input_tokens=None,output_tokens=None,total_tokens=None,usage_source='unavailable')
 return dict(input_tokens=sum(u.get('input_tokens',0) for u in usages),output_tokens=sum(u.get('output_tokens',0) for u in usages),total_tokens=sum(u.get('total_tokens',u.get('input_tokens',0)+u.get('output_tokens',0)) for u in usages),usage_source='upstream response.completed.usage; includes extraction calls')
def mcp():
 batch=latest('mcp-loading');rows=[]
 if batch is None:return {'status':'NOT_RUN'}
 enc=None;token_error=None
 try:
  import tiktoken
  enc=tiktoken.get_encoding('o200k_base')
 except Exception as e:token_error=str(e)
 for p in sorted(batch.glob('tools-*/run.json')):
  r=read(p);r['raw_path']=str(p.relative_to(ROOT));r['tokenizer']='tiktoken 0.12.0/o200k_base; estimated, not provider billing tokens'
  requests=list((p.parent/'wire').glob('*-request.json'));r['request_count']=len(requests)
  for key in ('serialized_mcp_schema_bytes','all_tool_schema_bytes','mcp_schema_estimated_tokens','all_tool_schema_estimated_tokens','complete_request_bytes','complete_request_estimated_tokens'):r[key]=None
  if requests:
   request_path=requests[0];request=read(request_path);ts=request.get('tools',[]);mcp=[t for t in ts if t.get('name','').startswith('mcp__')]
   serialize=lambda obj:json.dumps(obj,ensure_ascii=False,separators=(',',':'))
   mt,at=serialize(mcp),serialize(ts);full=request_path.read_text(encoding='utf-8')
   r.update(serialized_mcp_schema_bytes=len(mt.encode()),all_tool_schema_bytes=len(at.encode()),complete_request_bytes=len(full.encode()),observed_mcp_count=len(mcp),observed_all_tool_count=len(ts),request_json=str(request_path.relative_to(ROOT)))
   if len(mcp)!=r['tool_count'] or len(ts)!=r['tool_count']+r['builtin_tool_count']:r['status']='FAILURE';r['exception']='Serialized tool count mismatch'
   if enc:r.update(mcp_schema_estimated_tokens=len(enc.encode(mt,disallowed_special=())),all_tool_schema_estimated_tokens=len(enc.encode(at,disallowed_special=())),complete_request_estimated_tokens=len(enc.encode(full,disallowed_special=())))
  rows.append(r)
 groups=[]
 for n in (10,25,50,100):
  subset=[r for r in rows if r['tool_count']==n];valid=[r for r in subset if r['status']=='SUCCESS' and r['request_count']==1]
  g=dict(tool_count=n,attempts=len(subset),valid_runs=len(valid),status='MEASURED' if len(valid)>=5 else 'BLOCKED',lazy_status='NOT_IMPLEMENTED')
  for key in ('serialized_mcp_schema_bytes','all_tool_schema_bytes','mcp_schema_estimated_tokens','all_tool_schema_estimated_tokens','complete_request_estimated_tokens','wall_clock_seconds'):
   vals=[r[key] for r in valid if r.get(key) is not None];g[key]={'mean':statistics.mean(vals),'min':min(vals),'max':max(vals)} if vals else None
  groups.append(g)
 csvout('mcp-runs.csv',rows);write(OUT/'mcp-runs.json',rows)
 result=dict(status='MEASURED' if all(g['valid_runs']>=5 for g in groups) else 'BLOCKED',batch=str(batch.relative_to(ROOT)),groups=groups,tokenizer_error=token_error,prior_batches=[str(p.relative_to(ROOT)) for p in batch.parent.iterdir() if p!=batch],limitations=['Synthetic schemas derived from six production built-in schemas; not a sampled MCP marketplace catalog.','Local deterministic SSE sink measures serialized payload only, not network or model latency.','JSON token estimates include JSON syntax; incompatible with exact provider billing.','MCP discovery performed once per size; repeat wall times exclude discovery.'])
 write(OUT/'mcp-summary.json',result);return result
# Entity identifiers frozen before reading extraction output. Ownership is not inferred from an answer alone.
OWNERS=[['invoice export'],['shipment','PostalRouteNormalizer'],['refund'],['RetryQueue'],['billing report'],['AuditExport'],['CartCache'],['AccountMigration'],['InventoryReconcile'],['ReleaseAudit'],['shipping threshold'],['tax rounding','roundTaxHalfEven'],['customer suspension','/v3/customers/suspension'],['SearchBackfill'],['ReportMailer'],['LedgerReplay'],['SearchRefresh'],['SubscriptionExpiry'],['TokenRefresh'],['CatalogDiff'],['payment deduplication'],['notification policy'],['inventory reservation'],['DeliveryEstimator'],['InvoiceRenderer'],['PriceImport'],['LeaseCleaner'],['OrderArchive'],['CsvParser'],['RetryBudget'],['fraud score'],['CSV compatibility'],['readiness','readyz'],['StreamBuffer'],['JobScheduler'],['WebhookAck'],['MetricFlush'],['ProfileRepair'],['SessionPurge'],['RouteCache'],['locale fallback'],['reconciliation'],['account summary'],['AuthThrottle'],['MoneyFormatter'],['BlobUpload'],['SocketDrain'],['SchemaReview'],['DiscountPolicy'],['DeployChecklist']]
def score(f,answer,source,owners):
 if not isinstance(answer,dict):return False,'missing structured answer',None
 value=answer.get('value');quote=answer.get('evidence')
 if value is None:return False,'model returned missing',quote
 expected=f['expected'];allowed=[expected]+f['aliases']
 if isinstance(expected,bool):value_ok=type(value) is bool and value==expected
 elif isinstance(expected,(int,float)):value_ok=type(value) in (int,float) and Decimal(str(value))==Decimal(str(expected))
 else:value_ok=isinstance(value,str) and any(norm(value)==norm(v) for v in allowed)
 if not value_ok:return False,'typed value mismatch',quote
 if not isinstance(quote,str) or not quote.strip() or len(quote)>1000:return False,'missing or excessive evidence',quote
 nq=norm(quote)
 if nq not in norm(source):return False,'evidence is not a verbatim source quote',quote
 clauses=re.split(r'(?:[.;?!](?:\s+|$)|\b(?:while|whereas|but|however)\b)',nq,flags=re.I)
 owned=[part for part in clauses if any(norm(owner).casefold() in part.casefold() for owner in owners)]
 if not owned:return False,'evidence does not identify fact owner',quote
 negative=r'\b(not|no|never|failed|unsuccessful|without success|forbidden|prohibited|mustn.t|didn.t)\b'
 def clause_supports(part):
  neg=bool(re.search(negative,part,re.I))
  if isinstance(expected,bool):return neg if expected is False else not neg
  if neg:return False
  if isinstance(expected,(int,float)):return bool(re.search(r'(?<![\d.])'+re.escape(str(expected))+r'(?![\d.])',part.replace(',','')))
  return any(norm(v).casefold() in part.casefold() for v in allowed)
 if not any(clause_supports(part) for part in owned):return False,'value or polarity is not supported in the named-owner clause',quote
 return True,'typed value and owner-clause source evidence verified; semantic extraction is model-assisted',quote

def context():
 batch=latest('context-retention')
 if batch is None:return {'status':'NOT_RUN'}
 facts=read(ROOT/'context-retention/facts.json')['facts'];rows=[];allfacts=[]
 for p in sorted(batch.glob('repeat-*/run.json')):
  r=read(p);d=p.parent;r['raw_path']=str(p.relative_to(ROOT));r.update(actual_usage(d));calls=[read(c) for c in sorted((d/'calls').glob('*.json'))]
  compact_calls=[c for c in calls if c.get('phase')=='compact'];r['compact_attempts']=len(compact_calls);r['compact_retries']=max(0,len(compact_calls)-1);r['model_calls']=len(calls);r['failed_calls']=sum(c.get('status')!='SUCCESS' for c in calls)
  r['compact_input_tokens']=sum(c.get('input_tokens') or 0 for c in compact_calls) if compact_calls and r['usage_source']!='unavailable' else None;r['compact_output_tokens']=sum(c.get('output_tokens') or 0 for c in compact_calls) if compact_calls and r['usage_source']!='unavailable' else None
  response=compact_calls[-1].get('response_text','') if compact_calls else '';r['compact_response_characters']=len(response);r['has_summary_open']='<summary>' in response;r['has_summary_close']='</summary>' in response
  metas=[read(x) for x in sorted((d/'wire').glob('*-meta.json'))];r['wire_response_completed']=any('response.completed' in x.read_text(encoding='utf-8') for x in (d/'wire').glob('*-response.sse'));r['harness_timeout']=any(x.get('harness_timeout') is True for x in metas)
  summary=(d/'summary.txt').read_text(encoding='utf-8') if (d/'summary.txt').exists() else ''
  recent=read(d/'retained-recent.json') if (d/'retained-recent.json').exists() else [];recent_text='\n\n'.join(m.get('content') or '' for m in recent)
  recovery=(d/'recovery.txt').read_text(encoding='utf-8') if (d/'recovery.txt').exists() else ''
  complete='\n\n'.join(m.get('content') or '' for m in read(d/'compacted-context.json')) if (d/'compacted-context.json').exists() else ''
  answers={view:read(d/f'{view}-answers.json') if (d/f'{view}-answers.json').exists() else {} for view in ('summary-only','complete-context')}
  valid=r.get('status')=='SUCCESS' and (d/'summary-only-answers.json').exists() and (d/'complete-context-answers.json').exists();details=[]
  for i,f in enumerate(facts):
   a=answers['summary-only'].get(f['id']);b=answers['complete-context'].get(f['id']);s,swhy,sq=score(f,a,summary,OWNERS[i]);c,cwhy,cq=score(f,b,complete,OWNERS[i])
   origins=[]
   if s:origins.append('summary')
   # Unchanged original messages can be verified directly without trusting the extractor.
   retained=norm(f['statement']) in [norm(line) for line in recent_text.splitlines()];recovered=norm(f['statement']) in [norm(line) for line in recovery.splitlines()]
   if retained:origins.append('retained recent messages')
   if recovered:origins.append('recovery attachment')
   if c and cq:
    for label,source in [('summary',summary),('retained recent messages',recent_text),('recovery attachment',recovery)]:
     if norm(cq) in norm(source) and label not in origins:origins.append(label)
   # Context retention is fact presence: original unchanged messages are direct evidence.
   complete_pass=c or s or retained or recovered
   row=dict(run=r['run_id'],id=f['id'],category=f['category'],position=f['position'],expected=f['expected'],summary_answer=a,complete_answer=b,summary_pass=s,summary_reason=swhy,complete_extraction_pass=c,complete_reason=cwhy,complete_pass=complete_pass,sources=origins or ['missing'],original_retained=retained)
   details.append(row);allfacts.append(row)
  r['scoring_valid']=valid
  r['summary_retained']=sum(f['summary_pass'] for f in details) if valid else None;r['complete_retained']=sum(f['complete_pass'] for f in details) if valid else None
  r['summary_retention_percent']=r['summary_retained']*2 if valid else None;r['complete_retention_percent']=r['complete_retained']*2 if valid else None
  write(OUT/f"context-{r['run_id']}-facts.json",details);rows.append(r)
 write(OUT/'context-runs.json',rows);csvout('context-runs.csv',rows);csvout('context-facts.csv',allfacts)
 valid=[r for r in rows if r['scoring_valid']];result=dict(status='MEASURED' if len(valid)>=5 else 'INCOMPLETE',batch=str(batch.relative_to(ROOT)),attempts=len(rows),successful_compactions=sum(r.get('status')=='SUCCESS' for r in rows),failed_compactions=sum(r.get('status')!='SUCCESS' for r in rows),execution_success_percent=100*sum(r.get('status')=='SUCCESS' for r in rows)/len(rows) if rows else None,scored_runs=len(valid),rows=rows)
 for name in ('summary_retention_percent','complete_retention_percent'):
  vals=[r[name] for r in valid];result[name]=dict(mean=statistics.mean(vals),min=min(vals),max=max(vals),sample_stddev=statistics.stdev(vals) if len(vals)>1 else None) if vals else None
 result['limitations']=['Synthetic text-only session, not eight hours of interactive coding.','Same model extracts facts; strict frozen aliases may cause false negatives. Scores are evidence-based and conservative, not a fully validated semantic judge.','No changed-file snapshots in this dataset, so recovery attachment contribution can be zero without testing snapshot recovery.','Full context score unions verified summary evidence, complete-view extraction evidence and unchanged retained facts.','Provider model sampling defaults apply; seed fixes dataset only, not provider generation.']
 write(OUT/'context-summary.json',result);return result

def gate():
 batch=latest('multi-agent')
 if batch is None or not (batch/'run.json').exists():return {'status':'NOT_RUN'}
 r=read(batch/'run.json');r['raw_path']=str(batch.relative_to(ROOT));r.update(actual_usage(batch));calls=[read(p) for p in (batch/'calls').glob('*.json')]
 r['main_agent_calls']=sum(c.get('agent_kind')=='main' for c in calls);r['subagent_calls']=sum(c.get('agent_kind')=='subagent' for c in calls)
 r['model_call_failures']=sum(c.get('status')!='SUCCESS' for c in calls);write(OUT/'multi-agent-summary.json',r);return r

def main():
 m=mcp();c=context();g=gate();write(OUT/'summary.json',dict(mcp=m,context=c,multi_agent=g))
 print(json.dumps(dict(mcp=m['status'],context=c['status'],context_scored=c.get('scored_runs'),multi_agent=g['status']),ensure_ascii=False))
if __name__=='__main__':main()